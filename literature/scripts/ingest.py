"""
Progressive summarization queue manager for the literature v3 system.

This module is a QUEUE MANAGEMENT system — it does NOT call any LLM API.
The agent (human or AI) is responsible for generating summaries.
ingest.py manages the queue of papers needing summarization and stores results.

Summary levels:
    L4 — One-liner (20–30 words). The "leaf" summary, used in fast scanning.
    L2 — 3–5 key claims as a list. Used for structured synthesis.

Prompt templates (for agent use):

    L4_PROMPT_TEMPLATE — Generate a single-sentence summary of core contribution.
    L2_PROMPT_TEMPLATE — Extract 3–5 key claims as a bullet list.

Typical usage:
    1. Agent calls get_ingest_queue(root, "l4") to see what needs L4 summaries.
    2. Agent generates a summary via LLM using L4_PROMPT_TEMPLATE.
    3. Agent calls mark_ingested(citekey, root, "l4", summary_text, model_name).
    4. Agent calls lit rebuild to sync the updated frontmatter into SQLite.
"""

from __future__ import annotations

from pathlib import Path



# ── Prompt templates ───────────────────────────────────────────────────────────

L4_PROMPT_TEMPLATE = """
Generate a single sentence (20-30 words) summarizing this paper's core contribution.
Be specific about WHAT was built/discovered and WHY it matters.
Do NOT start with "The paper" or "This paper".

Paper: {title}
Abstract: {abstract}

Output format: One sentence only.
"""

L2_PROMPT_TEMPLATE = """
Extract 3-5 key claims from this paper as a bullet list.
Each claim should be a complete, standalone statement about the paper's findings or methods.
Be specific and avoid vague phrases like "improves performance".

Paper: {title}
Abstract: {abstract}

Output format: A Python list of strings, one claim per item.
"""


# ── Public API ─────────────────────────────────────────────────────────────────


def needs_summary(citekey: str, root: Path, level: str = "l4") -> bool:
    """Return True if the paper needs an L4 or L2 summary (missing or stale).

    Uses is_summary_stale() from parse.py (default 90-day staleness).

    Args:
        citekey: Paper citekey (e.g. 'vaswani2017attention').
        root: Path hint for the literature directory (passed to _find_literature_root).
        level: Summary level — 'l4' (one-liner) or 'l2' (claims list).

    Returns:
        True if the paper is missing, has no summary at this level, or the
        summary is older than 90 days.
    """
    from literature.scripts.parse import read_frontmatter, is_summary_stale
    from literature.scripts.rebuild_index import _find_literature_root

    lit_root = _find_literature_root(root)
    paper_path = lit_root / "papers" / f"{citekey}.md"
    if not paper_path.exists():
        return True  # Paper doesn't exist — definitely needs processing
    meta, _ = read_frontmatter(paper_path)
    return is_summary_stale(meta, level)


def get_ingest_queue(root: Path, level: str = "l4") -> list[dict]:
    """Return list of papers needing summarization at the given level.

    Papers are sorted by PageRank score descending (most important first).
    Only papers with a corresponding .md file in papers/ are included.

    Args:
        root: Path hint for the literature directory.
        level: 'l4' — return only papers needing L4 summaries.
               'l2' — return only papers needing L2 summaries.
               'all' — return papers needing either L4 or L2 summaries.

    Returns:
        List of dicts with keys:
            paper_id, title, abstract, needs_l4, needs_l2, pagerank_score
        Sorted by pagerank_score descending.
    """
    from literature.scripts.db import get_db
    from literature.scripts.parse import read_frontmatter, is_summary_stale
    from literature.scripts.rebuild_index import _find_literature_root

    lit_root = _find_literature_root(root)
    db = get_db(root)

    papers = db.execute(
        "SELECT paper_id, title, abstract, pagerank_score FROM papers ORDER BY pagerank_score DESC"
    ).fetchall()

    queue = []
    for paper in papers:
        paper_path = lit_root / "papers" / f"{paper['paper_id']}.md"
        if not paper_path.exists():
            continue
        meta, _ = read_frontmatter(paper_path)
        needs_l4 = is_summary_stale(meta, "l4")
        needs_l2 = is_summary_stale(meta, "l2")

        if level == "l4" and needs_l4:
            queue.append({
                "paper_id": paper["paper_id"],
                "title": paper["title"],
                "abstract": paper["abstract"] or "",
                "needs_l4": needs_l4,
                "needs_l2": needs_l2,
                "pagerank_score": paper["pagerank_score"],
            })
        elif level == "l2" and needs_l2:
            queue.append({
                "paper_id": paper["paper_id"],
                "title": paper["title"],
                "abstract": paper["abstract"] or "",
                "needs_l4": needs_l4,
                "needs_l2": needs_l2,
                "pagerank_score": paper["pagerank_score"],
            })
        elif level == "all" and (needs_l4 or needs_l2):
            queue.append({
                "paper_id": paper["paper_id"],
                "title": paper["title"],
                "abstract": paper["abstract"] or "",
                "needs_l4": needs_l4,
                "needs_l2": needs_l2,
                "pagerank_score": paper["pagerank_score"],
            })

    return queue


def mark_ingested(
    citekey: str,
    root: Path,
    level: str,
    content: str | list[str],
    model_name: str,
) -> None:
    """Write agent-generated summary to paper frontmatter with provenance.

    This function modifies the paper's .md file directly. Run ``lit rebuild``
    afterward to sync the updated frontmatter into the SQLite index.

    Args:
        citekey: Paper citekey (e.g. 'vaswani2017attention').
        root: Path hint for the literature directory.
        level: 'l4' (string) or 'l2' (list of strings).
        content: For l4: single string. For l2: list of claim strings.
        model_name: LLM model that generated this (e.g. 'claude-opus-4-6').

    Raises:
        FileNotFoundError: If the paper .md file does not exist.
        ValueError: If level is not 'l4' or 'l2'.
    """
    from literature.scripts.parse import read_frontmatter, write_paper_file, set_summary
    from literature.scripts.rebuild_index import _find_literature_root

    lit_root = _find_literature_root(root)
    paper_path = lit_root / "papers" / f"{citekey}.md"
    if not paper_path.exists():
        raise FileNotFoundError(f"Paper not found: {paper_path}")

    meta, body = read_frontmatter(paper_path)
    set_summary(meta, level, content, model_name)
    write_paper_file(paper_path, meta, body)


def get_ingest_status(root: Path) -> dict:
    """Return summary of ingestion progress.

    Reads L4 and L2 summary counts from the SQLite index.

    Args:
        root: Path hint for the literature directory.

    Returns:
        Dict with keys:
            total       — total number of papers in the DB
            l4_done     — papers with non-empty L4 summaries
            l4_needed   — papers missing L4 summaries
            l2_done     — papers with non-empty L2 summaries
            l2_needed   — papers missing L2 summaries
    """
    from literature.scripts.db import get_db

    db = get_db(root)
    total = db.execute("SELECT COUNT(*) FROM papers").fetchone()[0]

    l4_done = db.execute(
        "SELECT COUNT(*) FROM papers WHERE summary_l4_text != '' AND summary_l4_text IS NOT NULL"
    ).fetchone()[0]
    l2_done = db.execute(
        "SELECT COUNT(*) FROM papers WHERE summary_l2_claims != '' AND summary_l2_claims IS NOT NULL AND summary_l2_claims != '[]'"
    ).fetchone()[0]

    return {
        "total": total,
        "l4_done": l4_done,
        "l4_needed": total - l4_done,
        "l2_done": l2_done,
        "l2_needed": total - l2_done,
    }
