"""Tests for literature.scripts.db — SQLite schema and connection management."""

from __future__ import annotations

import json
import sqlite3
import struct
from pathlib import Path

import pytest

from literature.scripts.db import close_db, get_db, init_db


# ── Helpers ────────────────────────────────────────────────────────────────────


def _lit_root(tmp_path: Path) -> Path:
    """Create a minimal literature directory structure and return its path."""
    root = tmp_path / "literature"
    (root / "AGENTS.md").parent.mkdir(parents=True)
    (root / "AGENTS.md").write_text("# AGENTS", encoding="utf-8")
    (root / "papers").mkdir()
    (root / "index").mkdir()
    return root


def _table_names(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' OR type='shadow'"
    ).fetchall()
    return {r[0] for r in rows}


# ── Schema Tests ───────────────────────────────────────────────────────────────


def test_init_db_creates_papers_table(tmp_path: Path) -> None:
    root = _lit_root(tmp_path)
    conn = init_db(root)
    try:
        tables = _table_names(conn)
        assert "papers" in tables, f"Expected 'papers' table; got {tables}"
    finally:
        close_db(conn)


def test_init_db_creates_citations_table(tmp_path: Path) -> None:
    root = _lit_root(tmp_path)
    conn = init_db(root)
    try:
        tables = _table_names(conn)
        assert "citations" in tables
    finally:
        close_db(conn)


def test_init_db_creates_discovery_inbox_table(tmp_path: Path) -> None:
    root = _lit_root(tmp_path)
    conn = init_db(root)
    try:
        tables = _table_names(conn)
        assert "discovery_inbox" in tables
    finally:
        close_db(conn)


def test_init_db_creates_jobs_table(tmp_path: Path) -> None:
    root = _lit_root(tmp_path)
    conn = init_db(root)
    try:
        tables = _table_names(conn)
        assert "jobs" in tables
    finally:
        close_db(conn)


def test_init_db_creates_fts5_table(tmp_path: Path) -> None:
    """papers_fts virtual table must exist."""
    root = _lit_root(tmp_path)
    conn = init_db(root)
    try:
        # FTS5 virtual tables appear in sqlite_master with type='table'
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE name='papers_fts'"
        ).fetchall()
        assert rows, "papers_fts virtual table not found in sqlite_master"
    finally:
        close_db(conn)


def test_init_db_all_five_tables(tmp_path: Path) -> None:
    """All 5 required tables must exist after init_db."""
    root = _lit_root(tmp_path)
    conn = init_db(root)
    try:
        tables = _table_names(conn)
        for expected in ("papers", "citations", "discovery_inbox", "jobs", "papers_fts"):
            assert expected in tables, f"Missing table: {expected}"
    finally:
        close_db(conn)


# ── PRAGMA Tests ───────────────────────────────────────────────────────────────


def test_get_db_pragma_journal_mode_wal(tmp_path: Path) -> None:
    root = _lit_root(tmp_path)
    init_db(root)
    conn = get_db(root)
    try:
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert mode == "wal", f"Expected WAL journal mode; got {mode!r}"
    finally:
        close_db(conn)


def test_get_db_pragma_busy_timeout(tmp_path: Path) -> None:
    root = _lit_root(tmp_path)
    init_db(root)
    conn = get_db(root)
    try:
        timeout = conn.execute("PRAGMA busy_timeout").fetchone()[0]
        assert timeout == 5000, f"Expected busy_timeout=5000; got {timeout}"
    finally:
        close_db(conn)


def test_get_db_row_factory_is_sqlite_row(tmp_path: Path) -> None:
    """get_db must return connection with row_factory=sqlite3.Row."""
    root = _lit_root(tmp_path)
    init_db(root)
    conn = get_db(root)
    try:
        assert conn.row_factory is sqlite3.Row, (
            f"row_factory must be sqlite3.Row; got {conn.row_factory!r}"
        )
    finally:
        close_db(conn)


# ── FTS5 Tests ─────────────────────────────────────────────────────────────────


def test_fts5_hyphenated_term_search(tmp_path: Path) -> None:
    """FTS5 must match hyphenated scientific terms like 'self-attention'."""
    root = _lit_root(tmp_path)
    conn = init_db(root)
    try:
        conn.execute(
            "INSERT INTO papers (paper_id, title, abstract) VALUES (?, ?, ?)",
            ("vaswani2017attention", "Attention Is All You Need",
             "We propose self-attention as the core mechanism."),
        )
        # Sync FTS5 content table
        conn.execute(
            "INSERT INTO papers_fts (rowid, paper_id, title, abstract, tldr, "
            "summary_l4_text, summary_l2_claims) "
            "SELECT rowid, paper_id, title, abstract, tldr, summary_l4_text, "
            "summary_l2_claims FROM papers WHERE paper_id = 'vaswani2017attention'"
        )
        conn.commit()

        # FTS5 phrase-quote the term so the query parser passes "self-attention"
        # as a literal to the tokenizer; tokenchars='-_' means it indexes/matches
        # as a single token rather than splitting on '-'.
        rows = conn.execute(
            'SELECT paper_id FROM papers_fts WHERE papers_fts MATCH \'"self-attention"\''
        ).fetchall()
        assert rows, "FTS5 phrase MATCH '\"self-attention\"' returned no results — check tokenchars"
        paper_ids = [r[0] for r in rows]
        assert "vaswani2017attention" in paper_ids
    finally:
        close_db(conn)


