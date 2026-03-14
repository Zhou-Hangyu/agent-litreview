"""Tests for literature.scripts.enrich — paper enrichment via Semantic Scholar."""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

import pytest
import responses as responses_lib

from literature.scripts.enrich import (
    S2_BASE_URL,
    enrich_paper,
    format_author_name,
    generate_resource_id,
    run,
    s2_to_frontmatter,
)
from literature.scripts.parse import read_frontmatter, write_paper_file

FIXTURE_DIR = Path(__file__).parent / "fixtures"
VASWANI_ARXIV_URL_PATTERN = re.compile(
    r"https://api\.semanticscholar\.org/graph/v1/paper/arXiv:1706\.03762"
)
DOI_URL_PATTERN = re.compile(
    r"https://api\.semanticscholar\.org/graph/v1/paper/DOI:10\.48550/arXiv\.1706\.03762"
)


@pytest.fixture()
def s2_fixture() -> dict:
    with open(FIXTURE_DIR / "sample_s2_response.json") as fh:
        return json.load(fh)


@pytest.fixture()
def papers_dir(tmp_path: Path) -> Path:
    d = tmp_path / "papers"
    d.mkdir()
    return d


@pytest.fixture()
def resources_dir(tmp_path: Path) -> Path:
    d = tmp_path / "resources"
    d.mkdir()
    return d


# ── Unit: format_author_name ──────────────────────────────────────────────────


def test_format_author_first_last() -> None:
    assert format_author_name("Ashish Vaswani") == "Vaswani, Ashish"


def test_format_author_with_middle_name() -> None:
    assert format_author_name("Aidan N. Gomez") == "Gomez, Aidan N."


def test_format_author_already_formatted() -> None:
    assert format_author_name("Vaswani, Ashish") == "Vaswani, Ashish"


def test_format_author_single_name() -> None:
    assert format_author_name("Madonna") == "Madonna"


# ── Unit: generate_resource_id ─────────────────────────────────────────────────


def test_generate_resource_id_from_title() -> None:
    assert generate_resource_id("https://example.com", "My Great Blog Post") == "my_great_blog_post"


def test_generate_resource_id_from_url_when_untitled() -> None:
    result = generate_resource_id("https://example.com/some-post", "Untitled")
    assert result
    assert " " not in result


# ── Integration: test_enrich_arxiv_url ────────────────────────────────────────


@responses_lib.activate
def test_enrich_arxiv_url(
    s2_fixture: dict,
    papers_dir: Path,
    resources_dir: Path,
) -> None:
    responses_lib.add(
        responses_lib.GET,
        VASWANI_ARXIV_URL_PATTERN,
        json=s2_fixture,
        status=200,
    )

    exit_code = run(
        ["https://arxiv.org/abs/1706.03762"],
        papers_dir=papers_dir,
        resources_dir=resources_dir,
    )

    assert exit_code == 0
    paper_files = list(papers_dir.glob("*.md"))
    assert len(paper_files) == 1

    meta, body = read_frontmatter(paper_files[0])
    assert meta["title"] == "Attention Is All You Need"
    assert meta["year"] == 2017
    assert meta["arxiv_id"] == "1706.03762"
    assert meta["doc_id"] == "vaswani2017attention"
    assert meta["authors"][0] == "Vaswani, Ashish"
    assert meta["citation_count"] == 50000
    assert meta["reading_status"] == {"global": "unread"}
    assert meta["cites"] == []
    assert "## Notes" in body


# ── Integration: test_enrich_doi ─────────────────────────────────────────────


@responses_lib.activate
def test_enrich_doi(
    s2_fixture: dict,
    papers_dir: Path,
    resources_dir: Path,
) -> None:
    responses_lib.add(
        responses_lib.GET,
        DOI_URL_PATTERN,
        json=s2_fixture,
        status=200,
    )

    exit_code = run(
        ["10.48550/arXiv.1706.03762"],
        papers_dir=papers_dir,
        resources_dir=resources_dir,
    )

    assert exit_code == 0
    paper_files = list(papers_dir.glob("*.md"))
    assert len(paper_files) == 1
    meta, _ = read_frontmatter(paper_files[0])
    assert meta["doi"] == "10.48550/arXiv.1706.03762"
    assert meta["title"] == "Attention Is All You Need"


# ── Integration: test_enrich_paper_not_found ─────────────────────────────────


