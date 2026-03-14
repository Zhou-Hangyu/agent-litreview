"""PageRank and HITS algorithms for the literature citation graph.

Provides:
    compute_pagerank(db)  — PageRank scores for all papers
    compute_hits(db)      — HITS hub/authority scores
    store_pagerank_scores(db, scores) — persist scores to papers table

Uses scipy sparse matrices when available; falls back to pure-Python
power iteration otherwise.  No NetworkX dependency.
"""

from __future__ import annotations

import math
import sqlite3
from pathlib import Path



# ── PageRank ──────────────────────────────────────────────────────────────────


def compute_pagerank(
    db: sqlite3.Connection,
    *,
    damping: float = 0.85,
    max_iter: int = 100,
    tol: float = 1e-6,
) -> dict[str, float]:
    """Compute PageRank scores for all papers in the citation graph.

    Builds an adjacency from the ``citations`` table (edge = citing → cited)
    and runs power iteration.  Tries scipy sparse first, falls back to
    pure-Python if scipy is unavailable.

    Returns:
        ``{paper_id: pagerank_score}`` normalised so scores sum ≈ 1.0.
        Empty dict if the graph has no nodes.
    """
    paper_ids, adj_sets = _load_graph(db)
    n = len(paper_ids)
    if n == 0:
        return {}

    result = _pagerank_scipy(adj_sets, n, paper_ids, damping, max_iter, tol)
    if result is not None:
        return result

    return _pagerank_pure_python(adj_sets, n, paper_ids, damping, max_iter, tol)


# ── HITS ──────────────────────────────────────────────────────────────────────


def compute_hits(
    db: sqlite3.Connection,
    *,
    max_iter: int = 50,
    tol: float = 1e-6,
) -> tuple[dict[str, float], dict[str, float]]:
    """Compute HITS hub and authority scores.

    Hub   = paper that *cites* many important papers.
    Authority = paper *cited by* many important papers.

    Returns:
        ``(hub_scores, authority_scores)`` — each a ``{paper_id: score}`` dict.
        Empty dicts if the graph has no nodes.
    """
    paper_ids, adj_sets = _load_graph(db)
    n = len(paper_ids)
    if n == 0:
        return {}, {}

    idx = {pid: i for i, pid in enumerate(paper_ids)}

    # Build adjacency list: out_links[i] = set of nodes i points to
    # and in_links[i] = set of nodes pointing to i
    out_links: dict[int, set[int]] = {i: set() for i in range(n)}
    in_links: dict[int, set[int]] = {i: set() for i in range(n)}
    for src, dsts in adj_sets.items():
        for dst in dsts:
            out_links[src].add(dst)
            in_links[dst].add(src)

    # Initialise
    hub = {i: 1.0 for i in range(n)}
    auth = {i: 1.0 for i in range(n)}

    for _ in range(max_iter):
        # Authority update: auth[i] = sum of hub[j] for j → i
        new_auth = {i: sum(hub[j] for j in in_links[i]) for i in range(n)}
        # Hub update: hub[i] = sum of auth[j] for i → j
        new_hub = {i: sum(new_auth[j] for j in out_links[i]) for i in range(n)}

        # Normalise
        auth_norm = math.sqrt(sum(v * v for v in new_auth.values())) or 1.0
        hub_norm = math.sqrt(sum(v * v for v in new_hub.values())) or 1.0
        new_auth = {i: v / auth_norm for i, v in new_auth.items()}
        new_hub = {i: v / hub_norm for i, v in new_hub.items()}

        # Convergence check
        diff = sum(abs(new_auth[i] - auth[i]) for i in range(n)) + sum(
            abs(new_hub[i] - hub[i]) for i in range(n)
        )
        auth, hub = new_auth, new_hub
        if diff < tol:
            break

    hub_scores = {paper_ids[i]: hub[i] for i in range(n)}
    auth_scores = {paper_ids[i]: auth[i] for i in range(n)}
    return hub_scores, auth_scores


# ── Storage ───────────────────────────────────────────────────────────────────


def store_pagerank_scores(
    db: sqlite3.Connection,
    pagerank: dict[str, float],
) -> None:
    """Persist PageRank scores into the ``papers.pagerank_score`` column."""
    with db:
        for paper_id, score in pagerank.items():
            db.execute(
                "UPDATE papers SET pagerank_score = ? WHERE paper_id = ?",
                (score, paper_id),
            )


