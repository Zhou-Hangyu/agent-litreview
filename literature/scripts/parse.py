"""
YAML frontmatter parser and citekey utilities for the literature system.

Provides functions to read/write paper metadata files with YAML frontmatter,
generate citekeys, resolve collisions, and normalize paper identifiers.
"""

from __future__ import annotations

import re
import sys
import unicodedata
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path

from ruamel.yaml import YAML
from ruamel.yaml.scalarstring import DoubleQuotedScalarString

# ── Constants ──────────────────────────────────────────────────────────────────

STOP_WORDS: frozenset[str] = frozenset({
    "a", "an", "the", "of", "in", "on", "at", "to",
    "for", "with", "and", "or", "but", "is", "are", "was", "were",
})

_ARXIV_URL_RE = re.compile(
    r"https?://arxiv\.org/(?:abs|pdf)/(\d{4}\.\d{4,5})(?:v\d+)?(?:\.pdf)?",
    re.IGNORECASE,
)
_ARXIV_PREFIX_RE = re.compile(
    r"arxiv:(\d{4}\.\d{4,5})(?:v\d+)?",
    re.IGNORECASE,
)
_BARE_ARXIV_RE = re.compile(
    r"^(\d{4}\.\d{4,5})(?:v\d+)?$",
)
_DOI_URL_RE = re.compile(
    r"https?://doi\.org/(10\.\d{4,9}/\S+)",
    re.IGNORECASE,
)
_BARE_DOI_RE = re.compile(
    r"^(10\.\d{4,9}/\S+)$",
)
_LATEX_MATH_RE = re.compile(r"\$[^$]+\$")


# ── YAML setup ─────────────────────────────────────────────────────────────────

def _make_yaml() -> YAML:
    """Create a YAML 1.2 instance with safe round-trip settings."""
    y = YAML()
    y.default_flow_style = False
    y.preserve_quotes = True
    y.width = 4096  # avoid unwanted line wrapping
    return y


# ── Public API ─────────────────────────────────────────────────────────────────

def read_frontmatter(path: Path) -> tuple[dict, str]:
    """Parse YAML frontmatter and body from a markdown file.

    Args:
        path: Path to a markdown file with optional ``---`` delimited frontmatter.

    Returns:
        A ``(metadata, body)`` tuple.  If the file has no frontmatter delimiters
        the metadata dict is empty and the full content is returned as body.
    """
    text = path.read_text(encoding="utf-8")

    if not text.startswith("---"):
        return {}, text

    # Find the closing delimiter
    end_idx = text.find("---", 3)
    if end_idx == -1:
        return {}, text

    yaml_block = text[3:end_idx].strip()
    body = text[end_idx + 3:].lstrip("\n")

    y = _make_yaml()
    data = y.load(yaml_block)
    if data is None:
        data = {}

    # Convert ruamel CommentedMap to plain dict for easier consumption
    metadata: dict = dict(data)
    return metadata, body


def write_paper_file(path: Path, metadata: dict, body: str = "") -> None:
    """Write a markdown file with YAML frontmatter.

    Args:
        path: Destination file path.
        metadata: Dict of frontmatter fields.  The ``title`` field is always
            double-quoted in the output YAML.
        body: Optional markdown body written after the closing ``---``.
    """
    y = _make_yaml()

    # Sort keys alphabetically for deterministic output
    sorted_meta: dict = {}
    for key in sorted(metadata.keys()):
        value = metadata[key]
        # Always quote the title field
        if key == "title" and isinstance(value, str):
            value = DoubleQuotedScalarString(value)
        sorted_meta[key] = value

    stream = StringIO()
    y.dump(sorted_meta, stream)
    yaml_str = stream.getvalue()

    parts = ["---\n", yaml_str, "---\n"]
    if body:
        parts.append(body)

    path.write_text("".join(parts), encoding="utf-8")


def generate_citekey(authors: list[str], year: int, title: str) -> str:
    """Generate a citekey in ``{lastname}{year}{titleword}`` format.

    Args:
        authors: List of author names in ``"Last, First"`` or ``"First Last"``
            format.
        year: Publication year.
        title: Paper title.  LaTeX math (``$...$``) is stripped and stop words
            are skipped.

    Returns:
        Lowercase citekey, e.g. ``"vaswani2017attention"``.
    """
    # Extract first author's last name
    first_author = authors[0] if authors else "unknown"
    lastname = _extract_lastname(first_author)
    lastname = _transliterate(lastname).lower()

    # Process title: strip LaTeX math, then find first significant word
    clean_title = _LATEX_MATH_RE.sub("", title)
    words = re.findall(r"[A-Za-z]+", clean_title)
    title_word = ""
    for word in words:
        if word.lower() not in STOP_WORDS:
            title_word = word.lower()
            break

    return f"{lastname}{year}{title_word}"


def resolve_citekey_collision(citekey: str, existing_dir: Path) -> str:
    """Return a unique citekey by appending a suffix letter if needed.

    Checks ``existing_dir`` for ``{citekey}.md``.  If it exists, tries
    ``{citekey}b`` through ``{citekey}z``.

    Args:
        citekey: Base citekey to check.
        existing_dir: Directory containing existing paper ``.md`` files.

    Returns:
        The first available citekey (possibly unchanged).
    """
    if not (existing_dir / f"{citekey}.md").exists():
        return citekey

    for suffix in "bcdefghijklmnopqrstuvwxyz":
        candidate = f"{citekey}{suffix}"
        if not (existing_dir / f"{candidate}.md").exists():
            return candidate

    # Extremely unlikely — fall through
    print(
        f"Warning: exhausted citekey suffixes for {citekey!r}",
        file=sys.stderr,
    )
    return f"{citekey}z"


