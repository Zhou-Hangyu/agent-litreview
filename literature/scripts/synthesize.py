"""Multi-stage funnel retrieval engine for cross-paper synthesis.

Provides the ``funnel_retrieve()`` function that powers ``lit ask``.
The agent does the reasoning; this module does the retrieval.

Stage 1 (depth>=1): BM25 top-N candidates with L4 oneliners
Stage 2 (depth>=2): Abstract + TLDR for top-10 candidates
Stage 3 (depth>=3): L2 key claims for top-3 candidates
Stage 4 (depth>=4): Full abstract + notes body for top-1 candidate

Usage:
    from literature.scripts.synthesize import funnel_retrieve, format_funnel_output
    from pathlib import Path

    result = funnel_retrieve("limit order book simulation", Path("literature"), depth=3)
    print(format_funnel_output(result))
"""

from __future__ import annotations

import json
from pathlib import Path



def funnel_retrieve(
    question: str,
    root: Path,
    *,
    depth: int = 2,
    top_k_stage1: int = 50,
) -> dict:
    """Retrieve papers using multi-stage funnel for cross-paper synthesis.

    The agent does the reasoning; this function does the retrieval.
    No LLM is called — only SQLite BM25 + record fetches.

    Args:
        question: Research question to answer from the literature.
        root: Path to the ``literature/`` directory (or any ancestor).
        depth: Funnel depth controlling how much detail is returned:
            - 1: Stage 1 only — BM25 top candidates with L4 oneliners
            - 2: Stages 1-2 — adds abstract + TLDR for top-10
            - 3: Stages 1-3 — adds L2 key claims for top-3
            - 4: Stages 1-4 — adds full abstract + notes for top-1
        top_k_stage1: Number of BM25 candidates to retrieve (default: 50).

    Returns:
        Dict with keys:
        - ``question``: the original question
        - ``depth``: depth used
        - ``candidates``: list of {paper_id, title, year, bm25_score, l4_summary,
          reading_status} — from BM25 (stage 1)
        - ``shortlist``: list of {paper_id, title, year, abstract, tldr} — top-10
          candidates with abstract details (stage 2)
        - ``details``: list of {paper_id, title, l2_claims} — top-3 with key claims
          (stage 3)
        - ``deep``: list of {paper_id, title, abstract, notes} — top-1 with full text
          (stage 4)
    """
    from literature.scripts.search import search
    from literature.scripts.db import get_db

    result: dict = {
        "question": question,
        "depth": depth,
        "candidates": [],
        "shortlist": [],
        "details": [],
        "deep": [],
    }

    if not question or not question.strip():
        return result

    # Stage 1: BM25 search → candidates with L4 oneliners
    bm25_results = search(question, root, top_k=top_k_stage1)

    conn = get_db(root)
    try:
        for r in bm25_results:
            paper = conn.execute(
                "SELECT * FROM papers WHERE paper_id = ?",
                (r["paper_id"],),
            ).fetchone()
            if not paper:
                continue
            # L4 if available, fall back to tldr
            l4_summary = paper["summary_l4_text"] or paper["tldr"] or ""
            result["candidates"].append({
                "paper_id": r["paper_id"],
                "title": r["title"],
                "year": r.get("year"),
                "bm25_score": r.get("score", 0),
                "l4_summary": l4_summary,
                "reading_status": r.get("reading_status", "unread"),
            })

        if depth < 2:
            return result

        # Stage 2: Load abstract + tldr for top-10
        for candidate in result["candidates"][:10]:
            paper = conn.execute(
                "SELECT * FROM papers WHERE paper_id = ?",
                (candidate["paper_id"],),
            ).fetchone()
            if paper:
                result["shortlist"].append({
                    "paper_id": candidate["paper_id"],
                    "title": candidate["title"],
                    "year": candidate["year"],
                    "abstract": (paper["abstract"] or "")[:600],
                    "tldr": paper["tldr"] or "",
                })

        if depth < 3:
            return result

        # Stage 3: Load L2 key claims for top-3
        for candidate in result["candidates"][:3]:
            paper = conn.execute(
                "SELECT * FROM papers WHERE paper_id = ?",
                (candidate["paper_id"],),
            ).fetchone()
            if paper:
                l2_raw = paper["summary_l2_claims"] or "[]"
                try:
                    claims = json.loads(l2_raw)
                except (json.JSONDecodeError, TypeError):
                    claims = []
                result["details"].append({
                    "paper_id": candidate["paper_id"],
                    "title": candidate["title"],
                    "l2_claims": claims,
                })

        if depth < 4:
            return result

        # Stage 4: Full abstract + notes for top-1
        if result["candidates"]:
            top_paper = result["candidates"][0]
            paper = conn.execute(
                "SELECT * FROM papers WHERE paper_id = ?",
                (top_paper["paper_id"],),
            ).fetchone()
            if paper:
                notes = _load_paper_notes(top_paper["paper_id"], root)
                result["deep"].append({
                    "paper_id": top_paper["paper_id"],
                    "title": top_paper["title"],
                    "abstract": paper["abstract"] or "",
                    "notes": notes,
                })

    finally:
        conn.close()

    return result


