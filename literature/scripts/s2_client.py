#!/usr/bin/env python3
"""Shared Semantic Scholar API client.

Provides low-level functions to fetch, search, and query papers from the
Semantic Scholar Graph API and Recommendations API. All public functions
accept an optional ``headers`` parameter to allow callers (especially tests)
to inject custom headers without relying on environment variables.

Typical usage::

    from literature.scripts.s2_client import fetch_paper, S2Error

    try:
        paper = fetch_paper("arXiv:1706.03762", fields="title,year,authors")
    except S2Error as exc:
        print(f"Failed: {exc}")
"""
from __future__ import annotations

import os
import re
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any


import requests

# ── Public constants ──────────────────────────────────────────────────────────

S2_GRAPH_BASE = "https://api.semanticscholar.org/graph/v1"
S2_RECS_BASE = "https://api.semanticscholar.org/recommendations/v1"
SPECTER2_FIELD = "embedding.specter_v2"

# Regex for bare arXiv IDs (e.g. "1706.03762" or "2301.00001v2")
_BARE_ARXIV_RE = re.compile(r"^\d{4}\.\d{4,5}(v\d+)?$")


# ── Custom exception ──────────────────────────────────────────────────────────


class S2Error(Exception):
    """Raised when a Semantic Scholar API call fails.

    Attributes:
        status_code: The HTTP status code if available, otherwise ``None``.
    """

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


# ── Internal helpers ──────────────────────────────────────────────────────────


def _get_default_headers() -> dict[str, str]:
    """Return default request headers, including API key if set in env.

    Returns:
        Dict with ``x-api-key`` header when ``S2_API_KEY`` env var is set,
        otherwise an empty dict.
    """
    headers: dict[str, str] = {}
    api_key = os.environ.get("S2_API_KEY")
    if api_key:
        headers["x-api-key"] = api_key
    return headers


def _request_with_backoff(
    method: str,
    url: str,
    headers: dict[str, str],
    **kwargs: Any,
) -> requests.Response:
    """Execute an HTTP request, retrying with exponential backoff on 429.

    Args:
        method: HTTP method string (``"GET"``, ``"POST"``, etc.).
        url: Fully-qualified request URL.
        headers: Headers dict to send with the request.
        **kwargs: Additional keyword arguments forwarded to
            :func:`requests.request`.

    Returns:
        The :class:`requests.Response` on success.

    Raises:
        S2Error: On network error, persistent 429, or any non-200/429 status.
    """
    backoff_waits = [0, 1, 2, 4]

    for attempt, wait in enumerate(backoff_waits):
        if wait:
            time.sleep(wait)
        try:
            response = requests.request(
                method, url, headers=headers, timeout=30, **kwargs
            )
        except requests.RequestException as exc:
            raise S2Error(f"Network error: {exc}") from exc

        if response.status_code == 429:
            if attempt < len(backoff_waits) - 1:
                continue
            raise S2Error("Rate limited. Try again in a few minutes.", 429)

        return response

    raise S2Error("Rate limited. Try again in a few minutes.", 429)


def _normalize_paper_id(paper_id: str) -> str:
    """Normalize a paper ID to the format expected by the S2 Graph API.

    Bare arXiv IDs (e.g. ``"1706.03762"``) are promoted to
    ``"arXiv:1706.03762"``.  All other ID formats (``"arXiv:..."``,
    ``"DOI:..."``, 40-char hex S2 IDs, DOI URLs) are returned unchanged.

    Args:
        paper_id: Raw paper identifier supplied by the caller.

    Returns:
        Normalized identifier string.
    """
    if _BARE_ARXIV_RE.match(paper_id):
        return f"arXiv:{paper_id}"
    return paper_id


# ── Public functions ──────────────────────────────────────────────────────────


