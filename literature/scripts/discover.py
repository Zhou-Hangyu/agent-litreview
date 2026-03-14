#!/usr/bin/env python3
"""Paper discovery pipeline — S2 recommendations + arXiv RSS.

Provides functions to discover new papers via the Semantic Scholar
Recommendations API and arXiv RSS feeds, store them in the discovery_inbox
table, and manage the inbox.

Usage (via lit CLI)::

    lit discover --source s2
    lit discover --source arxiv --categories cs.LG,q-fin.TR
    lit discover                      # both sources
    lit inbox                         # show pending discoveries
    lit inbox add <id>                # add discovery to corpus
"""
from __future__ import annotations

import datetime
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any


import requests

from literature.scripts.db import init_db
from literature.scripts.purpose import extract_keywords, load_purpose

# ── Constants ─────────────────────────────────────────────────────────────────

ARXIV_RSS_BASE = "https://rss.arxiv.org/rss"

S2_REC_FIELDS = "title,abstract,externalIds"


# ── arXiv RSS parsing ─────────────────────────────────────────────────────────


def _parse_arxiv_rss(xml_text: str) -> list[dict]:
    """Parse arXiv Atom/RSS XML and extract paper entries.

    Handles both Atom (``<feed>/<entry>``) and RSS 2.0
    (``<rss>/<channel>/<item>``) formats.

    Args:
        xml_text: Raw XML string from arXiv RSS feed.

    Returns:
        List of dicts with keys: ``title``, ``abstract``, ``arxiv_id``,
        ``url``.
    """
    root_el = ET.fromstring(xml_text)
    ns = {"atom": "http://www.w3.org/2005/Atom"}

    # Try Atom format first, then bare elements, then RSS 2.0 <item>
    items = root_el.findall("atom:entry", ns)
    if not items:
        items = root_el.findall("entry")
    if not items:
        items = root_el.findall(".//item")

    entries: list[dict] = []
    for item in items:

        def _get_text(tag: str) -> str:
            el = item.find(f"atom:{tag}", ns)
            if el is None:
                el = item.find(tag)
            return (el.text or "").strip() if el is not None else ""

        title = _get_text("title")
        summary = _get_text("summary") or _get_text("description")

        # Resolve URL from <link> element
        link_el = item.find("atom:link[@rel='alternate']", ns)
        if link_el is None:
            link_el = item.find("atom:link", ns)
        if link_el is None:
            link_el = item.find("link")

        if link_el is not None:
            url = link_el.get("href", "") or (link_el.text or "").strip()
        else:
            url = _get_text("id")

        # Extract arXiv ID from URL
        arxiv_match = re.search(r"(\d{4}\.\d{4,5})", url)
        arxiv_id = arxiv_match.group(1) if arxiv_match else ""

        if title:
            entries.append(
                {
                    "title": title,
                    "abstract": summary[:500] if summary else "",
                    "arxiv_id": arxiv_id,
                    "url": url,
                }
            )

    return entries


# ── Relevance scoring ─────────────────────────────────────────────────────────


def _score_relevance(title: str, abstract: str, keywords: list[str]) -> float:
    """Score a paper's relevance against PURPOSE.md keywords.

    Returns a value between 0.0 and 1.0 representing the fraction of
    keywords that appear in the paper's title and abstract.
    """
    if not keywords:
        return 0.0
    text = (title + " " + abstract).lower()
    return sum(1 for kw in keywords if kw in text) / len(keywords)


# ── Discovery functions ───────────────────────────────────────────────────────


