"""Reading queue recommendation engine for the literature v3 system.

Scores unread/skimmed papers using 4 signals:
  1. project_relevance — BM25 match against PURPOSE.md keywords
  2. co_citation       — overlap with papers you've already read
  3. recency           — exponential decay by publication year
  4. pagerank          — normalised PageRank score

Usage:
    from literature.scripts.recommend import recommend_next
    from pathlib import Path

    results = recommend_next(Path("literature"), top_k=5)
    for r in results:
        print(r["paper_id"], r["score"])
"""

from __future__ import annotations

import datetime
import math
import sqlite3
from pathlib import Path



# ── Scoring signals ─────────────────────────────────────────────────────────────


def _score_project_relevance(
    paper: sqlite3.Row, keywords: list[str], db: sqlite3.Connection
) -> float:
    """BM25 score of paper's text against PURPOSE.md keywords.

    Returns 0.0 if no keywords are provided or if the paper isn't in FTS.
    BM25 scores from SQLite are negative (more negative = more relevant), so
    we take the absolute value and normalise by dividing by 20.

    Args:
        paper: A row from the papers table.
        keywords: List of keywords extracted from PURPOSE.md.
        db: Open database connection.

    Returns:
        Non-negative float. Higher = more relevant to project purpose.
    """
    if not keywords:
        return 0.0
    query = " ".join(f'"{k}"' for k in keywords[:20])  # cap at 20 keywords
    try:
        row = db.execute(
            "SELECT bm25(papers_fts) as score FROM papers_fts "
            "WHERE papers_fts MATCH ? AND paper_id = ?",
            (query, paper["paper_id"]),
        ).fetchone()
        if row and row["score"] is not None:
            return abs(row["score"]) / 20.0  # normalise negative BM25 to positive [0, ∞)
    except Exception:
        pass
    return 0.0


def _score_co_citation(
    paper: sqlite3.Row, read_citekeys: set[str], db: sqlite3.Connection
) -> float:
    """Papers that share references with papers you've read = more relevant.

    Computes Jaccard-like overlap between:
    - citations made by this candidate paper
    - citations made by all papers you've already read

    Args:
        paper: A row from the papers table.
        read_citekeys: Set of paper_ids the user has read/synthesized.
        db: Open database connection.

    Returns:
        Float in [0, 1]. Higher = more citation overlap with read papers.
    """
    if not read_citekeys:
        return 0.0

    # Papers this candidate cites
    candidate_citations = {
        row["cited_id"]
        for row in db.execute(
            "SELECT cited_id FROM citations WHERE citing_id = ?", (paper["paper_id"],)
        )
    }

    # Papers the read papers cite
    read_citations: set[str] = set()
    for read_key in read_citekeys:
        for row in db.execute(
            "SELECT cited_id FROM citations WHERE citing_id = ?", (read_key,)
        ):
            read_citations.add(row["cited_id"])

    overlap = len(candidate_citations & read_citations)
    return min(overlap / max(len(read_citations), 1), 1.0)


def _score_recency(paper: sqlite3.Row) -> float:
    """Exponential decay: papers from 3 years ago get ~0.5, older papers less.

    Uses half-life of 3 years so recent papers score near 1.0 and papers
    published 10+ years ago score near 0.1.

    Args:
        paper: A row from the papers table (must have 'year' column).

    Returns:
        Float in (0, 1]. Higher = more recent.
    """
    year = paper["year"] or 2000
    current_year = datetime.datetime.now().year
    age = current_year - year
    half_life = 3.0
    return math.exp(-age * math.log(2) / half_life)


def _score_pagerank(paper: sqlite3.Row, max_pagerank: float) -> float:
    """Normalise PageRank to [0, 1] range using the collection maximum.

    Args:
        paper: A row from the papers table (must have 'pagerank_score' column).
        max_pagerank: Maximum pagerank_score across all papers in the corpus.

    Returns:
        Float in [0, 1]. Higher = more cited/influential.
    """
    if max_pagerank <= 0:
        return 0.0
    return min((paper["pagerank_score"] or 0.0) / max_pagerank, 1.0)


# ── Public API ──────────────────────────────────────────────────────────────────


