"""Tests for the literature batch update script."""

from __future__ import annotations

from pathlib import Path

import pytest

from literature.scripts.parse import read_frontmatter, write_paper_file
from literature.scripts.update import run


# ── Fixtures ───────────────────────────────────────────────────────────────────


def _make_paper(
    path: Path,
    citekey: str,
    *,
    status: str = "unread",
    tags: list[str] | None = None,
    themes: list[str] | None = None,
) -> None:
    meta = {
        "doc_id": citekey,
        "title": f"Test Paper {citekey}",
        "reading_status": {"global": status},
        "tags": tags or [],
        "themes": themes or [],
        "cited_by": [],
        "cites": [],
    }
    write_paper_file(path, meta, "## Notes\n")


def _setup_root(tmp_path: Path) -> Path:
    root = tmp_path / "literature"
    papers_dir = root / "papers"
    papers_dir.mkdir(parents=True)

    _make_paper(papers_dir / "paper1.md", "paper1", tags=["existing"], themes=["theme1"])
    _make_paper(papers_dir / "paper2.md", "paper2", tags=["tag1"], themes=["theme2"])
    _make_paper(papers_dir / "paper3.md", "paper3")

    return root


# ── status subcommand ──────────────────────────────────────────────────────────


def test_status_sets_global_on_multiple_papers(tmp_path: Path) -> None:
    root = _setup_root(tmp_path)

    exit_code = run(["status", "read", "paper1", "paper2"], root=root)

    assert exit_code == 0

    for citekey in ("paper1", "paper2"):
        meta, _ = read_frontmatter(root / "papers" / f"{citekey}.md")
        assert meta["reading_status"]["global"] == "read"

    meta3, _ = read_frontmatter(root / "papers" / "paper3.md")
    assert meta3["reading_status"]["global"] == "unread"


def test_status_all_valid_values(tmp_path: Path) -> None:
    root = _setup_root(tmp_path)

    for value in ("unread", "skimmed", "read", "synthesized"):
        assert run(["status", value, "paper1"], root=root) == 0
        meta, _ = read_frontmatter(root / "papers" / "paper1.md")
        assert meta["reading_status"]["global"] == value


def test_status_invalid_value_returns_exit_1(tmp_path: Path) -> None:
    root = _setup_root(tmp_path)

    exit_code = run(["status", "invalid_status", "paper1"], root=root)

    assert exit_code == 1
    meta, _ = read_frontmatter(root / "papers" / "paper1.md")
    assert meta["reading_status"]["global"] == "unread"


def test_status_unknown_citekey_returns_exit_1(tmp_path: Path) -> None:
    root = _setup_root(tmp_path)

    exit_code = run(["status", "read", "nonexistent_paper"], root=root)

    assert exit_code == 1


def test_status_partial_success_updates_found_papers(tmp_path: Path) -> None:
    root = _setup_root(tmp_path)

    exit_code = run(["status", "read", "paper1", "nonexistent"], root=root)

    assert exit_code == 1
    meta, _ = read_frontmatter(root / "papers" / "paper1.md")
    assert meta["reading_status"]["global"] == "read"