def fetch_paper(
    paper_id: str,
    fields: str,
    headers: dict | None = None,
) -> dict:
    """Fetch a single paper's metadata from the Semantic Scholar Graph API.

    Accepts any identifier format recognised by the S2 API:
    ``"arXiv:1706.03762"``, ``"DOI:10.1234/..."``, a 40-character hex S2
    paper ID, or a bare arXiv version string like ``"1706.03762"`` (which is
    automatically normalised to ``"arXiv:1706.03762"``).

    Args:
        paper_id: Paper identifier in any supported format.
        fields: Comma-separated list of fields to return (e.g.
            ``"title,year,authors"``).
        headers: Optional dict of HTTP headers. When ``None`` the default
            headers (including any ``S2_API_KEY`` from the environment) are
            used.

    Returns:
        Parsed JSON response dict.

    Raises:
        S2Error: On 404, persistent 429, network error, or other HTTP errors.
    """
    if headers is None:
        headers = _get_default_headers()

    normalized_id = _normalize_paper_id(paper_id)
    url = f"{S2_GRAPH_BASE}/paper/{normalized_id}?fields={fields}"

    response = _request_with_backoff("GET", url, headers)

    if response.status_code == 404:
        raise S2Error(
            f"Paper not found: {normalized_id!r}. Check the ID format.",
            404,
        )
    if response.status_code != 200:
        raise S2Error(
            f"S2 API error: {response.status_code} {response.text}",
            response.status_code,
        )

    return response.json()


def fetch_papers_batch(
    paper_ids: list[str],
    fields: str,
    headers: dict | None = None,
) -> list[dict | None]:
    """Fetch up to 500 papers in a single batch POST request.

    The returned list is positional: index *i* corresponds to ``paper_ids[i]``.
    Papers that could not be found are represented as ``None``.

    Args:
        paper_ids: List of paper identifiers (any format accepted by S2).
            Maximum 500 per call.
        fields: Comma-separated list of fields to return.
        headers: Optional dict of HTTP headers; defaults to env-based headers.

    Returns:
        List of paper dicts (or ``None`` for not-found papers).

    Raises:
        S2Error: On HTTP error or network failure.
    """
    if headers is None:
        headers = _get_default_headers()

    if not paper_ids:
        return []

    url = f"{S2_GRAPH_BASE}/paper/batch?fields={fields}"
    response = _request_with_backoff(
        "POST", url, headers, json={"ids": paper_ids}
    )

    if response.status_code != 200:
        raise S2Error(
            f"S2 batch API error: {response.status_code} {response.text}",
            response.status_code,
        )

    return response.json()


def search_papers(
    query: str,
    fields: str,
    sort: str = "relevance",
    limit: int = 100,
    filters: dict | None = None,
    headers: dict | None = None,
) -> Iterator[dict]:
    """Search for papers via the S2 bulk search endpoint.

    Uses token-based pagination to yield up to *limit* papers.  Stops early
    when the API returns ``"token": null``, signalling that results are
    exhausted.

    Args:
        query: Free-text search query.
        fields: Comma-separated list of fields to return per paper.
        sort: Sort order (``"relevance"`` or ``"citationCount:desc"``).
        limit: Maximum total number of papers to yield.
        filters: Optional dict of additional query parameters (e.g.
            ``{"year": "2020-2023"}``).
        headers: Optional dict of HTTP headers; defaults to env-based headers.

    Yields:
        Individual paper dicts.

    Raises:
        S2Error: On HTTP error or network failure.
    """
    if headers is None:
        headers = _get_default_headers()

    params: dict[str, Any] = {
        "query": query,
        "fields": fields,
        "sort": sort,
    }
    if filters:
        params.update(filters)

    yielded = 0
    token: str | None = None

    while yielded < limit:
        page_params = dict(params)
        if token:
            page_params["token"] = token

        url = f"{S2_GRAPH_BASE}/paper/search/bulk"
        response = _request_with_backoff("GET", url, headers, params=page_params)

        if response.status_code != 200:
            raise S2Error(
                f"S2 search API error: {response.status_code} {response.text}",
                response.status_code,
            )

        data = response.json()
        papers = data.get("data", [])

        for paper in papers:
            if yielded >= limit:
                return
            yield paper
            yielded += 1

        token = data.get("token")
        if token is None:
            return


def recommend_papers(
    paper_id: str,
    fields: str,
    limit: int = 20,
    pool: str = "all-cs",
    headers: dict | None = None,
) -> list[dict]:
    """Fetch single-seed paper recommendations.

    Note: The Recommendations API can return HTTP 200 with an ``"error"``
    key in the JSON body.  This function raises :class:`S2Error` in that case.

    Args:
        paper_id: Seed paper identifier (any format accepted by S2).
        fields: Comma-separated list of fields to return per recommended paper.
        limit: Maximum number of recommendations to return.
        pool: Recommendation pool identifier (default ``"all-cs"``).
        headers: Optional dict of HTTP headers; defaults to env-based headers.

    Returns:
        List of recommended paper dicts.

    Raises:
        S2Error: On HTTP error, network failure, or error returned in body.
    """
    if headers is None:
        headers = _get_default_headers()

    url = f"{S2_RECS_BASE}/papers/forpaper/{paper_id}"
    params = {
        "fields": fields,
        "limit": limit,
        "from": pool,
    }
    response = _request_with_backoff("GET", url, headers, params=params)

    if response.status_code != 200:
        raise S2Error(
            f"S2 recommendations API error: {response.status_code} {response.text}",
            response.status_code,
        )

    body = response.json()
    # HTTP 200 can still carry an error payload
    if "error" in body:
        raise S2Error(f"S2 recommendations error: {body['error']}", 200)

    return body["recommendedPapers"]