def discover_s2(root: Path, *, limit: int = 20) -> list[dict]:
    """Find new papers via S2 Recommendations API.

    Uses papers already in corpus with high PageRank as anchor seeds.
    Filters out papers already in corpus.
    Scores candidates against PURPOSE.md keywords.
    Stores results in discovery_inbox table.

    Args:
        root: Path to the ``literature/`` directory.
        limit: Maximum recommendations to request per anchor paper.

    Returns:
        List of newly discovered paper dicts.
    """
    from literature.scripts.s2_client import recommend_papers

    db = init_db(root)

    # Get anchor papers: top-3 by PageRank that have s2_id
    anchors = db.execute(
        "SELECT paper_id, s2_id FROM papers WHERE s2_id != '' "
        "ORDER BY pagerank_score DESC LIMIT 3"
    ).fetchall()

    if not anchors:
        return []

    # Get set of already-known IDs
    known_arxiv = {
        row["arxiv_id"]
        for row in db.execute("SELECT arxiv_id FROM papers WHERE arxiv_id != ''")
    }
    known_s2 = {
        row["s2_id"]
        for row in db.execute("SELECT s2_id FROM papers WHERE s2_id != ''")
    }

    # Get PURPOSE keywords for relevance scoring
    purpose_text = load_purpose(root)
    keywords = extract_keywords(purpose_text)

    newly_found: list[dict] = []
    seen_ids: set[str] = set()  # Track IDs seen in this run for dedup

    for anchor in anchors:
        try:
            recs = recommend_papers(
                anchor["s2_id"],
                fields=S2_REC_FIELDS,
                limit=limit,
            )
        except Exception:
            continue

        for rec in recs:
            s2_id = rec.get("paperId", "")
            if s2_id in known_s2 or s2_id in seen_ids:
                continue

            external = rec.get("externalIds") or {}
            arxiv_id = external.get("ArXiv", "")
            if arxiv_id and arxiv_id in known_arxiv:
                continue

            paper_id = s2_id or arxiv_id or (rec.get("title") or "")[:40]
            if not paper_id:
                continue

            # Check if already in inbox
            existing = db.execute(
                "SELECT 1 FROM discovery_inbox WHERE paper_id = ?",
                (paper_id,),
            ).fetchone()
            if existing:
                if s2_id:
                    seen_ids.add(s2_id)
                continue

            title = rec.get("title", "")
            abstract = (rec.get("abstract") or "")[:500]
            relevance = _score_relevance(title, abstract, keywords)
            now = datetime.datetime.now(datetime.timezone.utc).isoformat()

            entry = {
                "paper_id": paper_id,
                "title": title,
                "abstract": abstract,
                "source": "s2_recommend",
                "relevance_score": relevance,
                "discovered_at": now,
                "status": "pending",
                "raw_json": json.dumps(rec),
            }

            db.execute(
                "INSERT INTO discovery_inbox "
                "(paper_id, title, abstract, source, relevance_score, "
                "discovered_at, status, raw_json) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    paper_id,
                    title,
                    abstract,
                    "s2_recommend",
                    relevance,
                    now,
                    "pending",
                    json.dumps(rec),
                ),
            )
            db.commit()
            newly_found.append(entry)
            if s2_id:
                seen_ids.add(s2_id)
                known_s2.add(s2_id)

    return newly_found