def test_status_prints_updated_path(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _setup_root(tmp_path)

    run(["status", "read", "paper1"], root=root)

    captured = capsys.readouterr()
    assert "paper1.md" in captured.out


# ── tags add subcommand ────────────────────────────────────────────────────────


def test_tags_add_single_tag(tmp_path: Path) -> None:
    root = _setup_root(tmp_path)

    exit_code = run(["tags", "add", "newtag", "paper1"], root=root)

    assert exit_code == 0
    meta, _ = read_frontmatter(root / "papers" / "paper1.md")
    assert "newtag" in meta["tags"]
    assert "existing" in meta["tags"]


def test_tags_add_multiple_comma_separated(tmp_path: Path) -> None:
    root = _setup_root(tmp_path)

    run(["tags", "add", "tag_a,tag_b,tag_c", "paper3"], root=root)

    meta, _ = read_frontmatter(root / "papers" / "paper3.md")
    assert "tag_a" in meta["tags"]
    assert "tag_b" in meta["tags"]
    assert "tag_c" in meta["tags"]


def test_tags_add_no_duplicates(tmp_path: Path) -> None:
    root = _setup_root(tmp_path)

    run(["tags", "add", "existing", "paper1"], root=root)

    meta, _ = read_frontmatter(root / "papers" / "paper1.md")
    assert meta["tags"].count("existing") == 1


def test_tags_add_to_multiple_papers(tmp_path: Path) -> None:
    root = _setup_root(tmp_path)

    run(["tags", "add", "shared", "paper1", "paper2"], root=root)

    for citekey in ("paper1", "paper2"):
        meta, _ = read_frontmatter(root / "papers" / f"{citekey}.md")
        assert "shared" in meta["tags"]


def test_tags_add_unknown_citekey_returns_exit_1(tmp_path: Path) -> None:
    root = _setup_root(tmp_path)

    exit_code = run(["tags", "add", "sometag", "ghost_paper"], root=root)

    assert exit_code == 1


# ── tags remove subcommand ────────────────────────────────────────────────────


def test_tags_remove_existing_tag(tmp_path: Path) -> None:
    root = _setup_root(tmp_path)

    exit_code = run(["tags", "remove", "existing", "paper1"], root=root)

    assert exit_code == 0
    meta, _ = read_frontmatter(root / "papers" / "paper1.md")
    assert "existing" not in meta["tags"]


def test_tags_remove_absent_tag_no_error(tmp_path: Path) -> None:
    root = _setup_root(tmp_path)

    exit_code = run(["tags", "remove", "not_there", "paper1"], root=root)

    assert exit_code == 0
    meta, _ = read_frontmatter(root / "papers" / "paper1.md")
    assert "existing" in meta["tags"]


def test_tags_remove_multiple_comma_separated(tmp_path: Path) -> None:
    root = _setup_root(tmp_path)

    run(["tags", "add", "a,b,c", "paper3"], root=root)
    run(["tags", "remove", "a,c", "paper3"], root=root)

    meta, _ = read_frontmatter(root / "papers" / "paper3.md")
    assert "a" not in meta["tags"]
    assert "c" not in meta["tags"]
    assert "b" in meta["tags"]


# ── themes add subcommand ──────────────────────────────────────────────────────


def test_themes_add_new_theme(tmp_path: Path) -> None:
    root = _setup_root(tmp_path)

    exit_code = run(["themes", "add", "new_theme", "paper1"], root=root)

    assert exit_code == 0
    meta, _ = read_frontmatter(root / "papers" / "paper1.md")
    assert "new_theme" in meta["themes"]
    assert "theme1" in meta["themes"]


def test_themes_add_no_duplicates(tmp_path: Path) -> None:
    root = _setup_root(tmp_path)

    run(["themes", "add", "theme1", "paper1"], root=root)

    meta, _ = read_frontmatter(root / "papers" / "paper1.md")
    assert meta["themes"].count("theme1") == 1


def test_themes_add_multiple_comma_separated(tmp_path: Path) -> None:
    root = _setup_root(tmp_path)

    run(["themes", "add", "t1,t2,t3", "paper3"], root=root)

    meta, _ = read_frontmatter(root / "papers" / "paper3.md")
    assert "t1" in meta["themes"]
    assert "t2" in meta["themes"]
    assert "t3" in meta["themes"]


def test_themes_add_unknown_citekey_returns_exit_1(tmp_path: Path) -> None:
    root = _setup_root(tmp_path)

    exit_code = run(["themes", "add", "t", "ghost"], root=root)

    assert exit_code == 1


# ── themes remove subcommand ───────────────────────────────────────────────────


def test_themes_remove_existing_theme(tmp_path: Path) -> None:
    root = _setup_root(tmp_path)

    exit_code = run(["themes", "remove", "theme1", "paper1"], root=root)

    assert exit_code == 0
    meta, _ = read_frontmatter(root / "papers" / "paper1.md")
    assert "theme1" not in meta["themes"]


def test_themes_remove_absent_theme_no_error(tmp_path: Path) -> None:
    root = _setup_root(tmp_path)

    exit_code = run(["themes", "remove", "nonexistent_theme", "paper1"], root=root)

    assert exit_code == 0
    meta, _ = read_frontmatter(root / "papers" / "paper1.md")
    assert "theme1" in meta["themes"]


def test_themes_remove_multiple_comma_separated(tmp_path: Path) -> None:
    root = _setup_root(tmp_path)

    run(["themes", "add", "x,y,z", "paper3"], root=root)
    run(["themes", "remove", "x,z", "paper3"], root=root)

    meta, _ = read_frontmatter(root / "papers" / "paper3.md")
    assert "x" not in meta["themes"]
    assert "z" not in meta["themes"]
    assert "y" in meta["themes"]


# ── body preservation ──────────────────────────────────────────────────────────


def test_update_preserves_markdown_body(tmp_path: Path) -> None:
    root = _setup_root(tmp_path)
    paper_path = root / "papers" / "paper1.md"
    meta, _ = read_frontmatter(paper_path)
    write_paper_file(paper_path, meta, "## My Custom Notes\n\nSome content.\n")

    run(["status", "read", "paper1"], root=root)

    _, body = read_frontmatter(paper_path)
    assert "## My Custom Notes" in body
    assert "Some content." in body
