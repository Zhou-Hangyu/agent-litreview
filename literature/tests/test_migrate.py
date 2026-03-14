"""Tests for literature.scripts.migrate."""

from __future__ import annotations

from pathlib import Path

import pytest

from literature.scripts.migrate import migrate_from_v1, run


def _setup_lit_dir(tmp_path: Path) -> Path:
    """Create a minimal literature/ directory with papers."""
    root = tmp_path / "literature"
    papers_dir = root / "papers"
    papers_dir.mkdir(parents=True)
    (root / "AGENTS.md").write_text("# Literature\n", encoding="utf-8")

    # Create a minimal paper file
    paper_file = papers_dir / "test2024paper.md"
    paper_file.write_text(
        """---
doc_id: "test2024paper"
title: "Test Paper"
authors: ["Test, A."]
year: 2024
citation_count: 100
---

Test content.
""",
        encoding="utf-8",
    )

    return root


def test_migrate_returns_correct_paper_count(tmp_path: Path) -> None:
    """Test that migrate returns the correct paper count."""
    root = _setup_lit_dir(tmp_path)
    result = migrate_from_v1(root)
    assert result["papers"] == 1


def test_migrate_returns_citation_count(tmp_path: Path) -> None:
    """Test that migrate returns citation count."""
    root = _setup_lit_dir(tmp_path)
    result = migrate_from_v1(root)
    assert "citations" in result
    assert isinstance(result["citations"], int)


def test_migrate_vaswani_exists() -> None:
    """Test that vaswani2017attention exists in the real collection."""
    from literature.scripts.db import init_db

    db = init_db(Path("literature"))
    result = db.execute(
        "SELECT paper_id FROM papers WHERE paper_id='vaswani2017attention'"
    ).fetchone()
    db.close()
    assert result is not None


def test_migrate_vaswani_citation_count() -> None:
    """Test that vaswani2017attention has correct citation count."""
    from literature.scripts.db import init_db

    db = init_db(Path("literature"))
    result = db.execute(
        "SELECT citation_count FROM papers WHERE paper_id='vaswani2017attention'"
    ).fetchone()
    db.close()
    assert result is not None
    assert result[0] == 169004


def test_migrate_cli_exits_zero(tmp_path: Path) -> None:
    """Test that lit migrate --from-v1 exits with code 0."""
    root = _setup_lit_dir(tmp_path)
    exit_code = run(["--from-v1"], root=root)
    assert exit_code == 0
