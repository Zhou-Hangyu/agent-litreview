"""Tests for literature.scripts.discover — paper discovery pipeline."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import responses as responses_lib

from literature.scripts.db import init_db
from literature.scripts.discover import (
    ARXIV_RSS_BASE,
    _parse_arxiv_rss,
    _score_relevance,
    discover_arxiv,
    discover_s2,
    get_inbox,
)
from literature.scripts.s2_client import S2_RECS_BASE


# ── Helpers ───────────────────────────────────────────────────────────────────


def _insert_paper(db, paper_id, s2_id="", arxiv_id="", pagerank=0.0):
    db.execute(
        "INSERT INTO papers (paper_id, title, s2_id, arxiv_id, pagerank_score) "
        "VALUES (?, ?, ?, ?, ?)",
        (paper_id, f"Paper {paper_id}", s2_id, arxiv_id, pagerank),
    )
    db.commit()


def _make_s2_rec(paper_id, title, arxiv_id="", abstract="Test abstract"):
    rec = {
        "paperId": paper_id,
        "title": title,
        "abstract": abstract,
        "externalIds": {},
    }
    if arxiv_id:
        rec["externalIds"]["ArXiv"] = arxiv_id
    return rec


def _make_atom_feed(entries):
    items = []
    for e in entries:
        items.append(
            f"<entry>"
            f"<title>{e['title']}</title>"
            f"<summary>{e.get('abstract', '')}</summary>"
            f'<link href="https://arxiv.org/abs/{e["arxiv_id"]}" rel="alternate"/>'
            f"<id>https://arxiv.org/abs/{e['arxiv_id']}</id>"
            f"</entry>"
        )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<feed xmlns="http://www.w3.org/2005/Atom">'
        "<title>Test</title>"
        f"{''.join(items)}"
        "</feed>"
    )


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture()
def lit_root(tmp_path: Path) -> Path:
    root = tmp_path / "literature"
    (root / "papers").mkdir(parents=True)
    (root / "index").mkdir(parents=True)
    (root / "AGENTS.md").write_text("# AGENTS", encoding="utf-8")
    return root


# ── Tests: _parse_arxiv_rss ───────────────────────────────────────────────────


def test_parse_arxiv_rss_extracts_fields():
    xml = _make_atom_feed([
        {"title": "Paper One", "abstract": "Abstract one", "arxiv_id": "2301.00001"},
        {"title": "Paper Two", "abstract": "Abstract two", "arxiv_id": "2301.00002"},
    ])
    results = _parse_arxiv_rss(xml)

    assert len(results) == 2
    assert results[0]["title"] == "Paper One"
    assert results[0]["abstract"] == "Abstract one"
    assert results[0]["arxiv_id"] == "2301.00001"
    assert "2301.00001" in results[0]["url"]
    assert results[1]["title"] == "Paper Two"
    assert results[1]["arxiv_id"] == "2301.00002"


def test_parse_arxiv_rss_handles_empty_feed():
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<feed xmlns="http://www.w3.org/2005/Atom">'
        "<title>Empty</title>"
        "</feed>"
    )
    assert _parse_arxiv_rss(xml) == []


# ── Tests: _score_relevance ──────────────────────────────────────────────────


def test_score_relevance_basic():
    keywords = ["transformer", "attention", "finance"]
    assert _score_relevance("Transformer Attention Model", "", keywords) == pytest.approx(2 / 3)
    assert _score_relevance("Transformer attention in finance", "", keywords) == pytest.approx(1.0)
    assert _score_relevance("Unrelated paper", "", keywords) == pytest.approx(0.0)


def test_score_relevance_empty_keywords():
    assert _score_relevance("Any title", "Any abstract", []) == 0.0


# ── Tests: discover_s2 ───────────────────────────────────────────────────────


def test_discover_s2_no_anchors_returns_empty(lit_root):
    init_db(lit_root)
    result = discover_s2(lit_root)
    assert result == []


@responses_lib.activate
def test_discover_s2_filters_known_papers(lit_root):
    db = init_db(lit_root)

    _insert_paper(db, "anchor1", s2_id="anchor_s2_1", pagerank=1.0)
    _insert_paper(db, "known1", s2_id="known_s2_1")
    _insert_paper(db, "known2", s2_id="known_s2_2")

    recs = [
        _make_s2_rec("known_s2_1", "Known Paper 1"),
        _make_s2_rec("known_s2_2", "Known Paper 2"),
        _make_s2_rec("new_s2_1", "New Paper 1"),
        _make_s2_rec("new_s2_2", "New Paper 2"),
        _make_s2_rec("new_s2_3", "New Paper 3"),
    ]

    responses_lib.add(
        responses_lib.GET,
        f"{S2_RECS_BASE}/papers/forpaper/anchor_s2_1",
        json={"recommendedPapers": recs},
        status=200,
    )

    result = discover_s2(lit_root, limit=20)

    assert len(result) == 3
    paper_ids = {r["paper_id"] for r in result}
    assert "new_s2_1" in paper_ids
    assert "new_s2_2" in paper_ids
    assert "new_s2_3" in paper_ids
    assert "known_s2_1" not in paper_ids

    inbox = get_inbox(lit_root)
    assert len(inbox) == 3


@responses_lib.activate
def test_discover_s2_deduplicates_s2_id(lit_root):
    db = init_db(lit_root)

    _insert_paper(db, "anchor1", s2_id="anchor_s2_1", pagerank=1.0)
    _insert_paper(db, "anchor2", s2_id="anchor_s2_2", pagerank=0.9)

    dup_rec = _make_s2_rec("dup_s2_1", "Duplicate Paper")

    responses_lib.add(
        responses_lib.GET,
        f"{S2_RECS_BASE}/papers/forpaper/anchor_s2_1",
        json={"recommendedPapers": [dup_rec]},
        status=200,
    )
    responses_lib.add(
        responses_lib.GET,
        f"{S2_RECS_BASE}/papers/forpaper/anchor_s2_2",
        json={"recommendedPapers": [dup_rec]},
        status=200,
    )

    result = discover_s2(lit_root, limit=20)

    assert len(result) == 1
    assert result[0]["paper_id"] == "dup_s2_1"

    inbox = get_inbox(lit_root)
    assert len(inbox) == 1


# ── Tests: discover_arxiv ────────────────────────────────────────────────────


@responses_lib.activate
def test_discover_arxiv_deduplicates_arxiv_id(lit_root):
    init_db(lit_root)

    feed_cs = _make_atom_feed([
        {"title": "Cross-Listed Paper", "abstract": "ML meets finance", "arxiv_id": "2301.99999"},
        {"title": "CS Only Paper", "abstract": "Pure CS", "arxiv_id": "2301.11111"},
    ])
    feed_qfin = _make_atom_feed([
        {"title": "Cross-Listed Paper", "abstract": "ML meets finance", "arxiv_id": "2301.99999"},
        {"title": "Finance Only", "abstract": "Pure finance", "arxiv_id": "2301.22222"},
    ])

    responses_lib.add(
        responses_lib.GET,
        f"{ARXIV_RSS_BASE}/cs.LG",
        body=feed_cs,
        status=200,
    )
    responses_lib.add(
        responses_lib.GET,
        f"{ARXIV_RSS_BASE}/q-fin.TR",
        body=feed_qfin,
        status=200,
    )

    result = discover_arxiv(lit_root, ["cs.LG", "q-fin.TR"], limit=50)

    arxiv_ids = {r["paper_id"] for r in result}
    assert len(arxiv_ids) == 3
    assert "2301.99999" in arxiv_ids
    assert "2301.11111" in arxiv_ids
    assert "2301.22222" in arxiv_ids


@responses_lib.activate
def test_discover_arxiv_filters_known(lit_root):
    db = init_db(lit_root)
    _insert_paper(db, "known_paper", arxiv_id="2301.00001")

    feed = _make_atom_feed([
        {"title": "Known Paper", "abstract": "Already in DB", "arxiv_id": "2301.00001"},
        {"title": "New Paper", "abstract": "Not in DB", "arxiv_id": "2301.00002"},
    ])

    responses_lib.add(
        responses_lib.GET,
        f"{ARXIV_RSS_BASE}/cs.LG",
        body=feed,
        status=200,
    )

    result = discover_arxiv(lit_root, ["cs.LG"], limit=50)

    assert len(result) == 1
    assert result[0]["paper_id"] == "2301.00002"


@responses_lib.activate
def test_discover_arxiv_invalid_category_doesnt_crash(lit_root):
    init_db(lit_root)

    responses_lib.add(
        responses_lib.GET,
        f"{ARXIV_RSS_BASE}/invalid.cat",
        body="Not Found",
        status=404,
    )

    result = discover_arxiv(lit_root, ["invalid.cat"], limit=50)
    assert result == []


# ── Tests: get_inbox ──────────────────────────────────────────────────────────


def test_get_inbox_returns_pending(lit_root):
    db = init_db(lit_root)

    db.execute(
        "INSERT INTO discovery_inbox "
        "(paper_id, title, abstract, source, relevance_score, discovered_at, status, raw_json) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("p1", "Paper 1", "Abstract 1", "s2_recommend", 0.5, "2026-01-01", "pending", "{}"),
    )
    db.execute(
        "INSERT INTO discovery_inbox "
        "(paper_id, title, abstract, source, relevance_score, discovered_at, status, raw_json) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("p2", "Paper 2", "Abstract 2", "arxiv_rss", 0.8, "2026-01-02", "pending", "{}"),
    )
    db.commit()

    items = get_inbox(lit_root)
    assert len(items) == 2
    assert items[0]["paper_id"] == "p2"  # higher relevance first
    assert items[1]["paper_id"] == "p1"


def test_get_inbox_filters_by_status(lit_root):
    db = init_db(lit_root)

    db.execute(
        "INSERT INTO discovery_inbox "
        "(paper_id, title, abstract, source, relevance_score, discovered_at, status, raw_json) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("p1", "Pending Paper", "Abs", "s2_recommend", 0.5, "2026-01-01", "pending", "{}"),
    )
    db.execute(
        "INSERT INTO discovery_inbox "
        "(paper_id, title, abstract, source, relevance_score, discovered_at, status, raw_json) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("p2", "Added Paper", "Abs", "s2_recommend", 0.8, "2026-01-02", "added", "{}"),
    )
    db.commit()

    items_pending = get_inbox(lit_root, status="pending")
    assert len(items_pending) == 1
    assert items_pending[0]["paper_id"] == "p1"

    items_added = get_inbox(lit_root, status="added")
    assert len(items_added) == 1
    assert items_added[0]["paper_id"] == "p2"
