"""Tests for literature.scripts.search — BM25 full-text search."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from literature.scripts.db import init_db, sync_from_markdown
from literature.scripts.lit import run
from literature.scripts.search import search, similar

REAL_PAPERS_DIR = Path(__file__).parent.parent / "papers"


# ── Fixtures ───────────────────────────────────────────────────────────────────


def _make_lit_root(tmp_path: Path) -> Path:
    lit_dir = tmp_path / "literature"
    (lit_dir / "papers").mkdir(parents=True)
    (lit_dir / "resources").mkdir()
    (lit_dir / "AGENTS.md").write_text("# Test")
    return lit_dir


@pytest.fixture
def populated_lit(tmp_path: Path) -> Path:
    """A literature root with all 17 real papers synced into SQLite."""
    lit_dir = _make_lit_root(tmp_path)
    for paper in sorted(REAL_PAPERS_DIR.glob("*.md")):
        shutil.copy(paper, lit_dir / "papers" / paper.name)
    db = init_db(lit_dir)
    sync_from_markdown(lit_dir, db)
    db.close()
    return lit_dir


# ── Basic search ───────────────────────────────────────────────────────────────


def test_search_returns_transformer_papers(populated_lit: Path) -> None:
    results = search("transformer attention", populated_lit, top_k=5)
    paper_ids = [r["paper_id"] for r in results]
    assert "vaswani2017attention" in paper_ids, (
        f"Expected vaswani2017attention in top-5; got {paper_ids}"
    )


def test_search_hyphenated_term(populated_lit: Path) -> None:
    results = search("self-attention", populated_lit)
    paper_ids = [r["paper_id"] for r in results]
    assert len(results) >= 1, f"Expected results for 'self-attention'; got {paper_ids}"
    assert "vaswani2017attention" in paper_ids, (
        f"Expected vaswani2017attention in results for 'self-attention'; got {paper_ids}"
    )


def test_search_lob_topic(populated_lit: Path) -> None:
    results = search("limit order book", populated_lit)
    assert len(results) >= 1, "Expected at least one LOB paper"
    paper_ids = [r["paper_id"] for r in results]
    lob_papers = {
        "gould2013limit", "nagy2025lob", "linna2025lobert", "wang2026difflob",
        "dwarakanath2024abides", "wheeler2024marketgpt",
    }
    overlap = lob_papers & set(paper_ids)
    assert overlap, f"Expected at least one LOB paper; got {paper_ids}"


def test_search_no_results_empty_list(populated_lit: Path) -> None:
    results = search("xyzzy_nonexistent_abc", populated_lit)
    assert results == [], f"Expected empty list; got {results}"


def test_search_returns_list_of_dicts(populated_lit: Path) -> None:
    results = search("attention", populated_lit, top_k=3)
    assert isinstance(results, list)
    for r in results:
        assert isinstance(r, dict)
        assert "paper_id" in r
        assert "title" in r
        assert "score" in r


def test_search_score_is_negative(populated_lit: Path) -> None:
    results = search("attention mechanism", populated_lit, top_k=5)
    assert results, "Expected non-empty results"
    for r in results:
        assert r["score"] < 0, f"Expected negative BM25 score; got {r['score']}"


def test_search_top_k_limit(populated_lit: Path) -> None:
    results = search("attention", populated_lit, top_k=3)
    assert len(results) <= 3, f"Expected at most 3 results; got {len(results)}"


def test_search_json_output(populated_lit: Path) -> None:
    results = search("transformer", populated_lit, top_k=5)
    serialized = json.dumps(results)
    decoded = json.loads(serialized)
    assert isinstance(decoded, list)


def test_search_empty_query_returns_empty(populated_lit: Path) -> None:
    results = search("", populated_lit)
    assert results == []


# ── Similar ────────────────────────────────────────────────────────────────────


def test_similar_excludes_self(populated_lit: Path) -> None:
    results = similar("vaswani2017attention", populated_lit)
    paper_ids = [r["paper_id"] for r in results]
    assert "vaswani2017attention" not in paper_ids, (
        "similar() must not include the target paper itself"
    )


def test_similar_returns_related_papers(populated_lit: Path) -> None:
    results = similar("devlin2019bert", populated_lit)
    assert len(results) >= 1, "Expected at least one similar paper to devlin2019bert"
    paper_ids = [r["paper_id"] for r in results]
    assert "vaswani2017attention" in paper_ids, (
        f"Expected vaswani2017attention in similar(devlin2019bert); got {paper_ids}"
    )


def test_similar_unknown_citekey_returns_empty(populated_lit: Path) -> None:
    results = similar("no_such_paper_xyz", populated_lit)
    assert results == []


# ── Relevance ordering ────────────────────────────────────────────────────────


def test_search_relevance_ordering(populated_lit: Path) -> None:
    results = search("attention transformer", populated_lit, top_k=10)
    assert results, "Expected non-empty results"
    scores = [r["score"] for r in results]
    assert scores == sorted(scores), (
        f"Results should be sorted by score ASC (most relevant first); got {scores}"
    )


# ── CLI integration ────────────────────────────────────────────────────────────


def test_lit_search_cli(populated_lit: Path, capsys) -> None:
    exit_code = run(["search", "transformer"], root=populated_lit)
    assert exit_code == 0
    captured = capsys.readouterr()
    assert captured.out.strip(), "Expected non-empty stdout from lit search"


def test_lit_search_cli_json(populated_lit: Path, capsys) -> None:
    exit_code = run(["--json", "search", "transformer"], root=populated_lit)
    assert exit_code == 0
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert isinstance(data, list)
    if data:
        assert "paper_id" in data[0]
        assert "title" in data[0]
        assert "score" in data[0]


def test_lit_search_no_results_cli(populated_lit: Path, capsys) -> None:
    exit_code = run(["search", "xyzzy_nonexistent_abc_999"], root=populated_lit)
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "No results found" in captured.out
