from __future__ import annotations
"""Reading queue recommendation engine.

Zero dependencies. Pure Python stdlib only. Reads from DB directly.
"""

import math
import sqlite3
from datetime import datetime


def recommend(
    conn: sqlite3.Connection,
    top_k: int = 10,
    taste_keywords: list[str] | None = None,
) -> list[dict]:
    """Recommend papers to read next.

    Uses PageRank + recency scoring, optionally weighted by purpose keywords.

    Args:
        conn: Open database connection.
        top_k: Number of recommendations to return.
        taste_keywords: Optional list of keywords to boost relevance.

    Returns:
        List of paper dicts with added 'score' field, sorted descending.
    """
    papers = conn.execute(
        "SELECT id, title, year, status, abstract, tags, pagerank, pdf_path, summary_l4 "
        "FROM papers WHERE status NOT IN ('read', 'synthesized') ORDER BY pagerank DESC"
    ).fetchall()

    max_pr = max((p["pagerank"] or 0.0 for p in papers), default=0.0) or 1.0
    current_year = datetime.now().year

    scored = []
    for p in papers:
        # Recency: half-life of 3 years
        age = max(0, current_year - (p["year"] or 2000))
        recency = math.exp(-age * math.log(2) / 3.0)

        # PageRank signal (normalised)
        pr = (p["pagerank"] or 0.0) / max_pr

        # Purpose relevance (simple keyword match)
        relevance = 0.0
        if taste_keywords:
            text = f"{p['title']} {p['abstract']} {p['tags']}".lower()
            hits = sum(1 for kw in taste_keywords if kw in text)
            relevance = min(hits / max(len(taste_keywords), 1), 1.0)

        if taste_keywords:
            score = 0.40 * relevance + 0.30 * pr + 0.30 * recency
        else:
            score = 0.50 * pr + 0.50 * recency

        breakdown = {"relevance": relevance, "pagerank": pr, "recency": recency}
        scored.append({**dict(p), "score": score, "breakdown": breakdown})

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:top_k]
