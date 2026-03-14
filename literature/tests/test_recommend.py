"""Tests for literature.scripts.recommend — 4-signal reading queue engine."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from literature.scripts.db import close_db, init_db
from literature.scripts.recommend import recommend_next, _score_recency


def _lit_root(tmp_path: Path) -> Path:
    root = tmp_path / "literature"
    (root / "AGENTS.md").parent.mkdir(parents=True)
    (root / "AGENTS.md").write_text("# AGENTS", encoding="utf-8")
    (root / "papers").mkdir()
    (root / "index").mkdir()
    return root


def _insert_paper(
    db: sqlite3.Connection,
    paper_id: str,
    *,
    year: int = 2020,
    status: str = "unread",
    pagerank: float = 0.1,
    abstract: str = "",
    title: str = "",
) -> None:
    db.execute(
        "INSERT OR REPLACE INTO papers "
        "(paper_id, title, year, reading_status_global, pagerank_score, abstract) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (paper_id, title or f"Title {paper_id}", year, status, pagerank, abstract),
    )
    db.commit()


def _insert_citation(db: sqlite3.Connection, citing: str, cited: str) -> None:
    db.execute(
        "INSERT OR IGNORE INTO citations (citing_id, cited_id, edge_type) VALUES (?, ?, 'cites')",
        (citing, cited),
    )
    db.commit()


class TestRecommendReturnTypes:

    def test_recommend_returns_list(self, tmp_path):
        root = _lit_root(tmp_path)
        db = init_db(root)
        _insert_paper(db, "paper_a")
        close_db(db)

        results = recommend_next(root)
        assert isinstance(results, list)

    def test_recommend_top_k_limit(self, tmp_path):
        root = _lit_root(tmp_path)
        db = init_db(root)
        for i in range(10):
            _insert_paper(db, f"paper_{i}")
        close_db(db)

        results = recommend_next(root, top_k=3)
        assert len(results) <= 3

    def test_recommend_has_score_breakdown(self, tmp_path):
        root = _lit_root(tmp_path)
        db = init_db(root)
        _insert_paper(db, "paper_a")
        close_db(db)

        results = recommend_next(root)
        assert len(results) >= 1
        for r in results:
            assert "score_breakdown" in r
            bd = r["score_breakdown"]
            assert "project_relevance" in bd
            assert "co_citation" in bd
            assert "recency" in bd
            assert "pagerank" in bd

    def test_recommend_scores_nonnegative(self, tmp_path):
        root = _lit_root(tmp_path)
        db = init_db(root)
        for i in range(5):
            _insert_paper(db, f"paper_{i}", year=2000 + i)
        close_db(db)

        results = recommend_next(root)
        for r in results:
            assert r["score"] >= 0.0, f"{r['paper_id']} has negative score {r['score']}"

    def test_recommend_sorted_by_score(self, tmp_path):
        root = _lit_root(tmp_path)
        db = init_db(root)
        for i in range(5):
            _insert_paper(db, f"paper_{i}", pagerank=0.1 * i)
        close_db(db)

        results = recommend_next(root)
        scores = [r["score"] for r in results]
        assert scores == sorted(scores, reverse=True)


class TestRecommendFiltering:

    def test_recommend_excludes_read_papers(self, tmp_path):
        root = _lit_root(tmp_path)
        db = init_db(root)
        _insert_paper(db, "read_paper", status="read")
        _insert_paper(db, "unread_paper", status="unread")
        close_db(db)

        results = recommend_next(root)
        ids = {r["paper_id"] for r in results}
        assert "read_paper" not in ids
        assert "unread_paper" in ids

    def test_recommend_excludes_synthesized(self, tmp_path):
        root = _lit_root(tmp_path)
        db = init_db(root)
        _insert_paper(db, "synth_paper", status="synthesized")
        _insert_paper(db, "unread_paper", status="unread")
        close_db(db)

        results = recommend_next(root)
        ids = {r["paper_id"] for r in results}
        assert "synth_paper" not in ids
        assert "unread_paper" in ids


class TestColdStart:

    def test_recommend_cold_start_no_purpose(self, tmp_path):
        root = _lit_root(tmp_path)
        # No PURPOSE.md written — cold start
        db = init_db(root)
        _insert_paper(db, "paper_a", pagerank=0.5)
        close_db(db)

        results = recommend_next(root)
        assert isinstance(results, list)
        for r in results:
            assert r["score_breakdown"]["project_relevance"] == 0.0

    def test_recommend_cold_start_no_reads(self, tmp_path):
        root = _lit_root(tmp_path)
        db = init_db(root)
        _insert_paper(db, "paper_a", status="unread")
        _insert_paper(db, "paper_b", status="unread")
        close_db(db)

        results = recommend_next(root)
        assert isinstance(results, list)
        for r in results:
            assert r["score_breakdown"]["co_citation"] == 0.0


class TestRecencySignal:

    def test_recency_newer_scores_higher(self, tmp_path):
        root = _lit_root(tmp_path)
        db = init_db(root)

        class _Row:
            def __init__(self, year):
                self._year = year
            def __getitem__(self, key):
                return self._year if key == "year" else None

        recent = _Row(2025)
        old = _Row(2000)
        assert _score_recency(recent) > _score_recency(old)


class TestCLIIntegration:

    def test_recommend_cli_json(self, tmp_path, capsys):
        root = _lit_root(tmp_path)
        db = init_db(root)
        _insert_paper(db, "paper_a", pagerank=0.3)
        _insert_paper(db, "paper_b", pagerank=0.1)
        close_db(db)

        from literature.scripts.lit import run

        exit_code = run(["--json", "recommend"], root=root)
        assert exit_code == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert isinstance(data, list)
        assert len(data) >= 1
        assert "paper_id" in data[0]
        assert "score" in data[0]
        assert "score_breakdown" in data[0]

    def test_recommend_cli_next_n(self, tmp_path, capsys):
        root = _lit_root(tmp_path)
        db = init_db(root)
        for i in range(10):
            _insert_paper(db, f"paper_{i}", pagerank=0.01 * i)
        close_db(db)

        from literature.scripts.lit import run

        exit_code = run(["--json", "recommend", "3"], root=root)
        assert exit_code == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert len(data) <= 3