def test_fts5_bm25_returns_negative_scores(tmp_path: Path) -> None:
    """bm25() must return negative scores — more negative = more relevant."""
    root = _lit_root(tmp_path)
    conn = init_db(root)
    try:
        papers = [
            ("paper1", "Self-Attention Mechanism", "self-attention enables parallelism"),
            ("paper2", "RNN Architecture", "recurrent neural networks use sequential computation"),
            ("paper3", "Transformer Model", "self-attention used in transformer self-attention"),
        ]
        for pid, title, abstract in papers:
            conn.execute(
                "INSERT INTO papers (paper_id, title, abstract) VALUES (?, ?, ?)",
                (pid, title, abstract),
            )
        conn.execute(
            "INSERT INTO papers_fts (rowid, paper_id, title, abstract, tldr, "
            "summary_l4_text, summary_l2_claims) "
            "SELECT rowid, paper_id, title, abstract, tldr, summary_l4_text, "
            "summary_l2_claims FROM papers"
        )
        conn.commit()

        rows = conn.execute(
            'SELECT paper_id, bm25(papers_fts) AS score '
            'FROM papers_fts WHERE papers_fts MATCH \'"self-attention"\' '
            "ORDER BY score"
        ).fetchall()
        assert rows, "Expected results for 'self-attention' query"
        for row in rows:
            assert row[1] < 0, (
                f"bm25() should return negative scores; got {row[1]} for {row[0]}"
            )
    finally:
        close_db(conn)


# ── Embedding BLOB Test ────────────────────────────────────────────────────────


def test_embedding_blob_roundtrip(tmp_path: Path) -> None:
    """Store 768 float32 embedding as BLOB and retrieve identical bytes."""
    root = _lit_root(tmp_path)
    conn = init_db(root)
    try:
        # 768 float32 values as raw bytes
        floats = [float(i) * 0.001 for i in range(768)]
        blob = struct.pack(f"{len(floats)}f", *floats)

        conn.execute(
            "INSERT INTO papers (paper_id, title, embedding) VALUES (?, ?, ?)",
            ("embed_test", "Embedding Test Paper", blob),
        )
        conn.commit()

        row = conn.execute(
            "SELECT embedding FROM papers WHERE paper_id = 'embed_test'"
        ).fetchone()
        assert row is not None
        retrieved = row[0]
        assert retrieved == blob, "Embedding BLOB roundtrip failed — bytes don't match"

        # Verify we can unpack back to floats
        recovered = struct.unpack(f"{len(floats)}f", retrieved)
        assert len(recovered) == 768
        assert abs(recovered[0] - floats[0]) < 1e-6
    finally:
        close_db(conn)


# ── Idempotent Init Test ───────────────────────────────────────────────────────


def test_init_db_idempotent(tmp_path: Path) -> None:
    """Calling init_db twice must not raise any errors."""
    root = _lit_root(tmp_path)
    conn1 = init_db(root)
    close_db(conn1)
    # Second call should not raise
    conn2 = init_db(root)
    try:
        tables = _table_names(conn2)
        assert "papers" in tables
    finally:
        close_db(conn2)


# ── DB Path Test ───────────────────────────────────────────────────────────────


def test_init_db_creates_db_at_correct_path(tmp_path: Path) -> None:
    """DB file must be created at literature/index/papers.db."""
    root = _lit_root(tmp_path)
    conn = init_db(root)
    close_db(conn)
    db_path = root / "index" / "papers.db"
    assert db_path.exists(), f"Expected DB at {db_path}, but it does not exist"


# ── Papers Table Column Test ───────────────────────────────────────────────────


def test_papers_table_has_required_columns(tmp_path: Path) -> None:
    """papers table must contain all required columns."""
    root = _lit_root(tmp_path)
    conn = init_db(root)
    try:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(papers)").fetchall()}
        required = {
            "paper_id", "title", "authors", "year", "venue", "doi", "arxiv_id",
            "s2_id", "url", "resource_type", "et_al", "abstract", "tldr",
            "citation_count", "influential_citation_count", "reading_status_global",
            "reading_status_json", "tags", "themes", "contribution_type",
            "provenance_json", "pdf_path", "summary_l4_text", "summary_l4_model",
            "summary_l4_generated_at", "summary_l2_claims", "summary_l2_model",
            "summary_l2_generated_at", "embedding", "pagerank_score",
            "file_path", "synced_at",
        }
        missing = required - cols
        assert not missing, f"papers table missing columns: {missing}"
    finally:
        close_db(conn)


def test_papers_table_defaults(tmp_path: Path) -> None:
    """Inserting minimal paper should apply DEFAULT values correctly."""
    root = _lit_root(tmp_path)
    conn = init_db(root)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute(
            "INSERT INTO papers (paper_id, title) VALUES (?, ?)",
            ("minimal_paper", "A Minimal Paper"),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM papers WHERE paper_id = 'minimal_paper'"
        ).fetchone()
        assert row is not None
        assert row["reading_status_global"] == "unread"
        assert row["resource_type"] == "paper"
        assert row["et_al"] == 0
        assert row["citation_count"] == 0
        assert row["pagerank_score"] == 0.0
    finally:
        close_db(conn)
