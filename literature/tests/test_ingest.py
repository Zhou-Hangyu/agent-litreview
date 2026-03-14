"""Tests for literature.scripts.ingest — progressive summarization queue manager."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from literature.scripts.db import init_db, sync_from_markdown
from literature.scripts.ingest import (
    get_ingest_queue,
    get_ingest_status,
    mark_ingested,
    needs_summary,
)
from literature.scripts.lit import run
from literature.scripts.pagerank import compute_pagerank, store_pagerank_scores
from literature.scripts.parse import read_frontmatter, write_paper_file


# ── Helpers ────────────────────────────────────────────────────────────────────


def _make_lit_root(tmp_path: Path) -> Path:
    """Create a minimal literature directory structure and return the lit root."""
    root = tmp_path / "literature"
    (root / "papers").mkdir(parents=True)
    (root / "resources").mkdir()
    (root / "index").mkdir()
    (root / "AGENTS.md").write_text("# AGENTS", encoding="utf-8")
    return root


_PAPER_TEMPLATE = """\
---
doc_id: "{doc_id}"
title: "{title}"
authors:
  - "Test, A."
year: 2024
resource_type: paper
reading_status:
  global: unread
tags: []
themes: []
cites: []
cited_by: []
citation_count: {citation_count}
influential_citation_count: 0
abstract: "{abstract}"
tldr: ""
---
"""


def _write_paper(
    lit_root: Path,
    doc_id: str,
    title: str = "Test Paper",
    abstract: str = "Test abstract.",
    citation_count: int = 0,
) -> Path:
    """Write a minimal paper file and return its path."""
    content = _PAPER_TEMPLATE.format(
        doc_id=doc_id,
        title=title,
        abstract=abstract,
        citation_count=citation_count,
    )
    p = lit_root / "papers" / f"{doc_id}.md"
    p.write_text(content, encoding="utf-8")
    return p


def _rebuild(lit_root: Path) -> None:
    """Sync papers into DB and compute PageRank."""
    conn = init_db(lit_root)
    sync_from_markdown(lit_root, conn)
    scores = compute_pagerank(conn)
    store_pagerank_scores(conn, scores)
    conn.close()


# ── needs_summary ──────────────────────────────────────────────────────────────


def test_needs_summary_true_when_missing(tmp_path: Path) -> None:
    """Paper without summaries → needs_summary returns True for l4."""
    lit_root = _make_lit_root(tmp_path)
    _write_paper(lit_root, "alpha2024test")
    assert needs_summary("alpha2024test", lit_root, "l4") is True


def test_needs_summary_false_when_fresh(tmp_path: Path) -> None:
    """Paper with just-written l4 → needs_summary returns False."""
    lit_root = _make_lit_root(tmp_path)
    _write_paper(lit_root, "beta2024test")
    # Mark it ingested first
    mark_ingested("beta2024test", lit_root, "l4", "Fresh summary text.", "test-model")
    assert needs_summary("beta2024test", lit_root, "l4") is False


def test_needs_summary_true_for_nonexistent_paper(tmp_path: Path) -> None:
    """Non-existent paper citekey → needs_summary returns True."""
    lit_root = _make_lit_root(tmp_path)
    assert needs_summary("does_not_exist", lit_root, "l4") is True


# ── get_ingest_queue ───────────────────────────────────────────────────────────


def test_get_ingest_queue_all_papers_initially(tmp_path: Path) -> None:
    """17 papers with no summaries → queue has all 17 items for l4."""
    lit_root = _make_lit_root(tmp_path)
    # Write 17 papers
    for i in range(17):
        _write_paper(lit_root, f"paper{i:02d}2024test", title=f"Paper {i}", citation_count=i)
    _rebuild(lit_root)

    queue = get_ingest_queue(lit_root, level="l4")
    assert len(queue) == 17


def test_get_ingest_queue_sorted_by_pagerank(tmp_path: Path) -> None:
    """Queue is sorted by PageRank descending (most important first)."""
    lit_root = _make_lit_root(tmp_path)
    # Create papers with citations: paper_b cites paper_a, giving paper_a higher PageRank
    content_a = """\