@responses_lib.activate
def test_enrich_paper_not_found(
    papers_dir: Path,
    resources_dir: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    responses_lib.add(
        responses_lib.GET,
        re.compile(r"https://api\.semanticscholar\.org/graph/v1/paper/arXiv:9999\.99999"),
        json={"error": "not found"},
        status=404,
    )

    exit_code = run(
        ["9999.99999"],
        papers_dir=papers_dir,
        resources_dir=resources_dir,
    )

    assert exit_code == 1
    stderr = capsys.readouterr().err
    assert "not found" in stderr.lower() or "check" in stderr.lower()


# ── Integration: test_enrich_rate_limited ─────────────────────────────────────


@responses_lib.activate
def test_enrich_rate_limited(
    papers_dir: Path,
    resources_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(time, "sleep", lambda _: None)

    for _ in range(4):
        responses_lib.add(
            responses_lib.GET,
            VASWANI_ARXIV_URL_PATTERN,
            json={"error": "rate limited"},
            status=429,
        )

    exit_code = run(
        ["https://arxiv.org/abs/1706.03762"],
        papers_dir=papers_dir,
        resources_dir=resources_dir,
    )

    assert exit_code == 1
    stderr = capsys.readouterr().err
    assert "rate limited" in stderr.lower() or "rate" in stderr.lower()


# ── Integration: test_enrich_duplicate_paper ─────────────────────────────────


@responses_lib.activate
def test_enrich_duplicate_paper(
    s2_fixture: dict,
    papers_dir: Path,
    resources_dir: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    responses_lib.add(
        responses_lib.GET,
        VASWANI_ARXIV_URL_PATTERN,
        json=s2_fixture,
        status=200,
    )
    run(
        ["https://arxiv.org/abs/1706.03762"],
        papers_dir=papers_dir,
        resources_dir=resources_dir,
    )
    original_content = (papers_dir / "vaswani2017attention.md").read_text()
    capsys.readouterr()

    responses_lib.add(
        responses_lib.GET,
        VASWANI_ARXIV_URL_PATTERN,
        json=s2_fixture,
        status=200,
    )
    exit_code = run(
        ["https://arxiv.org/abs/1706.03762"],
        papers_dir=papers_dir,
        resources_dir=resources_dir,
    )

    assert exit_code == 0
    stdout = capsys.readouterr().out
    assert "already exists" in stdout
    assert (papers_dir / "vaswani2017attention.md").read_text() == original_content


# ── Integration: test_enrich_update ──────────────────────────────────────────


@responses_lib.activate
def test_enrich_update(
    s2_fixture: dict,
    papers_dir: Path,
    resources_dir: Path,
) -> None:
    existing_meta = {
        "abstract": "Old abstract",
        "arxiv_id": "1706.03762",
        "authors": ["Vaswani, Ashish"],
        "citation_count": 100,
        "cited_by": [],
        "cites": [],
        "doc_id": "vaswani2017attention",
        "doi": "10.48550/arXiv.1706.03762",
        "et_al": False,
        "reading_status": {"global": "read"},
        "related": [],
        "resource_type": "paper",
        "s2_id": "abc123",
        "tags": ["transformers"],
        "themes": ["attention"],
        "title": "Attention Is All You Need",
        "tldr": "Old tldr",
        "url": "https://arxiv.org/abs/1706.03762",
        "venue": "NeurIPS",
        "year": 2017,
    }
    existing_body = "## Notes\n\nMy personal notes on this paper.\n"
    write_paper_file(
        papers_dir / "vaswani2017attention.md",
        existing_meta,
        existing_body,
    )

    updated_s2 = {**s2_fixture, "citationCount": 99999, "abstract": "Updated abstract"}
    responses_lib.add(
        responses_lib.GET,
        VASWANI_ARXIV_URL_PATTERN,
        json=updated_s2,
        status=200,
    )

    exit_code = run(
        ["--update", "vaswani2017attention"],
        papers_dir=papers_dir,
        resources_dir=resources_dir,
    )

    assert exit_code == 0
    meta, body = read_frontmatter(papers_dir / "vaswani2017attention.md")
    assert meta["citation_count"] == 99999
    assert meta["abstract"] == "Updated abstract"
    assert meta["reading_status"] == {"global": "read"}
    assert meta["tags"] == ["transformers"]
    assert meta["themes"] == ["attention"]
    assert "My personal notes on this paper." in body


# ── Integration: test_enrich_blog_resource ───────────────────────────────────


def test_enrich_blog_resource(
    papers_dir: Path,
    resources_dir: Path,
) -> None:
    exit_code = run(
        ["--type", "blog", "https://example.com/my-post", "--title", "My Blog Post"],
        papers_dir=papers_dir,
        resources_dir=resources_dir,
    )

    assert exit_code == 0
    resource_files = list(resources_dir.glob("*.md"))
    assert len(resource_files) == 1
    assert len(list(papers_dir.glob("*.md"))) == 0

    meta, body = read_frontmatter(resource_files[0])
    assert meta["resource_type"] == "blog"
    assert meta["title"] == "My Blog Post"
    assert meta["url"] == "https://example.com/my-post"
    assert meta["reading_status"] == {"global": "unread"}
    assert "## Notes" in body


# ── Integration: test_auto_tags_from_fields_of_study ─────────────────────────


@responses_lib.activate
def test_auto_tags_from_fields_of_study(
    s2_fixture: dict,
    papers_dir: Path,
    resources_dir: Path,
) -> None:
    """Auto-tags from fieldsOfStudy and s2FieldsOfStudy are stored lowercased and sorted."""
    # s2_fixture already has:
    #   fieldsOfStudy: ["Computer Science"]
    #   s2FieldsOfStudy: [{"category": "Computer Science"}, {"category": "Machine Learning"}]
    responses_lib.add(
        responses_lib.GET,
        VASWANI_ARXIV_URL_PATTERN,
        json=s2_fixture,
        status=200,
    )

    exit_code = run(
        ["https://arxiv.org/abs/1706.03762"],
        papers_dir=papers_dir,
        resources_dir=resources_dir,
    )

    assert exit_code == 0
    paper_files = list(papers_dir.glob("*.md"))
    assert len(paper_files) == 1
    meta, _ = read_frontmatter(paper_files[0])
    # Deduped, lowercased, sorted: "computer science" and "machine learning"
    assert meta["tags"] == ["computer science", "machine learning"]


# ── Integration: test_influential_citation_count_stored ──────────────────────


@responses_lib.activate
def test_influential_citation_count_stored(
    s2_fixture: dict,
    papers_dir: Path,
    resources_dir: Path,
) -> None:
    """influentialCitationCount from S2 is stored as influential_citation_count."""
    # s2_fixture has influentialCitationCount: 1000
    responses_lib.add(
        responses_lib.GET,
        VASWANI_ARXIV_URL_PATTERN,
        json=s2_fixture,
        status=200,
    )

    exit_code = run(
        ["https://arxiv.org/abs/1706.03762"],
        papers_dir=papers_dir,
        resources_dir=resources_dir,
    )

    assert exit_code == 0
    paper_files = list(papers_dir.glob("*.md"))
    assert len(paper_files) == 1
    meta, _ = read_frontmatter(paper_files[0])
    assert meta["influential_citation_count"] == 1000


# ── Integration: test_provenance_stored_when_passed ──────────────────────────


@responses_lib.activate
def test_provenance_stored_when_passed(
    s2_fixture: dict,
    tmp_path: Path,
) -> None:
    """Provenance dict passed to enrich_paper() is stored in frontmatter."""
    responses_lib.add(
        responses_lib.GET,
        VASWANI_ARXIV_URL_PATTERN,
        json=s2_fixture,
        status=200,
    )

    provenance = {"method": "scout_recommend", "discovered_at": "2026-03-14"}
    lit_root = tmp_path / "literature"
    lit_root.mkdir()

    paper_path = enrich_paper(
        "https://arxiv.org/abs/1706.03762",
        lit_root,
        provenance=provenance,
    )

    meta, _ = read_frontmatter(paper_path)
    assert meta["provenance"] == provenance


@responses_lib.activate
def test_provenance_absent_by_default(
    s2_fixture: dict,
    tmp_path: Path,
) -> None:
    """When provenance is not passed, it should not appear in frontmatter."""
    responses_lib.add(
        responses_lib.GET,
        VASWANI_ARXIV_URL_PATTERN,
        json=s2_fixture,
        status=200,
    )

    lit_root = tmp_path / "literature"
    lit_root.mkdir()

    paper_path = enrich_paper(
        "https://arxiv.org/abs/1706.03762",
        lit_root,
    )

    meta, _ = read_frontmatter(paper_path)
    assert "provenance" not in meta
