"""Tests for literature.scripts.summarize — PDF text extraction."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pymupdf
import pytest
import responses as responses_lib

from literature.scripts.enrich import S2_BASE_URL, run as enrich_run
from literature.scripts.parse import read_frontmatter, write_paper_file
from literature.scripts.summarize import extract_structured, run


def create_test_pdf(path: Path, text: str = "Test content page 1") -> None:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    doc.save(str(path))
    doc.close()


@pytest.fixture()
def lit_root(tmp_path: Path) -> Path:
    papers_dir = tmp_path / "papers"
    papers_dir.mkdir()
    return tmp_path


@pytest.fixture()
def pdf_dir(tmp_path: Path) -> Path:
    d = tmp_path / "pdfs"
    d.mkdir()
    return d


def _make_paper(
    lit_root: Path,
    citekey: str,
    pdf_path: str = "",
    reading_status: dict | None = None,
) -> Path:
    meta: dict = {
        "abstract": "Test abstract",
        "arxiv_id": "1234.5678",
        "authors": ["Smith, John"],
        "citation_count": 10,
        "cited_by": [],
        "cites": [],
        "doc_id": citekey,
        "doi": "",
        "et_al": False,
        "pdf_path": pdf_path,
        "reading_status": reading_status or {"global": "unread"},
        "related": [],
        "resource_type": "preprint",
        "s2_id": "abc123",
        "tags": [],
        "themes": [],
        "title": "Test Paper",
        "tldr": "",
        "url": "https://arxiv.org/abs/1234.5678",
        "venue": "",
        "year": 2024,
    }
    paper_path = lit_root / "papers" / f"{citekey}.md"
    write_paper_file(paper_path, meta, "## Notes\n\n(placeholder)\n")
    return paper_path


def test_stdout_mode_prints_extracted_text(
    lit_root: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    pdf_path = tmp_path / "test.pdf"
    create_test_pdf(pdf_path, "Hello from the PDF")
    _make_paper(lit_root, "smith2024test", pdf_path=str(pdf_path))

    exit_code = run(["smith2024test"], lit_root=lit_root)

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "Hello from the PDF" in captured.out


def test_write_mode_updates_body_and_status(
    lit_root: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    pdf_path = tmp_path / "test.pdf"
    create_test_pdf(pdf_path, "Write mode content")
    paper_path = _make_paper(lit_root, "smith2024write", pdf_path=str(pdf_path))

    exit_code = run(["smith2024write", "--write"], lit_root=lit_root)

    assert exit_code == 0
    meta, body = read_frontmatter(paper_path)
    assert meta["reading_status"]["global"] == "skimmed"
    assert "## Abstract" in body
    assert "Write mode content" in body
    assert "## Conclusion" in body


def test_missing_pdf_path_returns_error(
    lit_root: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _make_paper(lit_root, "smith2024nopdf", pdf_path="")

    exit_code = run(["smith2024nopdf"], lit_root=lit_root)

    assert exit_code == 1
    assert "pdf_path" in capsys.readouterr().err


def test_missing_pdf_file_returns_error(
    lit_root: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    nonexistent = tmp_path / "does_not_exist.pdf"
    _make_paper(lit_root, "smith2024gone", pdf_path=str(nonexistent))

    exit_code = run(["smith2024gone"], lit_root=lit_root)

    assert exit_code == 1
    assert "not found" in capsys.readouterr().err.lower()


def test_missing_paper_returns_error(
    lit_root: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = run(["doesnotexist2024foo"], lit_root=lit_root)

    assert exit_code == 1
    assert "not found" in capsys.readouterr().err.lower()


@responses_lib.activate
def test_enrich_detects_pdf_path(
    tmp_path: Path,
) -> None:
    papers_dir = tmp_path / "papers"
    papers_dir.mkdir()

    pdf_dir = tmp_path / "pdfs"
    pdf_dir.mkdir()
    pdf_file = pdf_dir / "1706.03762.pdf"
    create_test_pdf(pdf_file, "Attention paper PDF")

    fixture_path = Path(__file__).parent / "fixtures" / "sample_s2_response.json"
    with open(fixture_path) as fh:
        s2_fixture = json.load(fh)

    responses_lib.add(
        responses_lib.GET,
        re.compile(r"https://api\.semanticscholar\.org/graph/v1/paper/arXiv:1706\.03762"),
        json=s2_fixture,
        status=200,
    )

    import literature.scripts.enrich as enrich_mod

    original_repo_root = enrich_mod.REPO_ROOT
    enrich_mod.REPO_ROOT = tmp_path

    pdf_papers_dir = tmp_path / "papers"
    create_test_pdf(pdf_papers_dir / "1706.03762.pdf", "Attention paper PDF")

    try:
        exit_code = enrich_run(
            ["https://arxiv.org/abs/1706.03762"],
            papers_dir=papers_dir,
        )
    finally:
        enrich_mod.REPO_ROOT = original_repo_root

    assert exit_code == 0
    paper_files = list(papers_dir.glob("*.md"))
    assert len(paper_files) == 1
    meta, _ = read_frontmatter(paper_files[0])
    assert meta["pdf_path"] == "papers/1706.03762.pdf"


def test_extract_structured_returns_correct_keys(tmp_path: Path) -> None:
    pdf_path = tmp_path / "test.pdf"
    create_test_pdf(pdf_path, "Some content for structured extraction")

    result = extract_structured(pdf_path)

    assert isinstance(result, dict)
    assert "sections" in result
    assert "abstract" in result
    assert "conclusion" in result
    assert "section_headings" in result
    assert isinstance(result["sections"], list)
    assert isinstance(result["section_headings"], list)
    # With uniform font size, no headings detected — abstract is first paragraph
    assert "Some content" in result["abstract"]


def test_write_mode_produces_structured_not_page_dump(
    lit_root: Path,
    tmp_path: Path,
) -> None:
    pdf_path = tmp_path / "test.pdf"
    create_test_pdf(pdf_path, "Structured output test content")
    paper_path = _make_paper(lit_root, "smith2024struct", pdf_path=str(pdf_path))

    exit_code = run(["smith2024struct", "--write"], lit_root=lit_root)

    assert exit_code == 0
    meta, body = read_frontmatter(paper_path)
    assert "## Abstract" in body
    assert "## Section Outline" in body
    assert "--- Page 1 ---" not in body