---
doc_id: "pa2024test"
title: "Paper A"
authors: ["Test, A."]
year: 2024
resource_type: paper
reading_status:
  global: unread
tags: []
themes: []
cites: []
cited_by: []
citation_count: 100
influential_citation_count: 0
abstract: "Abstract A."
tldr: ""
---
"""
    content_b = """\
---
doc_id: "pb2024test"
title: "Paper B"
authors: ["Test, B."]
year: 2024
resource_type: paper
reading_status:
  global: unread
tags: []
themes: []
cites:
  - id: pa2024test
    type: cites
cited_by: []
citation_count: 0
influential_citation_count: 0
abstract: "Abstract B."
tldr: ""
---
"""
    (lit_root / "papers" / "pa2024test.md").write_text(content_a, encoding="utf-8")
    (lit_root / "papers" / "pb2024test.md").write_text(content_b, encoding="utf-8")
    _rebuild(lit_root)

    queue = get_ingest_queue(lit_root, level="l4")
    assert len(queue) == 2
    # pa2024test (cited by pb) should have higher or equal pagerank — first in queue
    scores = {item["paper_id"]: item["pagerank_score"] for item in queue}
    # pa is cited, pb is not cited → pa should have >= pagerank
    assert scores["pa2024test"] >= scores["pb2024test"]
    # Verify queue is sorted descending
    pageranks = [item["pagerank_score"] for item in queue]
    assert pageranks == sorted(pageranks, reverse=True)


def test_get_ingest_queue_skips_summarized(tmp_path: Path) -> None:
    """Paper with fresh l4 summary → not in l4 queue."""
    lit_root = _make_lit_root(tmp_path)
    _write_paper(lit_root, "gamma2024test")
    _write_paper(lit_root, "delta2024test")
    _rebuild(lit_root)

    # Mark gamma as summarized
    mark_ingested("gamma2024test", lit_root, "l4", "Already summarized.", "test-model")

    queue = get_ingest_queue(lit_root, level="l4")
    paper_ids = [item["paper_id"] for item in queue]
    assert "gamma2024test" not in paper_ids
    assert "delta2024test" in paper_ids


def test_get_ingest_queue_level_l2(tmp_path: Path) -> None:
    """Level l2 queue returns papers needing L2 summaries."""
    lit_root = _make_lit_root(tmp_path)
    _write_paper(lit_root, "epsilon2024test")
    _rebuild(lit_root)

    queue_l2 = get_ingest_queue(lit_root, level="l2")
    assert len(queue_l2) == 1
    assert queue_l2[0]["paper_id"] == "epsilon2024test"
    assert queue_l2[0]["needs_l2"] is True


def test_get_ingest_queue_level_all(tmp_path: Path) -> None:
    """Level 'all' includes papers needing either l4 or l2."""
    lit_root = _make_lit_root(tmp_path)
    _write_paper(lit_root, "zeta2024test")
    _write_paper(lit_root, "eta2024test")
    _rebuild(lit_root)

    # Mark zeta l4 only
    mark_ingested("zeta2024test", lit_root, "l4", "L4 done.", "test-model")

    queue_all = get_ingest_queue(lit_root, level="all")
    paper_ids = [item["paper_id"] for item in queue_all]
    # zeta still needs l2 → should be in 'all' queue
    assert "zeta2024test" in paper_ids
    assert "eta2024test" in paper_ids


# ── mark_ingested ──────────────────────────────────────────────────────────────


def test_mark_ingested_l4_stores_text(tmp_path: Path) -> None:
    """mark_ingested for l4 → frontmatter has the summary text."""
    lit_root = _make_lit_root(tmp_path)
    _write_paper(lit_root, "theta2024test")

    mark_ingested("theta2024test", lit_root, "l4", "Transformer introduces self-attention.", "claude-opus-4-6")

    paper_path = lit_root / "papers" / "theta2024test.md"
    meta, _ = read_frontmatter(paper_path)
    assert meta["summaries"]["l4"]["text"] == "Transformer introduces self-attention."


def test_mark_ingested_l4_stores_model(tmp_path: Path) -> None:
    """mark_ingested → frontmatter has model name."""
    lit_root = _make_lit_root(tmp_path)
    _write_paper(lit_root, "iota2024test")

    mark_ingested("iota2024test", lit_root, "l4", "Some summary.", "claude-opus-4-6")

    paper_path = lit_root / "papers" / "iota2024test.md"
    meta, _ = read_frontmatter(paper_path)
    assert meta["summaries"]["l4"]["model"] == "claude-opus-4-6"


def test_mark_ingested_l4_stores_timestamp(tmp_path: Path) -> None:
    """mark_ingested → frontmatter has ISO 8601 timestamp."""
    lit_root = _make_lit_root(tmp_path)
    _write_paper(lit_root, "kappa2024test")

    mark_ingested("kappa2024test", lit_root, "l4", "Summary with timestamp.", "test-model")

    paper_path = lit_root / "papers" / "kappa2024test.md"
    meta, _ = read_frontmatter(paper_path)
    ts = meta["summaries"]["l4"]["generated_at"]
    assert ts.endswith("Z"), f"Expected ISO timestamp ending in Z, got: {ts!r}"
    assert "T" in ts, f"Expected ISO timestamp with T separator, got: {ts!r}"


def test_mark_ingested_l2_stores_claims_list(tmp_path: Path) -> None:
    """l2 with 3 claims → claims list stored in frontmatter."""
    lit_root = _make_lit_root(tmp_path)
    _write_paper(lit_root, "lambda2024test")

    claims = [
        "Self-attention replaces recurrence entirely.",
        "Multi-head attention enables parallel sequence processing.",
        "Position encodings inject sequence order information.",
    ]
    mark_ingested("lambda2024test", lit_root, "l2", claims, "claude-opus-4-6")

    paper_path = lit_root / "papers" / "lambda2024test.md"
    meta, _ = read_frontmatter(paper_path)
    stored_claims = meta["summaries"]["l2"]["claims"]
    assert stored_claims == claims
    assert len(stored_claims) == 3


def test_mark_ingested_nonexistent_raises(tmp_path: Path) -> None:
    """Non-existent citekey → FileNotFoundError."""
    lit_root = _make_lit_root(tmp_path)
    with pytest.raises(FileNotFoundError):
        mark_ingested("does_not_exist", lit_root, "l4", "Summary.", "test-model")


# ── get_ingest_status ──────────────────────────────────────────────────────────


def test_get_ingest_status_returns_counts(tmp_path: Path) -> None:
    """Status dict has total, l4_done, l4_needed keys with correct types."""
    lit_root = _make_lit_root(tmp_path)
    _write_paper(lit_root, "mu2024test")
    _write_paper(lit_root, "nu2024test")
    _rebuild(lit_root)

    status = get_ingest_status(lit_root)
    assert "total" in status
    assert "l4_done" in status
    assert "l4_needed" in status
    assert "l2_done" in status
    assert "l2_needed" in status
    assert status["total"] == 2
    assert status["l4_done"] == 0
    assert status["l4_needed"] == 2


# ── CLI integration ────────────────────────────────────────────────────────────


def test_ingest_cli_list(tmp_path: Path, capsys) -> None:
    """lit ingest --list → exit 0, shows papers needing summaries."""
    lit_root = _make_lit_root(tmp_path)
    _write_paper(lit_root, "xi2024test", title="Xi Test Paper")
    _rebuild(lit_root)

    exit_code = run(["ingest", "--list"], root=lit_root)
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "xi2024test" in captured.out or "1 paper" in captured.out


def test_ingest_cli_status(tmp_path: Path, capsys) -> None:
    """lit ingest --status → exit 0, shows L4/L2 counts."""
    lit_root = _make_lit_root(tmp_path)
    _write_paper(lit_root, "omicron2024test")
    _rebuild(lit_root)

    exit_code = run(["ingest", "--status"], root=lit_root)
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "L4" in captured.out or "l4" in captured.out.lower()