def discover_arxiv(
    root: Path,
    categories: list[str],
    *,
    limit: int = 50,
) -> list[dict]:
    """Fetch arXiv RSS feeds and find new relevant papers.

    Parses Atom/RSS from ``https://rss.arxiv.org/rss/{category}``.
    Deduplicates by arXiv ID (handles cross-listed papers).
    Filters papers already in corpus by ``arxiv_id``.
    Scores against PURPOSE.md keywords.
    Stores in discovery_inbox.

    Args:
        root: Path to the ``literature/`` directory.
        categories: List of arXiv category strings (e.g. ``["cs.LG"]``).
        limit: Maximum number of new papers to store.

    Returns:
        List of newly discovered paper dicts.
    """
    db = init_db(root)

    # Get already-known arXiv IDs
    known_arxiv = {
        row["arxiv_id"]
        for row in db.execute("SELECT arxiv_id FROM papers WHERE arxiv_id != ''")
    }

    # Get PURPOSE keywords
    purpose_text = load_purpose(root)
    keywords = extract_keywords(purpose_text)

    # Fetch and parse RSS for each category, dedup by arXiv ID
    all_entries: dict[str, dict] = {}  # arxiv_id → entry

    for category in categories:
        url = f"{ARXIV_RSS_BASE}/{category.strip()}"
        try:
            resp = requests.get(url, timeout=15)
            if resp.status_code != 200:
                continue
            parsed = _parse_arxiv_rss(resp.text)
        except Exception:
            continue

        for entry in parsed:
            arxiv_id = entry.get("arxiv_id", "")
            if not arxiv_id:
                continue
            # Deduplicate across categories (first occurrence wins)
            if arxiv_id not in all_entries:
                all_entries[arxiv_id] = entry

    # Filter known, score, and insert
    newly_found: list[dict] = []
    count = 0

    for arxiv_id, entry in all_entries.items():
        if count >= limit:
            break
        if arxiv_id in known_arxiv:
            continue

        # Check if already in inbox
        existing = db.execute(
            "SELECT 1 FROM discovery_inbox WHERE paper_id = ?",
            (arxiv_id,),
        ).fetchone()
        if existing:
            continue

        title = entry["title"]
        abstract = entry.get("abstract", "")
        relevance = _score_relevance(title, abstract, keywords)
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()

        result = {
            "paper_id": arxiv_id,
            "title": title,
            "abstract": abstract,
            "source": "arxiv_rss",
            "relevance_score": relevance,
            "discovered_at": now,
            "status": "pending",
            "raw_json": json.dumps(entry),
        }

        db.execute(
            "INSERT INTO discovery_inbox "
            "(paper_id, title, abstract, source, relevance_score, "
            "discovered_at, status, raw_json) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                arxiv_id,
                title,
                abstract,
                "arxiv_rss",
                relevance,
                now,
                "pending",
                json.dumps(entry),
            ),
        )
        db.commit()
        newly_found.append(result)
        count += 1

    return newly_found


# ── Inbox management ──────────────────────────────────────────────────────────


def get_inbox(root: Path, *, status: str = "pending") -> list[dict]:
    """Fetch discovery_inbox entries with given status.

    Args:
        root: Path to the ``literature/`` directory.
        status: Filter by status (default: ``"pending"``).

    Returns:
        List of dicts with inbox entry data, ordered by relevance descending.
    """
    db = init_db(root)
    rows = db.execute(
        "SELECT id, paper_id, title, abstract, source, relevance_score, "
        "discovered_at, status, raw_json FROM discovery_inbox "
        "WHERE status = ? ORDER BY relevance_score DESC",
        (status,),
    ).fetchall()

    return [
        {
            "id": row["id"],
            "paper_id": row["paper_id"],
            "title": row["title"],
            "abstract": row["abstract"],
            "source": row["source"],
            "relevance_score": row["relevance_score"],
            "discovered_at": row["discovered_at"],
            "status": row["status"],
            "raw_json": row["raw_json"],
        }
        for row in rows
    ]


def add_from_inbox(inbox_id: int, root: Path) -> str:
    """Add a discovered paper to corpus via enrich.py.

    Updates inbox row status to ``'added'``.

    Args:
        inbox_id: The ``id`` column of the discovery_inbox row.
        root: Path to the ``literature/`` directory.

    Returns:
        Citekey of the newly added paper.

    Raises:
        ValueError: If *inbox_id* not found.
        RuntimeError: If enrichment fails.
    """
    from literature.scripts.enrich import enrich_paper

    db = init_db(root)
    row = db.execute(
        "SELECT * FROM discovery_inbox WHERE id = ?", (inbox_id,)
    ).fetchone()

    if not row:
        raise ValueError(f"Inbox item {inbox_id} not found")

    # Determine best input string for enrich_paper
    raw = json.loads(row["raw_json"]) if row["raw_json"] else {}
    external = raw.get("externalIds") or {}
    arxiv_id = external.get("ArXiv", "")

    # Prefer arXiv ID, fall back to paper_id (S2 hex ID or other)
    input_str = arxiv_id if arxiv_id else row["paper_id"]

    paper_path = enrich_paper(input_str, root)
    citekey = paper_path.stem

    # Update inbox status
    db.execute(
        "UPDATE discovery_inbox SET status = 'added' WHERE id = ?",
        (inbox_id,),
    )
    db.commit()

    return citekey
