#!/usr/bin/env python3
"""
Fetch paper metadata from Semantic Scholar and create paper files.

Usage:
    uv run python literature/scripts/enrich.py "https://arxiv.org/abs/1706.03762"
    uv run python literature/scripts/enrich.py "10.1145/3442188.3445922"
    uv run python literature/scripts/enrich.py --type blog "https://example.com/post" --title "My Post"
    uv run python literature/scripts/enrich.py --update vaswani2017attention
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


from literature.scripts.parse import (
    generate_citekey,
    normalize_paper_id,
    read_frontmatter,
    resolve_citekey_collision,
    write_paper_file,
)
from literature.scripts.s2_client import S2Error
from literature.scripts.s2_client import fetch_paper as s2_fetch_paper

# ── Constants ──────────────────────────────────────────────────────────────────

# Kept for backward compatibility (tests import this)
S2_BASE_URL = "https://api.semanticscholar.org/graph/v1/paper"
S2_FIELDS = (
    "title,abstract,authors,year,venue,publicationVenue,citationCount,"
    "referenceCount,fieldsOfStudy,tldr,externalIds,openAccessPdf,publicationDate,"
    "influentialCitationCount,s2FieldsOfStudy"
)

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PAPERS_DIR = REPO_ROOT / "literature" / "papers"
DEFAULT_RESOURCES_DIR = REPO_ROOT / "literature" / "resources"

NON_PAPER_TYPES = ("blog", "report", "talk", "code")
RESOURCE_TYPES = ("paper", "preprint", "blog", "report", "talk", "code")


# ── Internal exception ─────────────────────────────────────────────────────────


class _EnrichError(Exception):
    """Raised when enrichment fails; carries an exit code."""

    def __init__(self, message: str, code: int = 1) -> None:
        super().__init__(message)
        self.code = code


# ── Author formatting ──────────────────────────────────────────────────────────


def format_author_name(name: str) -> str:
    """Convert 'First Last' to 'Last, First' format.

    If the name already contains a comma it is returned unchanged.

    Args:
        name: Author name in either 'First Last' or 'Last, First' format.

    Returns:
        Author name in 'Last, First' format.
    """
    if "," in name:
        return name  # Already formatted
    parts = name.strip().split()
    if len(parts) <= 1:
        return name
    last = parts[-1]
    first = " ".join(parts[:-1])
    return f"{last}, {first}"


# ── Internal helper ────────────────────────────────────────────────────────────


def _fetch_s2_data(id_type: str, paper_id: str) -> dict[str, Any]:
    """Fetch paper metadata from S2 using the shared s2_client.

    Args:
        id_type: Either ``"arxiv"`` or ``"doi"``.
        paper_id: The normalized paper identifier.

    Returns:
        Parsed JSON response dict.

    Raises:
        _EnrichError: On 404, persistent 429, or other HTTP errors.
    """
    s2_prefix = "arXiv" if id_type == "arxiv" else "DOI"
    try:
        return s2_fetch_paper(f"{s2_prefix}:{paper_id}", fields=S2_FIELDS)
    except S2Error as exc:
        raise _EnrichError(str(exc)) from exc


# ── Frontmatter mapping ────────────────────────────────────────────────────────


def s2_to_frontmatter(s2_data: dict, citekey: str) -> dict:
    """Map a Semantic Scholar API response to paper frontmatter fields.

    Args:
        s2_data: Parsed S2 API JSON response.
        citekey: The resolved citekey for the paper.

    Returns:
        Dict ready to pass to ``write_paper_file``.
    """
    all_authors = [a["name"] for a in (s2_data.get("authors") or [])]
    et_al = len(all_authors) > 10
    authors = [format_author_name(n) for n in all_authors[:10]]

    external_ids = s2_data.get("externalIds") or {}
    arxiv_id: str = external_ids.get("ArXiv") or ""
    doi: str = external_ids.get("DOI") or ""

    # Prefer arXiv URL, fall back to DOI URL
    if arxiv_id:
        url = f"https://arxiv.org/abs/{arxiv_id}"
    elif doi:
        url = f"https://doi.org/{doi}"
    else:
        url = ""

    venue: str = (
        s2_data.get("venue")
        or (s2_data.get("publicationVenue") or {}).get("name", "")
        or ""
    )

    # Determine resource_type based on venue
    if not venue or "arxiv" in venue.lower():
        resource_type = "preprint"
    else:
        resource_type = "paper"

    tldr_obj = s2_data.get("tldr") or {}
    tldr: str = tldr_obj.get("text", "") if isinstance(tldr_obj, dict) else ""

    # influential citation count (always int, default 0)
    influential_citation_count: int = s2_data.get("influentialCitationCount") or 0

    # auto-tags from fieldsOfStudy + s2FieldsOfStudy
    raw_tags: list[str] = list(s2_data.get("fieldsOfStudy") or [])
    for entry in s2_data.get("s2FieldsOfStudy") or []:
        cat = entry.get("category", "")
        if cat:
            raw_tags.append(cat)
    tags = sorted({t.lower() for t in raw_tags if t})  # deduplicated, sorted, lowercased

    return {
        "abstract": s2_data.get("abstract") or "",
        "arxiv_id": arxiv_id,
        "authors": authors,
        "citation_count": s2_data.get("citationCount") or 0,
        "cited_by": [],
        "cites": [],
        "doc_id": citekey,
        "doi": doi,
        "et_al": et_al,
        "influential_citation_count": influential_citation_count,
        "pdf_path": "",
        "reading_status": {"global": "unread"},
        "related": [],
        "resource_type": resource_type,
        "s2_id": s2_data.get("paperId") or "",
        "tags": tags,
        "themes": [],
        "title": s2_data.get("title") or "",
        "tldr": tldr,
        "url": url,
        "venue": venue,
        "year": s2_data.get("year") or 0,
    }


# ── PDF detection ─────────────────────────────────────────────────────────────


def _find_pdf_for_paper(s2_data: dict, repo_root: Path) -> str:
    """Search for a matching PDF file and return its relative path from repo root.

    Searches ``{repo_root}/papers/{arxiv_id}.pdf`` for arXiv papers.

    Args:
        s2_data: Parsed S2 API JSON response containing ``externalIds``.
        repo_root: Absolute path to the repository root.

    Returns:
        Relative path string (e.g. ``"papers/2602.23784.pdf"``) if found,
        otherwise an empty string.
    """
    external_ids = s2_data.get("externalIds") or {}
    arxiv_id: str = external_ids.get("ArXiv") or ""
    doi: str = external_ids.get("DOI") or ""

    papers_dir = repo_root / "papers"

    if arxiv_id:
        candidate = papers_dir / f"{arxiv_id}.pdf"
        if candidate.exists():
            return str(candidate.relative_to(repo_root))

    if doi:
        doi_filename = doi.replace("/", "_").replace(":", "_")
        candidate = papers_dir / f"{doi_filename}.pdf"
        if candidate.exists():
            return str(candidate.relative_to(repo_root))

    return ""


# ── Resource ID generation ─────────────────────────────────────────────────────


def generate_resource_id(url: str, title: str) -> str:
    """Generate a doc_id for a non-paper resource.

    Sanitizes the title (preferred) or URL slug into a lowercase
    underscore-separated identifier.

    Args:
        url: Resource URL.
        title: Resource title.

    Returns:
        A lowercase, underscore-separated identifier string.
    """
    if title and title.lower() != "untitled":
        words = re.findall(r"[a-z0-9]+", title.lower())
        return "_".join(words[:5])

    parsed = urlparse(url)
    path_parts = [p for p in parsed.path.split("/") if p]
    slug = path_parts[-1] if path_parts else parsed.netloc.replace(".", "_")
    sanitized = re.sub(r"[^a-z0-9_]", "_", slug.lower())
    return re.sub(r"_+", "_", sanitized)[:40].rstrip("_")


# ── Internal operation handlers ────────────────────────────────────────────────


def _handle_update(citekey: str, papers_dir: Path) -> int:
    """Re-fetch S2 metadata and merge into an existing paper file."""
    paper_path = papers_dir / f"{citekey}.md"
    if not paper_path.exists():
        raise _EnrichError(f"Paper not found: {paper_path}")

    existing_meta, existing_body = read_frontmatter(paper_path)

    arxiv_id: str = str(existing_meta.get("arxiv_id") or "")
    doi: str = str(existing_meta.get("doi") or "")

    if arxiv_id:
        id_type, paper_id = "arxiv", arxiv_id
    elif doi:
        id_type, paper_id = "doi", doi
    else:
        raise _EnrichError(
            f"Cannot update {citekey!r}: no arxiv_id or doi in frontmatter."
        )

    s2_data = _fetch_s2_data(id_type, paper_id)

    # Merge: update only auto-enriched fields; preserve user-curated fields
    venue: str = (
        s2_data.get("venue")
        or (s2_data.get("publicationVenue") or {}).get("name", "")
        or str(existing_meta.get("venue", ""))
    )
    tldr_obj = s2_data.get("tldr") or {}
    tldr: str = tldr_obj.get("text", "") if isinstance(tldr_obj, dict) else ""

    updated_meta: dict = dict(existing_meta)
    updated_meta["citation_count"] = (
        s2_data.get("citationCount") or existing_meta.get("citation_count", 0)
    )
    updated_meta["venue"] = venue
    updated_meta["tldr"] = tldr
    updated_meta["abstract"] = s2_data.get("abstract") or existing_meta.get("abstract", "")

    write_paper_file(paper_path, updated_meta, existing_body)
    print(str(paper_path))
    return 0


def _handle_resource(
    url: str,
    resource_type: str,
    title: str | None,
    resources_dir: Path,
) -> int:
    """Create a non-paper resource file (blog, talk, code, report) without S2."""
    display_title = title or "Untitled"
    doc_id = generate_resource_id(url, display_title)

    meta: dict = {
        "doc_id": doc_id,
        "reading_status": {"global": "unread"},
        "resource_type": resource_type,
        "tags": [],
        "themes": [],
        "title": display_title,
        "url": url,
    }

    resources_dir.mkdir(parents=True, exist_ok=True)
    out_path = resources_dir / f"{doc_id}.md"
    write_paper_file(out_path, meta, "## Notes\n\n(Add your notes here)\n")
    print(str(out_path))
    return 0


def _handle_paper(
    input_str: str,
    custom_citekey: str | None,
    papers_dir: Path,
) -> int:
    """Fetch paper metadata from S2 and create a paper file."""
    try:
        id_type, paper_id = normalize_paper_id(input_str)
    except ValueError as exc:
        raise _EnrichError(f"Invalid URL/ID: {exc}") from exc

    s2_data = _fetch_s2_data(id_type, paper_id)

    # Validate required fields
    missing: list[str] = []
    if not s2_data.get("title"):
        missing.append("title")
    if not s2_data.get("authors"):
        missing.append("authors")
    if not s2_data.get("year"):
        missing.append("year")
    if missing:
        raise _EnrichError(
            f"Missing required fields from S2 response: {', '.join(missing)}"
        )

    # Build author list for citekey generation
    all_authors_raw = [a["name"] for a in s2_data["authors"]]
    authors_formatted = [format_author_name(n) for n in all_authors_raw[:10]]

    # Generate / override citekey
    citekey: str = (
        custom_citekey
        or generate_citekey(authors_formatted, s2_data["year"], s2_data["title"])
    )

    # Duplicate check (before collision resolution)
    base_path = papers_dir / f"{citekey}.md"
    if base_path.exists():
        print(
            f"Paper already exists at {base_path}. "
            "Use --update to refresh metadata."
        )
        return 0

    # Resolve collisions (in case different papers share the same base citekey)
    citekey = resolve_citekey_collision(citekey, papers_dir)
    paper_path = papers_dir / f"{citekey}.md"

    meta = s2_to_frontmatter(s2_data, citekey)
    pdf_path = _find_pdf_for_paper(s2_data, REPO_ROOT)
    if pdf_path:
        meta["pdf_path"] = pdf_path

    papers_dir.mkdir(parents=True, exist_ok=True)
    write_paper_file(paper_path, meta, "## Notes\n\n(Add your notes here)\n")
    print(str(paper_path))
    return 0


def enrich_paper(
    input_str: str,
    lit_root: Path,
    *,
    citekey: str | None = None,
    provenance: dict | None = None,
) -> Path:
    """Public API: enrich a single paper and return the created file path.

    Args:
        input_str: arXiv URL, DOI, or Semantic Scholar ID.
        lit_root: Root of the ``literature/`` directory.
        citekey: Optional custom citekey override.
        provenance: Optional provenance metadata dict. When provided, it is
            stored in the paper frontmatter under the ``provenance`` key.

    Returns:
        Path to the created (or existing) paper file.

    Raises:
        RuntimeError: If enrichment fails.
    """
    papers_dir = lit_root / "papers"
    papers_dir.mkdir(parents=True, exist_ok=True)

    try:
        id_type, paper_id = normalize_paper_id(input_str)
    except ValueError as exc:
        raise RuntimeError(f"Invalid URL/ID: {exc}") from exc

    try:
        s2_data = _fetch_s2_data(id_type, paper_id)
    except _EnrichError as exc:
        raise RuntimeError(str(exc)) from exc

    missing: list[str] = []
    if not s2_data.get("title"):
        missing.append("title")
    if not s2_data.get("authors"):
        missing.append("authors")
    if not s2_data.get("year"):
        missing.append("year")
    if missing:
        raise RuntimeError(
            f"Missing required fields from S2 response: {', '.join(missing)}"
        )

    all_authors_raw = [a["name"] for a in s2_data["authors"]]
    authors_formatted = [format_author_name(n) for n in all_authors_raw[:10]]

    resolved_citekey: str = (
        citekey
        or generate_citekey(authors_formatted, s2_data["year"], s2_data["title"])
    )

    paper_path = papers_dir / f"{resolved_citekey}.md"
    if paper_path.exists():
        return paper_path

    resolved_citekey = resolve_citekey_collision(resolved_citekey, papers_dir)
    paper_path = papers_dir / f"{resolved_citekey}.md"

    meta = s2_to_frontmatter(s2_data, resolved_citekey)
    pdf_path = _find_pdf_for_paper(s2_data, REPO_ROOT)
    if pdf_path:
        meta["pdf_path"] = pdf_path

    if provenance is not None:
        meta["provenance"] = provenance

    write_paper_file(paper_path, meta, "## Notes\n\n(Add your notes here)\n")
    return paper_path


# ── CLI ────────────────────────────────────────────────────────────────────────


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="enrich.py",
        description=(
            "Fetch paper metadata from Semantic Scholar and create paper files "
            "in the literature system."
        ),
    )
    parser.add_argument(
        "input",
        nargs="?",
        help="arXiv URL, DOI, or resource URL.",
    )
    parser.add_argument(
        "--type",
        choices=RESOURCE_TYPES,
        default=None,
        metavar="TYPE",
        help=(
            "Resource type: blog, talk, code, report, preprint, paper. "
            "When set to blog/talk/code/report, skips the S2 API call."
        ),
    )
    parser.add_argument(
        "--title",
        default=None,
        help="Title for non-paper resources (used with --type).",
    )
    parser.add_argument(
        "--update",
        metavar="CITEKEY",
        default=None,
        help="Update metadata for an existing paper by citekey.",
    )
    parser.add_argument(
        "--citekey",
        default=None,
        help="Override the auto-generated citekey.",
    )
    return parser


def run(
    argv: list[str] | None = None,
    *,
    papers_dir: Path | None = None,
    resources_dir: Path | None = None,
) -> int:
    """Run the enrich CLI and return an exit code.

    Args:
        argv: Argument list (defaults to ``sys.argv[1:]``).
        papers_dir: Override the papers directory (useful in tests).
        resources_dir: Override the resources directory (useful in tests).

    Returns:
        0 on success, 1 on failure.
    """
    _papers_dir = papers_dir or DEFAULT_PAPERS_DIR
    _resources_dir = resources_dir or DEFAULT_RESOURCES_DIR

    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.update is None and args.input is None:
        parser.error("Either provide an input URL/ID or use --update CITEKEY.")

    try:
        if args.update is not None:
            return _handle_update(args.update, _papers_dir)

        if args.type in NON_PAPER_TYPES:
            return _handle_resource(
                args.input, args.type, args.title, _resources_dir
            )

        return _handle_paper(args.input, args.citekey, _papers_dir)

    except _EnrichError as exc:
        print(str(exc), file=sys.stderr)
        return exc.code


def main() -> None:
    """CLI entry point."""
    sys.exit(run())


if __name__ == "__main__":
    main()
