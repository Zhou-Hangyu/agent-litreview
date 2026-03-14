"""Tests for literature.scripts.synthesize — funnel retrieval engine."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from literature.scripts.db import init_db, sync_from_markdown
from literature.scripts.lit import run
from literature.scripts.synthesize import format_funnel_output, funnel_retrieve

REAL_PAPERS_DIR = Path(__file__).parent.parent / "papers"


def _make_lit_root(tmp_path: Path) -> Path:
    lit_dir = tmp_path / "literature"
    (lit_dir / "papers").mkdir(parents=True)
    (lit_dir / "resources").mkdir()
    (lit_dir / "AGENTS.md").write_text("# Test")
    return lit_dir


@pytest.fixture
def populated_lit(tmp_path: Path) -> Path:
    lit_dir = _make_lit_root(tmp_path)
    for paper in sorted(REAL_PAPERS_DIR.glob("*.md")):
        shutil.copy(paper, lit_dir / "papers" / paper.name)
    db = init_db(lit_dir)
    sync_from_markdown(lit_dir, db)
    db.close()
    return lit_dir


@pytest.fixture
def empty_lit(tmp_path: Path) -> Path:
    lit_dir = _make_lit_root(tmp_path)
    db = init_db(lit_dir)
    db.close()
    return lit_dir


class TestFunnelDepth1:
    def test_funnel_depth1_returns_candidates_only(self, populated_lit: Path) -> None:
        result = funnel_retrieve("transformer attention", populated_lit, depth=1)
        assert len(result["candidates"]) > 0, "Expected candidates for 'transformer attention'"
        assert result["shortlist"] == [], "depth=1 should have empty shortlist"
        assert result["details"] == [], "depth=1 should have empty details"
        assert result["deep"] == [], "depth=1 should have empty deep"

    def test_funnel_depth1_uses_top_k(self, populated_lit: Path) -> None:
        result_small = funnel_retrieve("attention", populated_lit, depth=1, top_k_stage1=3)
        result_large = funnel_retrieve("attention", populated_lit, depth=1, top_k_stage1=20)
        assert len(result_small["candidates"]) <= 3
        assert len(result_large["candidates"]) <= 20


class TestFunnelDepth2:
    def test_funnel_depth2_returns_shortlist(self, populated_lit: Path) -> None:
        result = funnel_retrieve("transformer attention", populated_lit, depth=2)
        assert len(result["candidates"]) > 0
        assert len(result["shortlist"]) > 0, "depth=2 should have shortlist entries"
        assert len(result["shortlist"]) <= 10, "shortlist capped at 10"
        assert result["details"] == []
        assert result["deep"] == []

    def test_funnel_shortlist_has_abstract_key(self, populated_lit: Path) -> None:
        result = funnel_retrieve("limit order book", populated_lit, depth=2)
        for s in result["shortlist"]:
            assert "abstract" in s
            assert "tldr" in s
            assert isinstance(s["abstract"], str)


class TestFunnelDepth3:
    def test_funnel_depth3_returns_details(self, populated_lit: Path) -> None:
        result = funnel_retrieve("transformer attention", populated_lit, depth=3)
        assert len(result["candidates"]) > 0
        assert len(result["shortlist"]) > 0
        assert len(result["details"]) > 0, "depth=3 should have details entries"
        assert len(result["details"]) <= 3, "details capped at 3"
        assert result["deep"] == []

    def test_funnel_details_have_l2_claims_key(self, populated_lit: Path) -> None:
        result = funnel_retrieve("attention mechanism", populated_lit, depth=3)
        for d in result["details"]:
            assert "l2_claims" in d
            assert isinstance(d["l2_claims"], list)


class TestFunnelDepth4:
    def test_funnel_depth4_returns_deep(self, populated_lit: Path) -> None:
        result = funnel_retrieve("transformer attention", populated_lit, depth=4)
        assert len(result["candidates"]) > 0
        assert len(result["deep"]) == 1, "depth=4 should have exactly 1 deep entry"

    def test_funnel_deep_has_abstract_and_notes_keys(self, populated_lit: Path) -> None:
        result = funnel_retrieve("attention", populated_lit, depth=4)
        if result["deep"]:
            deep = result["deep"][0]
            assert "abstract" in deep
            assert "notes" in deep
            assert isinstance(deep["abstract"], str)
            assert isinstance(deep["notes"], str)


class TestFunnelEdgeCases:
    def test_funnel_no_results_empty_candidates(self, populated_lit: Path) -> None:
        result = funnel_retrieve("xyzzy_nonexistent_abc", populated_lit, depth=2)
        assert result["candidates"] == [], "Nonsense query should return no candidates"
        assert result["shortlist"] == []
        assert result["details"] == []
        assert result["deep"] == []

    def test_funnel_empty_corpus_returns_empty(self, empty_lit: Path) -> None:
        result = funnel_retrieve("transformer", empty_lit, depth=3)
        assert result["candidates"] == []
        assert result["shortlist"] == []

    def test_funnel_question_preserved_in_result(self, populated_lit: Path) -> None:
        question = "What approaches generate realistic LOB data?"
        result = funnel_retrieve(question, populated_lit, depth=1)
        assert result["question"] == question

    def test_funnel_depth_preserved_in_result(self, populated_lit: Path) -> None:
        result = funnel_retrieve("attention", populated_lit, depth=3)
        assert result["depth"] == 3

    def test_funnel_candidates_have_l4_summary_key(self, populated_lit: Path) -> None:
        result = funnel_retrieve("limit order book", populated_lit, depth=1)
        for c in result["candidates"]:
            assert "l4_summary" in c, f"Candidate {c.get('paper_id')} missing l4_summary"
            assert isinstance(c["l4_summary"], str)

    def test_funnel_result_is_json_serializable(self, populated_lit: Path) -> None:
        result = funnel_retrieve("transformer attention", populated_lit, depth=4)
        serialized = json.dumps(result, ensure_ascii=False)
        parsed = json.loads(serialized)
        assert parsed["question"] == result["question"]
        assert parsed["depth"] == result["depth"]


class TestFormatFunnelOutput:
    def test_format_no_candidates_returns_no_results_message(self) -> None:
        result = {
            "question": "What is xyzzy?",
            "depth": 2,
            "candidates": [],
            "shortlist": [],
            "details": [],
            "deep": [],
        }
        output = format_funnel_output(result)
        assert "No relevant papers found" in output
        assert "xyzzy" in output

    def test_format_with_candidates_includes_stage1_header(self) -> None:
        result = {
            "question": "transformers",
            "depth": 1,
            "candidates": [
                {"paper_id": "vaswani2017attention", "year": 2017, "l4_summary": "Attention is all you need"},
            ],
            "shortlist": [],
            "details": [],
            "deep": [],
        }
        output = format_funnel_output(result)
        assert "Stage 1" in output
        assert "vaswani2017attention" in output


class TestLitAskCLI:
    def test_lit_ask_cli_exits_zero(self, populated_lit: Path) -> None:
        exit_code = run(["ask", "transformers"], root=populated_lit)
        assert exit_code == 0

    def test_lit_ask_cli_json_parseable(self, populated_lit: Path, capsys) -> None:
        exit_code = run(["--json", "ask", "transformers"], root=populated_lit)
        assert exit_code == 0
        captured = capsys.readouterr()
        parsed = json.loads(captured.out)
        assert "question" in parsed
        assert "candidates" in parsed
        assert "shortlist" in parsed

    def test_lit_ask_empty_corpus_exits_zero(self, empty_lit: Path) -> None:
        exit_code = run(["ask", "transformers"], root=empty_lit)
        assert exit_code == 0

    def test_lit_ask_depth1_flag(self, populated_lit: Path, capsys) -> None:
        exit_code = run(["--json", "ask", "attention", "--depth", "1"], root=populated_lit)
        assert exit_code == 0
        captured = capsys.readouterr()
        parsed = json.loads(captured.out)
        assert parsed["depth"] == 1
        assert parsed["shortlist"] == []

    def test_lit_ask_depth4_flag(self, populated_lit: Path, capsys) -> None:
        exit_code = run(["--json", "ask", "limit order book", "--depth", "4"], root=populated_lit)
        assert exit_code == 0
        captured = capsys.readouterr()
        parsed = json.loads(captured.out)
        assert parsed["depth"] == 4
