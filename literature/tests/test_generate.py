"""Tests for literature.scripts.generate_review."""

from __future__ import annotations

from pathlib import Path

import pytest

from literature.scripts.generate_review import (
    check_cite_keys,
    find_cite_keys,
    generate,
    load_themes,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _make_lit_dir(tmp_path: Path) -> Path:
    """Create a minimal literature/ directory with required subdirs."""
    root = tmp_path / "literature"
    for d in ("themes", "output", "index", "templates"):
        (root / d).mkdir(parents=True)
    (root / "AGENTS.md").write_text("# Literature\n", encoding="utf-8")

    # Copy templates
    src_templates = Path(__file__).parents[2] / "literature" / "templates"
    import shutil
    if (src_templates / "review_template.tex.j2").exists():
        shutil.copy2(src_templates / "review_template.tex.j2", root / "templates" / "review_template.tex.j2")
    if (src_templates / "neurips_2025.sty").exists():
        shutil.copy2(src_templates / "neurips_2025.sty", root / "templates" / "neurips_2025.sty")

    return root


def _make_theme(root: Path, name: str, title: str, order: int, content: str) -> Path:
    path = root / "themes" / name
    path.write_text(
        f"---\ntitle: \"{title}\"\norder: {order}\n---\n\n{content}\n",
        encoding="utf-8",
    )
    return path


def _make_bib(root: Path, entries: str = "") -> Path:
    bib = root / "index" / "references.bib"
    bib.write_text(
        "% Auto-generated\n\n" + entries,
        encoding="utf-8",
    )
    return bib


# ── load_themes ───────────────────────────────────────────────────────────────

def test_load_themes_sorted_by_order(tmp_path: Path) -> None:
    root = _make_lit_dir(tmp_path)
    _make_theme(root, "b.md", "Beta", 2, "Beta content.")
    _make_theme(root, "a.md", "Alpha", 1, "Alpha content.")
    themes = load_themes(root / "themes")
    assert len(themes) == 2
    assert themes[0]["title"] == "Alpha"
    assert themes[1]["title"] == "Beta"


def test_load_themes_empty_dir(tmp_path: Path) -> None:
    root = _make_lit_dir(tmp_path)
    themes = load_themes(root / "themes")
    assert themes == []


def test_load_themes_missing_dir(tmp_path: Path) -> None:
    themes = load_themes(tmp_path / "nonexistent")
    assert themes == []


# ── find_cite_keys ────────────────────────────────────────────────────────────

def test_find_cite_keys_basic() -> None:
    themes = [{"title": "T", "content": r"See \cite{vaswani2017attention} and \cite{devlin2019bert}."}]
    keys = find_cite_keys(themes)
    assert "vaswani2017attention" in keys
    assert "devlin2019bert" in keys


def test_find_cite_keys_empty() -> None:
    assert find_cite_keys([{"title": "T", "content": "No citations here."}]) == set()


# ── check_cite_keys ───────────────────────────────────────────────────────────

def test_check_cite_keys_missing(tmp_path: Path) -> None:
    bib = tmp_path / "refs.bib"
    bib.write_text("@article{vaswani2017attention,\n  title={A},\n}\n", encoding="utf-8")
    missing = check_cite_keys({"vaswani2017attention", "missing_key"}, bib)
    assert "missing_key" in missing
    assert "vaswani2017attention" not in missing


def test_check_cite_keys_no_bib(tmp_path: Path) -> None:
    missing = check_cite_keys({"some_key"}, tmp_path / "nonexistent.bib")
    assert "some_key" in missing


# ── generate ──────────────────────────────────────────────────────────────────

def test_generate_creates_tex_file(tmp_path: Path) -> None:
    root = _make_lit_dir(tmp_path)
    _make_theme(root, "01-intro.md", "Introduction", 1, "This survey covers transformers.")
    _make_bib(root)
    tex_path = generate(root, title="My Survey", authors="Alice, Bob")
    assert tex_path.exists()
    content = tex_path.read_text(encoding="utf-8")
    assert r"\section{" in content or r"\section{ " in content
    assert "Introduction" in content


def test_generate_contains_neurips_package(tmp_path: Path) -> None:
    root = _make_lit_dir(tmp_path)
    _make_theme(root, "01.md", "Methods", 1, "Content here.")
    _make_bib(root)
    tex_path = generate(root)
    content = tex_path.read_text(encoding="utf-8")
    assert "neurips_2025" in content


def test_generate_contains_bibliographystyle(tmp_path: Path) -> None:
    root = _make_lit_dir(tmp_path)
    _make_theme(root, "01.md", "Methods", 1, "Content here.")
    _make_bib(root)
    tex_path = generate(root)
    content = tex_path.read_text(encoding="utf-8")
    assert r"\bibliographystyle{plainnat}" in content


def test_generate_copies_bib_to_output(tmp_path: Path) -> None:
    root = _make_lit_dir(tmp_path)
    _make_theme(root, "01.md", "Intro", 1, "Content.")
    _make_bib(root, "@article{key,\n  title={T},\n}\n")
    generate(root)
    bib_out = root / "output" / "references.bib"
    assert bib_out.exists()
    assert "@article{key," in bib_out.read_text(encoding="utf-8")


def test_generate_empty_themes_no_crash(tmp_path: Path) -> None:
    root = _make_lit_dir(tmp_path)
    _make_bib(root)
    # No theme files — should not crash
    tex_path = generate(root)
    assert tex_path.exists()


def test_generate_title_override(tmp_path: Path) -> None:
    root = _make_lit_dir(tmp_path)
    _make_theme(root, "01.md", "Methods", 1, "Content.")
    _make_bib(root)
    tex_path = generate(root, title="Custom Survey Title")
    content = tex_path.read_text(encoding="utf-8")
    assert "Custom Survey Title" in content


def test_generate_missing_cite_warns(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    root = _make_lit_dir(tmp_path)
    _make_theme(root, "01.md", "Methods", 1, r"See \cite{missing_key} for details.")
    _make_bib(root)  # empty bib, no entries
    generate(root)
    captured = capsys.readouterr()
    assert "missing_key" in captured.err
