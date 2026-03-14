"""BM25 full-text search over the SQLite FTS5 index.

Provides two public functions:

    search(query, root, *, top_k=20)  — keyword BM25 search
    similar(citekey, root, *, top_k=10) — find papers with similar content

Usage:
    from literature.scripts.search import search, similar
    from pathlib import Path

    root = Path("literature")
    results = search("attention mechanism", root)
    for r in results:
        print(r["paper_id"], r["score"], r["title"])
"""

from __future__ import annotations

from pathlib import Path



# ── FTS5 helpers ───────────────────────────────────────────────────────────────


def _escape_fts_query(query: str, *, use_or: bool = False) -> str:
    """Escape a user query for safe use in FTS5 MATCH expressions.

    Splits on whitespace only — hyphenated terms like "self-attention" remain
    as single tokens, matching the FTS5 index (tokenize="unicode61 tokenchars '-_'").

    Args:
        query: Raw user query string.
        use_or: If True, join terms with OR (any match); otherwise AND (all match).

    Returns:
        FTS5-safe MATCH expression.
    """
    words = query.strip().split()
    if not words:
        return '""'
    quoted = [f'"{w}"' for w in words if w]
    return " OR ".join(quoted) if use_or else " ".join(quoted)


def _run_fts_search(
    conn,
    fts_query: str,
    top_k: int,
) -> list[dict]:
    """Execute a single FTS5 MATCH query and return result dicts.

    Args:
        conn: Open ``sqlite3.Connection``.
        fts_query: Already-escaped FTS5 MATCH expression.
        top_k: Maximum number of rows to return.

    Returns:
        List of dicts with keys: paper_id, title, year, reading_status,
        citation_count, score, snippet.  May be empty.
    """
    sql = """
        SELECT
            p.paper_id,
            p.title,
            p.year,
            p.reading_status_global,
            p.citation_count,
            bm25(papers_fts) AS score,
            snippet(papers_fts, 2, '«', '»', '...', 20) AS snippet
        FROM papers_fts
        JOIN papers p ON papers_fts.paper_id = p.paper_id
        WHERE papers_fts MATCH ?
        ORDER BY score ASC
        LIMIT ?
    """
    try:
        rows = conn.execute(sql, (fts_query, top_k)).fetchall()
    except Exception:
        return []

    results = []
    for row in rows:
        results.append(
            {
                "paper_id": row["paper_id"],
                "title": row["title"],
                "year": row["year"],
                "reading_status": row["reading_status_global"],
                "citation_count": row["citation_count"],
                "score": row["score"],
                "snippet": row["snippet"] or "",
            }
        )
    return results


# ── Public API ─────────────────────────────────────────────────────────────────


def search(query: str, root: Path, *, top_k: int = 20) -> list[dict]:
    """BM25 full-text search over the FTS5 index.

    Searches the ``papers_fts`` virtual table using SQLite's built-in BM25
    ranking.  Results are sorted by relevance (most relevant first).

    Implements a relaxed fallback: if the full multi-word query returns zero
    results, terms are dropped from the end one at a time until results are
    found or no terms remain.

    Args:
        query: Free-text search query.
        root: Path to the ``literature/`` directory (or any ancestor
              containing it).
        top_k: Maximum number of results to return (default: 20).

    Returns:
        List of dicts, each with keys:

        - ``paper_id``       — citekey / document ID
        - ``title``          — paper title
        - ``year``           — publication year (int or None)
        - ``reading_status`` — global reading status string
        - ``citation_count`` — integer citation count
        - ``score``          — BM25 score (negative float; more negative = more relevant)
        - ``snippet``        — excerpt from abstract with match markers (``«``, ``»``)

        Empty list if no results or empty query.
    """
    from literature.scripts.db import get_db

    query = query.strip()
    if not query:
        return []

    conn = get_db(root)
    try:
        words = query.split()

        # Try progressively shorter queries (drop from end) until results found
        while words:
            fts_query = _escape_fts_query(" ".join(words))
            results = _run_fts_search(conn, fts_query, top_k)
            if results:
                return results
            words = words[:-1]

        return []
    finally:
        conn.close()


def similar(citekey: str, root: Path, *, top_k: int = 10) -> list[dict]:
    """Find papers with similar content using BM25 on the target paper's abstract.

    Loads the target paper's abstract and TLDR, uses them as a BM25 query,
    and returns the top-K most similar papers (excluding the target itself).

    Args:
        citekey: The citekey of the paper to find similar papers for.
        root: Path to the ``literature/`` directory (or any ancestor
              containing it).
        top_k: Maximum number of similar papers to return (default: 10).

    Returns:
        List of result dicts (same schema as :func:`search`), excluding the
        target paper.  Empty list if the paper is not found or has no abstract.
    """
    from literature.scripts.db import get_db

    conn = get_db(root)
    try:
        row = conn.execute(
            "SELECT title, abstract, tldr FROM papers WHERE paper_id = ?",
            (citekey,),
        ).fetchone()

        if row is None:
            return []

        title = (row["title"] or "").strip()
        tldr = (row["tldr"] or "").strip()
        abstract = (row["abstract"] or "").strip()

        combined_words = title.split() + tldr.split()[:20] + abstract.split()[:30]
        if not combined_words:
            return []

        fts_query = _escape_fts_query(" ".join(combined_words), use_or=True)
        results = _run_fts_search(conn, fts_query, top_k + 1)

        # Exclude the target paper itself
        filtered = [r for r in results if r["paper_id"] != citekey]
        return filtered[:top_k]
    finally:
        conn.close()