# ── Internal helpers ──────────────────────────────────────────────────────────


def _load_graph(
    db: sqlite3.Connection,
) -> tuple[list[str], dict[int, set[int]]]:
    """Load citation graph from the DB.

    Returns:
        ``(paper_ids, adj_sets)`` where ``paper_ids`` is a list of paper IDs
        (index = node number) and ``adj_sets[i]`` is the set of node indices
        that node *i* links to (outgoing edges: citing → cited).
    """
    rows = db.execute("SELECT paper_id FROM papers ORDER BY paper_id").fetchall()
    paper_ids = [r[0] for r in rows]
    idx = {pid: i for i, pid in enumerate(paper_ids)}
    n = len(paper_ids)

    adj: dict[int, set[int]] = {i: set() for i in range(n)}
    edges = db.execute("SELECT citing_id, cited_id FROM citations").fetchall()
    for citing, cited in edges:
        src = idx.get(citing)
        dst = idx.get(cited)
        if src is not None and dst is not None:
            adj[src].add(dst)

    return paper_ids, adj


def _pagerank_scipy(
    adj_sets: dict[int, set[int]],
    n: int,
    paper_ids: list[str],
    damping: float,
    max_iter: int,
    tol: float,
) -> dict[str, float] | None:
    """scipy sparse PageRank — fast for large graphs.  Returns None if scipy
    is not installed so the caller can fall back to pure Python."""
    try:
        from scipy import sparse
        import numpy as np
    except ImportError:
        return None

    # Build column-stochastic transition matrix.
    # Edge (i→j) means j receives rank from i.  The transition matrix M has
    # M[j, i] = 1/out_degree(i) so that rank flows from column i to row j.
    rows_list: list[int] = []
    cols_list: list[int] = []
    for src, dsts in adj_sets.items():
        for dst in dsts:
            rows_list.append(dst)
            cols_list.append(src)

    if not rows_list:
        # No edges — uniform distribution
        return {paper_ids[i]: 1.0 / n for i in range(n)}

    data = [1.0] * len(rows_list)
    A = sparse.csr_matrix(
        (data, (rows_list, cols_list)), shape=(n, n), dtype=float
    )

    col_sums = np.array(A.sum(axis=0)).flatten()
    col_sums[col_sums == 0] = 1.0  # dangling nodes
    D_inv = sparse.diags(1.0 / col_sums)
    M = A @ D_inv

    rank = np.ones(n) / n
    for _ in range(max_iter):
        new_rank = damping * (M @ rank) + (1 - damping) / n
        # Re-distribute dangling-node mass
        dangling_mass = damping * sum(
            rank[i] for i in range(n) if len(adj_sets.get(i, set())) == 0
        )
        new_rank += dangling_mass / n
        if np.linalg.norm(new_rank - rank, 1) < tol:
            rank = new_rank
            break
        rank = new_rank

    return {paper_ids[i]: float(rank[i]) for i in range(n)}


def _pagerank_pure_python(
    adj_sets: dict[int, set[int]],
    n: int,
    paper_ids: list[str],
    damping: float,
    max_iter: int,
    tol: float,
) -> dict[str, float]:
    """Pure-Python power iteration — no numpy/scipy required.

    Uses dict-of-sets adjacency for O(1) neighbour lookup.
    """
    if n == 0:
        return {}

    # Build reverse adjacency (incoming edges) for efficient iteration
    in_links: dict[int, set[int]] = {i: set() for i in range(n)}
    out_degree: dict[int, int] = {i: len(adj_sets.get(i, set())) for i in range(n)}
    for src, dsts in adj_sets.items():
        for dst in dsts:
            in_links[dst].add(src)

    rank = {i: 1.0 / n for i in range(n)}

    for _ in range(max_iter):
        new_rank: dict[int, float] = {}

        # Dangling node mass — nodes with no outgoing edges
        dangling_mass = damping * sum(
            rank[i] for i in range(n) if out_degree[i] == 0
        )

        for i in range(n):
            incoming_rank = sum(
                rank[j] / out_degree[j] for j in in_links[i] if out_degree[j] > 0
            )
            new_rank[i] = (1 - damping) / n + damping * incoming_rank + dangling_mass / n

        # Convergence check
        diff = sum(abs(new_rank[i] - rank[i]) for i in range(n))
        rank = new_rank
        if diff < tol:
            break

    return {paper_ids[i]: rank[i] for i in range(n)}