def recommend_multi(
    positive_ids: list[str],
    negative_ids: list[str],
    fields: str,
    limit: int = 20,
    headers: dict | None = None,
) -> list[dict]:
    """Fetch multi-seed paper recommendations.

    **Important**: This endpoint only accepts 40-character hex S2 paper IDs.
    Passing ``"arXiv:..."`` or ``"DOI:..."`` prefixes will result in an error.

    Note: As with :func:`recommend_papers`, HTTP 200 with an ``"error"`` key
    in the body is treated as an error.

    Args:
        positive_ids: List of 40-char hex S2 IDs for positive seed papers.
        negative_ids: List of 40-char hex S2 IDs for negative seed papers.
        fields: Comma-separated list of fields to return.
        limit: Maximum number of recommendations to return.
        headers: Optional dict of HTTP headers; defaults to env-based headers.

    Returns:
        List of recommended paper dicts.

    Raises:
        S2Error: On HTTP error, network failure, or error returned in body.
    """
    if headers is None:
        headers = _get_default_headers()

    url = f"{S2_RECS_BASE}/papers/"
    params = {
        "fields": fields,
        "limit": limit,
    }
    body_payload = {
        "positivePaperIds": positive_ids,
        "negativePaperIds": negative_ids,
    }
    response = _request_with_backoff(
        "POST", url, headers, params=params, json=body_payload
    )

    if response.status_code != 200:
        raise S2Error(
            f"S2 multi-seed recommendations API error: {response.status_code} {response.text}",
            response.status_code,
        )

    body = response.json()
    if "error" in body:
        raise S2Error(f"S2 multi-seed recommendations error: {body['error']}", 200)

    return body["recommendedPapers"]


def fetch_citations(
    paper_id: str,
    fields: str,
    limit: int = 100,
    headers: dict | None = None,
) -> list[dict]:
    """Fetch papers that cite the given paper.

    Each returned dict has a ``"citingPaper"`` key containing the citing
    paper's metadata.

    Args:
        paper_id: Paper identifier in any format accepted by S2.
        fields: Comma-separated list of fields to return per citing paper.
        limit: Maximum number of citations to return.
        headers: Optional dict of HTTP headers; defaults to env-based headers.

    Returns:
        List of ``{"citingPaper": {...}}`` dicts.

    Raises:
        S2Error: On HTTP error or network failure.
    """
    if headers is None:
        headers = _get_default_headers()

    url = f"{S2_GRAPH_BASE}/paper/{paper_id}/citations"
    params = {
        "fields": fields,
        "limit": limit,
    }
    response = _request_with_backoff("GET", url, headers, params=params)

    if response.status_code != 200:
        raise S2Error(
            f"S2 citations API error: {response.status_code} {response.text}",
            response.status_code,
        )

    return response.json().get("data", [])


def fetch_references(
    paper_id: str,
    fields: str,
    limit: int = 100,
    headers: dict | None = None,
) -> list[dict]:
    """Fetch the references (papers cited by) the given paper.

    Each returned dict has a ``"citedPaper"`` key containing the referenced
    paper's metadata.

    Args:
        paper_id: Paper identifier in any format accepted by S2.
        fields: Comma-separated list of fields to return per referenced paper.
        limit: Maximum number of references to return.
        headers: Optional dict of HTTP headers; defaults to env-based headers.

    Returns:
        List of ``{"citedPaper": {...}}`` dicts.

    Raises:
        S2Error: On HTTP error or network failure.
    """
    if headers is None:
        headers = _get_default_headers()

    url = f"{S2_GRAPH_BASE}/paper/{paper_id}/references"
    params = {
        "fields": fields,
        "limit": limit,
    }
    response = _request_with_backoff("GET", url, headers, params=params)

    if response.status_code != 200:
        raise S2Error(
            f"S2 references API error: {response.status_code} {response.text}",
            response.status_code,
        )

    return response.json().get("data", [])
