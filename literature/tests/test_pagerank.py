"""Tests for literature.scripts.pagerank — PageRank and HITS algorithms."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from literature.scripts.db import close_db, init_db
from literature.scripts.pagerank import (
    compute_hits,
    compute_pagerank,
    store_pagerank_scores,
)


def _lit_root(tmp_path: Path) -> Path:
    root = tmp_path / "literature"
    (root / "AGENTS.md").parent.mkdir(parents=True)
    (root / "AGENTS.md").write_text("# AGENTS", encoding="utf-8")
    (root / "papers").mkdir()
    (root / "index").mkdir()
    return root


def _insert_papers(db: sqlite3.Connection, paper_ids: list[str]) -> None:
    for pid in paper_ids:
        db.execute(
            "INSERT OR IGNORE INTO papers (paper_id, title) VALUES (?, ?)",
            (pid, f"Title for {pid}"),
        )
    db.commit()


def _insert_edges(
    db: sqlite3.Connection, edges: list[tuple[str, str]]
) -> None:
    for citing, cited in edges:
        db.execute(
            "INSERT OR IGNORE INTO citations (citing_id, cited_id, edge_type) "
            "VALUES (?, ?, 'cites')",
            (citing, cited),
        )
    db.commit()


class TestPageRankKnownGraph:
    """4-node graph: A→B, A→C, B→C, D→C.  C should have highest score."""

    def test_c_has_highest_score(self, tmp_path: Path) -> None:
        root = _lit_root(tmp_path)
        conn = init_db(root)
        try:
            _insert_papers(conn, ["A", "B", "C", "D"])
            _insert_edges(conn, [("A", "B"), ("A", "C"), ("B", "C"), ("D", "C")])

            scores = compute_pagerank(conn)

            assert scores["C"] == max(scores.values())
        finally:
            close_db(conn)

    def test_all_scores_positive(self, tmp_path: Path) -> None:
        root = _lit_root(tmp_path)
        conn = init_db(root)
        try:
            _insert_papers(conn, ["A", "B", "C", "D"])
            _insert_edges(conn, [("A", "B"), ("A", "C"), ("B", "C"), ("D", "C")])

            scores = compute_pagerank(conn)

            assert all(s > 0 for s in scores.values())
        finally:
            close_db(conn)

    def test_scores_sum_to_one(self, tmp_path: Path) -> None:
        root = _lit_root(tmp_path)
        conn = init_db(root)
        try:
            _insert_papers(conn, ["A", "B", "C", "D"])
            _insert_edges(conn, [("A", "B"), ("A", "C"), ("B", "C"), ("D", "C")])

            scores = compute_pagerank(conn)

            assert abs(sum(scores.values()) - 1.0) < 0.01
        finally:
            close_db(conn)


class TestPageRankEdgeCases:

    def test_empty_graph(self, tmp_path: Path) -> None:
        root = _lit_root(tmp_path)
        conn = init_db(root)
        try:
            scores = compute_pagerank(conn)
            assert scores == {}
        finally:
            close_db(conn)

    def test_single_node_no_edges(self, tmp_path: Path) -> None:
        root = _lit_root(tmp_path)
        conn = init_db(root)
        try:
            _insert_papers(conn, ["solo"])
            scores = compute_pagerank(conn)
            assert abs(scores["solo"] - 1.0) < 0.01
        finally:
            close_db(conn)

    def test_no_negative_scores(self, tmp_path: Path) -> None:
        root = _lit_root(tmp_path)
        conn = init_db(root)
        try:
            _insert_papers(conn, ["X", "Y", "Z"])
            _insert_edges(conn, [("X", "Y"), ("Y", "Z"), ("Z", "X")])

            scores = compute_pagerank(conn)

            assert all(s >= 0 for s in scores.values())
        finally:
            close_db(conn)


class TestPageRankRealCollection:

    def test_scores_sum_to_one(self) -> None:
        conn = init_db(Path("literature"))
        try:
            scores = compute_pagerank(conn)
            assert len(scores) == 17, f"Expected 17 papers, got {len(scores)}"
            assert abs(sum(scores.values()) - 1.0) < 0.01
        finally:
            close_db(conn)

    def test_top_cited_in_top_3(self) -> None:
        conn = init_db(Path("literature"))
        try:
            scores = compute_pagerank(conn)
            ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
            top_3_ids = {pid for pid, _ in ranked[:3]}

            assert (
                "sirignano2018universal" in top_3_ids
                or "vaswani2017attention" in top_3_ids
            ), f"Expected sirignano or vaswani in top 3, got {top_3_ids}"
        finally:
            close_db(conn)


class TestStorePageRankScores:

    def test_scores_persisted(self, tmp_path: Path) -> None:
        root = _lit_root(tmp_path)
        conn = init_db(root)
        try:
            _insert_papers(conn, ["p1", "p2"])
            scores = {"p1": 0.7, "p2": 0.3}

            store_pagerank_scores(conn, scores)

            row = conn.execute(
                "SELECT pagerank_score FROM papers WHERE paper_id = 'p1'"
            ).fetchone()
            assert row is not None
            assert abs(row[0] - 0.7) < 1e-9
        finally:
            close_db(conn)


class TestRebuildIncludesPageRank:

    def test_rebuild_populates_pagerank(self) -> None:
        from literature.scripts.lit import run

        exit_code = run(["rebuild"])
        assert exit_code == 0

        conn = init_db(Path("literature"))
        try:
            row = conn.execute(
                "SELECT pagerank_score FROM papers "
                "WHERE paper_id = 'vaswani2017attention'"
            ).fetchone()
            assert row is not None
            assert row[0] > 0, "PageRank score should be > 0 after rebuild"
        finally:
            close_db(conn)


class TestHITS:

    def test_hits_known_graph(self, tmp_path: Path) -> None:
        root = _lit_root(tmp_path)
        conn = init_db(root)
        try:
            _insert_papers(conn, ["A", "B", "C", "D"])
            _insert_edges(conn, [("A", "B"), ("A", "C"), ("B", "C"), ("D", "C")])

            hubs, authorities = compute_hits(conn)

            assert len(hubs) == 4
            assert len(authorities) == 4
            assert authorities["C"] == max(authorities.values())
            assert hubs["A"] > hubs["C"]
        finally:
            close_db(conn)

    def test_hits_empty_graph(self, tmp_path: Path) -> None:
        root = _lit_root(tmp_path)
        conn = init_db(root)
        try:
            hubs, authorities = compute_hits(conn)
            assert hubs == {}
            assert authorities == {}
        finally:
            close_db(conn)