def recommend_next(
    root: Path,
    *,
    top_k: int = 10,
    exclude_status: list[str] | None = None,
) -> list[dict]:
    """Return top-k recommended papers with score breakdowns.

    Papers with reading_status_global in *exclude_status* are excluded from
    results (default: "read" and "synthesized").

    Signal weights depend on what data is available:
    - Cold start (no PURPOSE.md, no read papers): 50% recency + 50% pagerank
    - No PURPOSE.md (but have read papers): 35% co-citation + 35% recency + 30% pagerank
    - No read papers (but have PURPOSE.md): 55% project_relevance + 25% recency + 20% pagerank
    - Full signals: 35% project_relevance + 25% co-citation + 20% recency + 20% pagerank

    Args:
        root: Path to the literature/ directory (or any ancestor containing it).
        top_k: Maximum number of results to return.
        exclude_status: Reading statuses to exclude (default: ["read", "synthesized"]).

    Returns:
        List of dicts sorted descending by score. Each dict contains:
        - paper_id
        - title
        - year
        - reading_status
        - pagerank_score
        - score (float, weighted total)
        - score_breakdown (dict with keys: project_relevance, co_citation,
          recency, pagerank)
    """
    if exclude_status is None:
        exclude_status = ["read", "synthesized"]

    from literature.scripts.db import get_db
    from literature.scripts.purpose import extract_keywords, load_purpose

    db = get_db(root)

    # ── Signals preparation ──────────────────────────────────────────────────────

    # Keywords from PURPOSE.md
    purpose_text = load_purpose(root)
    keywords = extract_keywords(purpose_text) if purpose_text else []

    # Papers already read (for co-citation signal)
    read_rows = db.execute(
        "SELECT paper_id FROM papers WHERE reading_status_global IN ('read', 'synthesized')"
    ).fetchall()
    read_citekeys = {row["paper_id"] for row in read_rows}

    # Candidate papers (not in exclude_status)
    placeholders = ",".join("?" * len(exclude_status))
    candidates = db.execute(
        f"SELECT * FROM papers WHERE reading_status_global NOT IN ({placeholders})",
        exclude_status,
    ).fetchall()

    # Max pagerank for normalisation
    max_pr_row = db.execute("SELECT MAX(pagerank_score) FROM papers").fetchone()
    max_pr = (max_pr_row[0] or 0.0) if max_pr_row else 0.0

    # ── Score each candidate ─────────────────────────────────────────────────────

    results = []
    for paper in candidates:
        pr = _score_project_relevance(paper, keywords, db)
        cc = _score_co_citation(paper, read_citekeys, db)
        re = _score_recency(paper)
        pa = _score_pagerank(paper, max_pr)

        # Weight scheme: depends on signal availability
        if not keywords and not read_citekeys:
            # Cold start: only recency + pagerank
            total = 0.5 * re + 0.5 * pa
            breakdown = {
                "project_relevance": 0.0,
                "co_citation": 0.0,
                "recency": re,
                "pagerank": pa,
            }
        elif not keywords:
            # Have read papers but no PURPOSE.md
            total = 0.35 * cc + 0.35 * re + 0.30 * pa
            breakdown = {
                "project_relevance": 0.0,
                "co_citation": cc,
                "recency": re,
                "pagerank": pa,
            }
        elif not read_citekeys:
            # Have PURPOSE.md but no read papers
            total = 0.55 * pr + 0.25 * re + 0.20 * pa
            breakdown = {
                "project_relevance": pr,
                "co_citation": 0.0,
                "recency": re,
                "pagerank": pa,
            }
        else:
            # Full signal set
            total = 0.35 * pr + 0.25 * cc + 0.20 * re + 0.20 * pa
            breakdown = {
                "project_relevance": pr,
                "co_citation": cc,
                "recency": re,
                "pagerank": pa,
            }

        results.append(
            {
                "paper_id": paper["paper_id"],
                "title": paper["title"],
                "year": paper["year"],
                "reading_status": paper["reading_status_global"],
                "pagerank_score": paper["pagerank_score"],
                "score": total,
                "score_breakdown": breakdown,
            }
        )

    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:top_k]
