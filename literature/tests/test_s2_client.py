"""Tests for literature.scripts.s2_client — shared Semantic Scholar API client."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
import requests
import responses as responses_lib

from literature.scripts.s2_client import (
    S2_GRAPH_BASE,
    S2_RECS_BASE,
    S2Error,
    fetch_citations,
    fetch_paper,
    fetch_papers_batch,
    fetch_references,
    recommend_multi,
    recommend_papers,
    search_papers,
)

FIXTURE_DIR = Path(__file__).parent / "fixtures"

# Reusable test IDs
PAPER_ID = "arXiv:1706.03762"
S2_HEX_ID = "abc123def456abc123def456abc123def456abc12"
S2_HEX_ID2 = "def456abc123def456abc123def456abc123def45"
FIELDS = "title,year,citationCount"


# ── Helpers ───────────────────────────────────────────────────────────────────


def _load_fixture(name: str) -> dict | list:
    with open(FIXTURE_DIR / name) as fh:
        return json.load(fh)


# ── S2Error ───────────────────────────────────────────────────────────────────


def test_s2error_can_be_raised_and_caught() -> None:
    """S2Error is a proper Exception subclass."""
    with pytest.raises(S2Error, match="Something broke"):
        raise S2Error("Something broke", 500)


def test_s2error_stores_status_code() -> None:
    err = S2Error("Rate limited", 429)
    assert err.status_code == 429


def test_s2error_no_status_code() -> None:
    err = S2Error("Network failure")
    assert err.status_code is None


# ── fetch_paper ───────────────────────────────────────────────────────────────


@responses_lib.activate
def test_fetch_paper_success() -> None:
    fixture = _load_fixture("sample_s2_response.json")
    responses_lib.add(
        responses_lib.GET,
        f"{S2_GRAPH_BASE}/paper/{PAPER_ID}",
        json=fixture,
        status=200,
        match_querystring=False,
    )
    result = fetch_paper(PAPER_ID, FIELDS, headers={})
    assert result["title"] == "Attention Is All You Need"
    assert result["paperId"] == "204e3073870fae3d05bcbc2f6a8e263d9b72e776"


@responses_lib.activate
def test_fetch_paper_404() -> None:
    responses_lib.add(
        responses_lib.GET,
        f"{S2_GRAPH_BASE}/paper/arXiv:9999.99999",
        json={"error": "Paper not found"},
        status=404,
        match_querystring=False,
    )
    with pytest.raises(S2Error) as exc_info:
        fetch_paper("arXiv:9999.99999", FIELDS, headers={})
    assert exc_info.value.status_code == 404
    assert "not found" in str(exc_info.value).lower()


@responses_lib.activate
def test_fetch_paper_429_then_success() -> None:
    """Should retry on 429 and eventually succeed."""
    fixture = _load_fixture("sample_s2_response.json")
    responses_lib.add(
        responses_lib.GET,
        f"{S2_GRAPH_BASE}/paper/{PAPER_ID}",
        status=429,
        match_querystring=False,
    )
    responses_lib.add(
        responses_lib.GET,
        f"{S2_GRAPH_BASE}/paper/{PAPER_ID}",
        json=fixture,
        status=200,
        match_querystring=False,
    )
    # Patch sleep so the test doesn't actually wait
    with patch("literature.scripts.s2_client.time.sleep"):
        result = fetch_paper(PAPER_ID, FIELDS, headers={})
    assert result["title"] == "Attention Is All You Need"


@responses_lib.activate
def test_fetch_paper_429_exhausted() -> None:
    """Should raise S2Error after all retries fail with 429."""
    for _ in range(4):
        responses_lib.add(
            responses_lib.GET,
            f"{S2_GRAPH_BASE}/paper/{PAPER_ID}",
            status=429,
            match_querystring=False,
        )
    with patch("literature.scripts.s2_client.time.sleep"):
        with pytest.raises(S2Error) as exc_info:
            fetch_paper(PAPER_ID, FIELDS, headers={})
    assert exc_info.value.status_code == 429


def test_fetch_paper_network_error() -> None:
    """Should wrap requests.RequestException in S2Error."""
    with patch("requests.request", side_effect=requests.ConnectionError("timeout")):
        with pytest.raises(S2Error, match="Network error"):
            fetch_paper(PAPER_ID, FIELDS, headers={})


@responses_lib.activate
def test_fetch_paper_bare_arxiv_id_normalization() -> None:
    """Bare arXiv IDs like '1706.03762' must be prefixed as 'arXiv:1706.03762'."""
    fixture = _load_fixture("sample_s2_response.json")
    responses_lib.add(
        responses_lib.GET,
        f"{S2_GRAPH_BASE}/paper/arXiv:1706.03762",
        json=fixture,
        status=200,
        match_querystring=False,
    )
    # Pass the bare ID — should be normalised internally
    result = fetch_paper("1706.03762", FIELDS, headers={})
    assert result["paperId"] == "204e3073870fae3d05bcbc2f6a8e263d9b72e776"


# ── fetch_papers_batch ────────────────────────────────────────────────────────


@responses_lib.activate
def test_fetch_papers_batch_success_with_none_entries() -> None:
    fixture = _load_fixture("s2_batch_response.json")
    responses_lib.add(
        responses_lib.POST,
        f"{S2_GRAPH_BASE}/paper/batch",
        json=fixture,
        status=200,
        match_querystring=False,
    )
    ids = [S2_HEX_ID, "nonexistent000000000000000000000000000000", S2_HEX_ID2]
    results = fetch_papers_batch(ids, FIELDS, headers={})
    assert len(results) == 3
    assert results[0]["title"] == "Batch Paper"
    assert results[1] is None
    assert results[2]["title"] == "Second Paper"


def test_fetch_papers_batch_empty_list() -> None:
    """Empty input should return an empty list without hitting the network."""
    results = fetch_papers_batch([], FIELDS, headers={})
    assert results == []


@responses_lib.activate
def test_fetch_papers_batch_two_papers() -> None:
    responses_lib.add(
        responses_lib.POST,
        f"{S2_GRAPH_BASE}/paper/batch",
        json=[
            {"paperId": S2_HEX_ID, "title": "Paper A"},
            {"paperId": S2_HEX_ID2, "title": "Paper B"},
        ],
        status=200,
        match_querystring=False,
    )
    results = fetch_papers_batch([S2_HEX_ID, S2_HEX_ID2], FIELDS, headers={})
    assert len(results) == 2
    assert results[0]["title"] == "Paper A"
    assert results[1]["title"] == "Paper B"


# ── search_papers ─────────────────────────────────────────────────────────────


@responses_lib.activate
def test_search_papers_single_page() -> None:
    fixture = _load_fixture("s2_search_response.json")
    responses_lib.add(
        responses_lib.GET,
        f"{S2_GRAPH_BASE}/paper/search/bulk",
        json=fixture,
        status=200,
        match_querystring=False,
    )
    results = list(search_papers("transformers", FIELDS, headers={}))
    assert len(results) == 1
    assert results[0]["title"] == "Search Result Paper"


@responses_lib.activate
def test_search_papers_multi_page_pagination() -> None:
    """Should follow token-based pagination across two pages."""
    page1 = {
        "data": [{"paperId": "p1", "title": "Paper 1"}],
        "token": "next-page-token",
    }
    page2 = {
        "data": [{"paperId": "p2", "title": "Paper 2"}],
        "token": None,
    }
    responses_lib.add(
        responses_lib.GET,
        f"{S2_GRAPH_BASE}/paper/search/bulk",
        json=page1,
        status=200,
        match_querystring=False,
    )
    responses_lib.add(
        responses_lib.GET,
        f"{S2_GRAPH_BASE}/paper/search/bulk",
        json=page2,
        status=200,
        match_querystring=False,
    )
    results = list(search_papers("attention", FIELDS, headers={}))
    assert len(results) == 2
    assert results[0]["title"] == "Paper 1"
    assert results[1]["title"] == "Paper 2"


@responses_lib.activate
def test_search_papers_empty_results() -> None:
    responses_lib.add(
        responses_lib.GET,
        f"{S2_GRAPH_BASE}/paper/search/bulk",
        json={"data": [], "token": None},
        status=200,
        match_querystring=False,
    )
    results = list(search_papers("zzznomatchzzzz", FIELDS, headers={}))
    assert results == []


# ── recommend_papers ──────────────────────────────────────────────────────────


@responses_lib.activate
def test_recommend_papers_success() -> None:
    fixture = _load_fixture("s2_recommendations_response.json")
    responses_lib.add(
        responses_lib.GET,
        f"{S2_RECS_BASE}/papers/forpaper/{S2_HEX_ID}",
        json=fixture,
        status=200,
        match_querystring=False,
    )
    results = recommend_papers(S2_HEX_ID, FIELDS, headers={})
    assert len(results) == 1
    assert results[0]["title"] == "Test Recommended Paper"


@responses_lib.activate
def test_recommend_papers_error_in_200_body() -> None:
    """HTTP 200 with an 'error' key in the body must raise S2Error."""
    responses_lib.add(
        responses_lib.GET,
        f"{S2_RECS_BASE}/papers/forpaper/badid",
        json={"error": "Paper not found"},
        status=200,
        match_querystring=False,
    )
    with pytest.raises(S2Error, match="Paper not found"):
        recommend_papers("badid", FIELDS, headers={})


# ── recommend_multi ───────────────────────────────────────────────────────────


@responses_lib.activate
def test_recommend_multi_success() -> None:
    fixture = _load_fixture("s2_recommendations_response.json")
    responses_lib.add(
        responses_lib.POST,
        f"{S2_RECS_BASE}/papers/",
        json=fixture,
        status=200,
        match_querystring=False,
    )
    results = recommend_multi([S2_HEX_ID], [], FIELDS, headers={})
    assert len(results) == 1
    assert results[0]["title"] == "Test Recommended Paper"


@responses_lib.activate
def test_recommend_multi_error_in_200_body() -> None:
    """HTTP 200 with 'error' key must raise S2Error."""
    responses_lib.add(
        responses_lib.POST,
        f"{S2_RECS_BASE}/papers/",
        json={"error": "Invalid paper ID format"},
        status=200,
        match_querystring=False,
    )
    with pytest.raises(S2Error, match="Invalid paper ID format"):
        recommend_multi(["not-a-hex-id"], [], FIELDS, headers={})


# ── fetch_citations ───────────────────────────────────────────────────────────


@responses_lib.activate
def test_fetch_citations_success() -> None:
    fixture = _load_fixture("s2_citations_response.json")
    responses_lib.add(
        responses_lib.GET,
        f"{S2_GRAPH_BASE}/paper/{S2_HEX_ID}/citations",
        json=fixture,
        status=200,
        match_querystring=False,
    )
    results = fetch_citations(S2_HEX_ID, "title,year,citationCount,intents", headers={})
    assert len(results) == 1
    assert results[0]["citingPaper"]["title"] == "Citing Paper"


@responses_lib.activate
def test_fetch_citations_http_error() -> None:
    responses_lib.add(
        responses_lib.GET,
        f"{S2_GRAPH_BASE}/paper/{S2_HEX_ID}/citations",
        json={"message": "Internal server error"},
        status=500,
        match_querystring=False,
    )
    with pytest.raises(S2Error) as exc_info:
        fetch_citations(S2_HEX_ID, FIELDS, headers={})
    assert exc_info.value.status_code == 500


# ── fetch_references ──────────────────────────────────────────────────────────


@responses_lib.activate
def test_fetch_references_success() -> None:
    responses_lib.add(
        responses_lib.GET,
        f"{S2_GRAPH_BASE}/paper/{S2_HEX_ID}/references",
        json={
            "data": [
                {"citedPaper": {"paperId": S2_HEX_ID2, "title": "Referenced Paper"}}
            ]
        },
        status=200,
        match_querystring=False,
    )
    results = fetch_references(S2_HEX_ID, "title,year,contexts", headers={})
    assert len(results) == 1
    assert results[0]["citedPaper"]["title"] == "Referenced Paper"


@responses_lib.activate
def test_fetch_references_with_context_fields() -> None:
    """Verify references endpoint works with context/intent fields."""
    responses_lib.add(
        responses_lib.GET,
        f"{S2_GRAPH_BASE}/paper/{S2_HEX_ID}/references",
        json={
            "data": [
                {
                    "citedPaper": {"paperId": S2_HEX_ID2, "title": "Ref With Context"},
                    "contexts": ["We build on the method of ..."],
                    "intents": ["methodology"],
                }
            ]
        },
        status=200,
        match_querystring=False,
    )
    results = fetch_references(
        S2_HEX_ID, "title,year,contexts,intents", headers={}
    )
    assert results[0]["citedPaper"]["title"] == "Ref With Context"
    assert results[0]["contexts"] == ["We build on the method of ..."]