def _load_paper_notes(paper_id: str, root: Path, max_chars: int = 1500) -> str:
    """Load the markdown body (notes) of a paper from its .md file.

    Args:
        paper_id: The citekey / paper_id (without .md extension).
        root: Path to the literature/ directory (or ancestor).
        max_chars: Maximum characters of notes to return.

    Returns:
        First ``max_chars`` characters of the notes body, or empty string if
        the file is not found or has no body.
    """
    try:
        from literature.scripts.rebuild_index import _find_literature_root
        from literature.scripts.parse import read_frontmatter

        lit_root = _find_literature_root(root)
        paper_path = lit_root / "papers" / f"{paper_id}.md"
        if not paper_path.exists():
            return ""
        _, body = read_frontmatter(paper_path)
        return (body or "")[:max_chars]
    except Exception:
        return ""


def format_funnel_output(result: dict) -> str:
    """Format funnel results for human-readable output (agent consumption).

    Args:
        result: Dict returned by :func:`funnel_retrieve`.

    Returns:
        Multi-line markdown string suitable for display or agent ingestion.
    """
    lines: list[str] = [f"## Research Query: {result['question']}", ""]

    candidates = result.get("candidates", [])
    if not candidates:
        return f"No relevant papers found for: {result['question']}"

    lines.append(f"### Stage 1 — {len(candidates)} candidates found\n")
    for c in candidates:
        l4 = c.get("l4_summary", "")
        l4_display = f" — {l4[:100]}" if l4 else " — (no summary yet)"
        lines.append(f"- **{c['paper_id']}** ({c['year']}){l4_display}")

    if result.get("shortlist"):
        lines.append(f"\n### Stage 2 — Top {len(result['shortlist'])} abstracts\n")
        for s in result["shortlist"]:
            abstract_preview = s.get("abstract", "")[:200]
            lines.append(f"**{s['paper_id']}** — {abstract_preview}...")

    if result.get("details"):
        lines.append(f"\n### Stage 3 — Key claims from top {len(result['details'])} papers\n")
        for d in result["details"]:
            lines.append(f"**{d['paper_id']}**:")
            for claim in d.get("l2_claims", []):
                lines.append(f"  - {claim}")
            if not d.get("l2_claims"):
                lines.append("  (no key claims extracted yet)")

    if result.get("deep"):
        lines.append("\n### Stage 4 — Full detail: top paper\n")
        deep = result["deep"][0]
        lines.append(f"**{deep['paper_id']}**\n")
        lines.append(f"Abstract: {deep['abstract'][:500]}\n")
        if deep.get("notes"):
            lines.append(f"Notes: {deep['notes'][:500]}")

    return "\n".join(lines)