def normalize_paper_id(input_str: str) -> tuple[str, str]:
    """Normalize an arXiv URL/ID or DOI to a canonical ``(id_type, id)`` pair.

    Args:
        input_str: An arXiv URL, ``arXiv:`` prefixed ID, bare arXiv ID,
            DOI URL, or bare DOI string.

    Returns:
        ``("arxiv", normalized_id)`` or ``("doi", normalized_doi)``.

    Raises:
        ValueError: If the input cannot be recognized as arXiv or DOI.
    """
    s = input_str.strip()

    # arXiv URL (abs or pdf, with optional version)
    m = _ARXIV_URL_RE.match(s)
    if m:
        return ("arxiv", m.group(1))

    # arXiv: prefix
    m = _ARXIV_PREFIX_RE.match(s)
    if m:
        return ("arxiv", m.group(1))

    # DOI URL
    m = _DOI_URL_RE.match(s)
    if m:
        return ("doi", m.group(1))

    # Bare DOI (must start with 10.)
    m = _BARE_DOI_RE.match(s)
    if m:
        return ("doi", m.group(1))

    # Bare arXiv ID (YYMM.NNNNN)
    m = _BARE_ARXIV_RE.match(s)
    if m:
        return ("arxiv", m.group(1))

    raise ValueError(f"Unrecognized paper identifier: {input_str!r}")


def set_summary(meta: dict, level: str, content: str | list[str], model_name: str) -> None:
    """Write a summary with provenance into the meta dict (in-place).

    Stores LLM-generated summaries in the frontmatter with full provenance tracking.
    The ``summaries`` field is a nested dict mapping summary level to metadata.

    Args:
        meta: Paper frontmatter dict (modified in place).
        level: Summary level — ``'l4'`` (one-liner text) or ``'l2'`` (list of claim strings).
        content: For ``'l4'``: a single string. For ``'l2'``: list of strings.
        model_name: Name of the LLM that generated this (e.g. ``'claude-opus-4-6'``).

    Raises:
        ValueError: If ``level`` is not ``'l4'`` or ``'l2'``.

    Example:
        >>> meta = {"doc_id": "test2024paper"}
        >>> set_summary(meta, "l4", "A paper about transformers.", "claude-opus-4-6")
        >>> meta["summaries"]["l4"]["text"]
        'A paper about transformers.'
        >>> meta["summaries"]["l4"]["model"]
        'claude-opus-4-6'
    """
    if "summaries" not in meta:
        meta["summaries"] = {}

    entry: dict = {
        "model": model_name,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

    if level == "l4":
        entry["text"] = str(content)
    elif level == "l2":
        entry["claims"] = list(content)  # type: ignore
    else:
        raise ValueError(f"Unknown summary level: {level!r}. Use 'l4' or 'l2'.")

    meta["summaries"][level] = entry


def get_summary(meta: dict, level: str) -> dict | None:
    """Return summary dict for given level, or None if not present.

    Retrieves a stored summary by level. Returns the full summary entry
    (including ``text``/``claims``, ``model``, and ``generated_at``).

    Args:
        meta: Paper frontmatter dict.
        level: Summary level — ``'l4'`` or ``'l2'``.

    Returns:
        A dict with ``text``/``claims``, ``model``, and ``generated_at`` keys,
        or ``None`` if the summary level is not present.

    Example:
        >>> meta = {"summaries": {"l4": {"text": "...", "model": "...", "generated_at": "..."}}}
        >>> get_summary(meta, "l4")
        {'text': '...', 'model': '...', 'generated_at': '...'}
        >>> get_summary(meta, "l2")
        None
    """
    return (meta.get("summaries") or {}).get(level)


def is_summary_stale(meta: dict, level: str, max_age_days: int = 90) -> bool:
    """Return True if summary is missing or older than max_age_days.

    Checks whether a summary exists and is recent. A summary is considered stale if:
    - It is not present in the metadata, or
    - Its ``generated_at`` timestamp is older than ``max_age_days``, or
    - The timestamp cannot be parsed.

    Args:
        meta: Paper frontmatter dict.
        level: Summary level — ``'l4'`` or ``'l2'``.
        max_age_days: Maximum age in days before a summary is considered stale (default 90).

    Returns:
        ``True`` if the summary is missing, unparseable, or stale; ``False`` if fresh.

    Example:
        >>> meta = {"summaries": {"l4": {"text": "...", "model": "...", "generated_at": "2026-03-14T00:00:00Z"}}}
        >>> is_summary_stale(meta, "l4", max_age_days=90)
        False
        >>> is_summary_stale(meta, "l2", max_age_days=90)
        True
    """
    summary = get_summary(meta, level)
    if not summary or not summary.get("generated_at"):
        return True

    try:
        generated = datetime.fromisoformat(summary["generated_at"].replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - generated).days > max_age_days
    except (ValueError, TypeError):
        return True


# ── Internal helpers ───────────────────────────────────────────────────────────

def _extract_lastname(author: str) -> str:
    """Extract the last name from ``"Last, First"`` or ``"First Last"`` format."""
    if "," in author:
        return author.split(",")[0].strip()
    parts = author.strip().split()
    return parts[-1] if parts else "unknown"


def _transliterate(s: str) -> str:
    """Transliterate non-ASCII characters to closest ASCII equivalents."""
    nfkd = unicodedata.normalize("NFKD", s)
    return nfkd.encode("ascii", "ignore").decode()
