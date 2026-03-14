#!/usr/bin/env python3
"""Compact query interface for the literature index.

Provides subcommands to search papers, list unread, show stats,
inspect a single paper, and find related papers -- all from the
pre-built index files without reading the full graph.yaml manually.

Usage:
    python literature/scripts/query.py search transformers
    python literature/scripts/query.py unread --tags ml,nlp
    python literature/scripts/query.py stats
    python literature/scripts/query.py paper vaswani2017attention
    python literature/scripts/query.py related vaswani2017attention
    python literature/scripts/query.py --root /path/to/literature/ stats
"""

from __future__ import annotations

import argparse
import sys
from io import StringIO
from pathlib import Path


from ruamel.yaml import YAML

from literature.scripts.parse import read_frontmatter

# ── Constants ──────────────────────────────────────────────────────────────────

TITLE_WIDTH: int = 60
MAX_RESULTS: int = 20
BODY_PREVIEW_CHARS: int = 500
STATUS_ORDER: tuple[str, ...] = ("unread", "skimmed", "read", "synthesized")


# ── YAML setup ─────────────────────────────────────────────────────────────────

def _make_yaml() -> YAML:
    """Create a YAML instance for reading index files."""
    y = YAML()
    y.default_flow_style = False
    y.width = 4096
    return y


# ── Helpers ────────────────────────────────────────────────────────────────────

def _find_literature_root(start: Path | None = None) -> Path:
    """Search upward from *start* for a directory containing literature/AGENTS.md."""
    current = (start or Path.cwd()).resolve()
    for parent in [current, *current.parents]:
        candidate = parent / "literature" / "AGENTS.md"
        if candidate.is_file():
            return parent / "literature"
    return Path("./literature")


def _load_graph(root: Path) -> dict:
    """Load graph.yaml from the index directory.

    Args:
        root: Path to the literature/ directory.

    Returns:
        Dict with ``nodes`` and ``edges`` keys.
    """
    path = root / "index" / "graph.yaml"
    y = _make_yaml()
    data = y.load(path.read_text(encoding="utf-8"))
    return data or {"nodes": {}, "edges": []}


def _load_status(root: Path) -> dict:
    """Load status.yaml from the index directory.

    Args:
        root: Path to the literature/ directory.

    Returns:
        Dict with ``global`` and per-collaborator status sections.
    """
    path = root / "index" / "status.yaml"
    y = _make_yaml()
    data = y.load(path.read_text(encoding="utf-8"))
    return data or {"global": {s: [] for s in STATUS_ORDER}}


def _load_embeddings(lit_root: Path) -> dict[str, list[float]]:
    """Load index/embeddings.yaml, return {citekey: vector}.
    
    Returns empty dict if file is missing.

    Args:
        lit_root: Path to the literature/ directory.

    Returns:
        Dict mapping citekey to embedding vector.
    """
    embeddings_path = lit_root / "index" / "embeddings.yaml"
    if not embeddings_path.exists():
        return {}
    yaml = _make_yaml()
    with embeddings_path.open(encoding="utf-8") as fh:
        data = yaml.load(fh) or {}
    return dict(data.get("vectors") or {})


def _get_paper_status(citekey: str, status_data: dict) -> str:
    """Get the global reading status for a citekey.

    Args:
        citekey: Paper citekey to look up.
        status_data: Loaded status.yaml contents.

    Returns:
        Status string; defaults to ``"unread"`` if not found.
    """
    g = status_data.get("global") or {}
    for s in STATUS_ORDER:
        if citekey in (g.get(s) or []):
            return s
    return "unread"


def _truncate(s: str, width: int) -> str:
    """Truncate *s* to *width* chars, appending ``...`` if cut.

    Args:
        s: Input string.
        width: Maximum character width.

    Returns:
        Possibly truncated string.
    """
    if len(s) <= width:
        return s
    return s[:width - 3] + "..."


def _format_row(citekey: str, title: str, year: object, status: str) -> str:
    """Format one result row for compact tabular output.

    Args:
        citekey: Paper citekey.
        title: Paper title (will be truncated to TITLE_WIDTH).
        year: Publication year.
        status: Reading status string.

    Returns:
        Single formatted line.
    """
    title_col = _truncate(title, TITLE_WIDTH)
    year_str = str(year) if year is not None else "????"
    return f"{citekey:<30}  {title_col:<{TITLE_WIDTH}}  {year_str}  {status}"


# ── Subcommands ────────────────────────────────────────────────────────────────

def cmd_search(keywords: list[str], root: Path) -> int:
    """Search papers by keyword match on title, abstract, tags, and tldr.

    Performs a case-insensitive substring search across all indexed nodes.
    Returns at most MAX_RESULTS results in compact table format.

    Args:
        keywords: Keywords joined into a single query string.
        root: Path to the literature/ directory.

    Returns:
        Exit code (always 0).
    """
    graph = _load_graph(root)
    status_data = _load_status(root)

    query = " ".join(keywords).lower()

    results: list[tuple[str, dict]] = []

    for citekey, node in (graph.get("nodes") or {}).items():
        parts: list[str] = [
            str(node.get("title") or ""),
            str(node.get("abstract") or ""),
            str(node.get("tldr") or ""),
        ]
        for tag in (node.get("tags") or []):
            parts.append(str(tag))

        haystack = " ".join(parts).lower()

        if query in haystack:
            results.append((citekey, node))
            if len(results) >= MAX_RESULTS:
                break

    for citekey, node in results:
        status = _get_paper_status(citekey, status_data)
        print(_format_row(
            citekey,
            str(node.get("title") or ""),
            node.get("year"),
            status,
        ))

    return 0


def cmd_unread(tags: list[str] | None, root: Path) -> int:
    """List all papers with global reading status ``unread``.

    Args:
        tags: Optional list of tags; only papers having at least one matching
            tag are printed.
        root: Path to the literature/ directory.

    Returns:
        Exit code (always 0).
    """
    graph = _load_graph(root)
    status_data = _load_status(root)

    unread_keys: list[str] = list(status_data.get("global", {}).get("unread") or [])
    nodes = graph.get("nodes") or {}

    for citekey in unread_keys:
        node = nodes.get(citekey) or {}

        if tags:
            paper_tags = [str(t) for t in (node.get("tags") or [])]
            if not any(t in paper_tags for t in tags):
                continue

        print(_format_row(
            citekey,
            str(node.get("title") or ""),
            node.get("year"),
            "unread",
        ))

    return 0


def cmd_stats(root: Path) -> int:
    """Print collection summary: paper counts, edge count, top tags.

    Args:
        root: Path to the literature/ directory.

    Returns:
        Exit code (always 0).
    """
    graph = _load_graph(root)
    status_data = _load_status(root)

    nodes = graph.get("nodes") or {}
    edges = graph.get("edges") or []
    g = status_data.get("global") or {}

    tag_counts: dict[str, int] = {}
    for node in nodes.values():
        for tag in (node.get("tags") or []):
            tag_str = str(tag)
            tag_counts[tag_str] = tag_counts.get(tag_str, 0) + 1

    top_tags = sorted(tag_counts.items(), key=lambda x: (-x[1], x[0]))[:10]

    print(f"Papers: {len(nodes)}")
    for s in STATUS_ORDER:
        count = len(g.get(s) or [])
        print(f"  {s}: {count}")
    print(f"Edges: {len(edges)}")
    if top_tags:
        print("Top tags:")
        for tag, count in top_tags:
            print(f"  {tag}: {count}")

    return 0


def cmd_paper(citekey: str, root: Path) -> int:
    """Print a paper's full frontmatter and first 500 chars of body notes.

    Args:
        citekey: The citekey of the paper to display.
        root: Path to the literature/ directory.

    Returns:
        Exit code (0 on success, 1 if not found).
    """
    paper_path = root / "papers" / f"{citekey}.md"

    if not paper_path.is_file():
        print(f"Error: paper not found: {citekey}", file=sys.stderr)
        return 1

    meta, body = read_frontmatter(paper_path)

    y = _make_yaml()
    stream = StringIO()
    y.dump(dict(meta), stream)
    print(stream.getvalue().rstrip())

    if body:
        print("---")
        preview = body[:BODY_PREVIEW_CHARS]
        print(preview.rstrip())
        if len(body) > BODY_PREVIEW_CHARS:
            print(f"... [{len(body) - BODY_PREVIEW_CHARS} more chars]")

    return 0


def cmd_related(citekey: str, root: Path) -> int:
    """Print papers connected to *citekey* via the citation graph (both directions).

    Output format per line: ``<direction>  <other_citekey>  <title>  (<type>)``
    where direction is ``cites`` (this paper → other) or ``cited_by``
    (other paper → this paper).

    Args:
        citekey: The paper to find connections for.
        root: Path to the literature/ directory.

    Returns:
        Exit code (0 on success, 1 if citekey not in index).
    """
    graph = _load_graph(root)
    nodes = graph.get("nodes") or {}
    edges = graph.get("edges") or []

    if citekey not in nodes:
        print(f"Error: paper not found: {citekey}", file=sys.stderr)
        return 1

    for edge in edges:
        src = str(edge.get("from") or "")
        tgt = str(edge.get("to") or "")
        rel_type = str(edge.get("type") or "")

        if src == citekey:
            other, direction = tgt, "cites"
        elif tgt == citekey:
            other, direction = src, "cited_by"
        else:
            continue

        other_node = nodes.get(other) or {}
        title = str(other_node.get("title") or other)
        print(f"{direction}  {other}  {title}  ({rel_type})")

    return 0


def cmd_similar(citekey: str, root: Path, top_k: int = 10) -> int:
    """Find papers semantically similar to a given paper using SPECTER2 embeddings.

    Args:
        citekey: The citekey of the query paper.
        root: Path to the literature/ directory.
        top_k: Number of results to return (default: 10).

    Returns:
        Exit code (0 on success, 1 if embeddings missing or paper not found).
    """
    from literature.scripts.cluster import find_nearest

    embeddings = _load_embeddings(root)
    if not embeddings:
        print(
            "No embeddings found. Run: uv run python literature/scripts/rebuild_index.py",
            file=sys.stderr,
        )
        return 1

    if citekey not in embeddings:
        print(f"Paper '{citekey}' not found in embeddings.", file=sys.stderr)
        return 1

    query_vector = embeddings[citekey]
    results = find_nearest(query_vector, embeddings, top_k=top_k + 1)
    # Exclude the query paper itself
    results = [(ck, score) for ck, score in results if ck != citekey][:top_k]

    if not results:
        print("No similar papers found.")
        return 0

    # Load paper metadata for output
    papers_dir = root / "papers"

    print(f"{'CITEKEY':<30} {'TITLE':<{TITLE_WIDTH}} {'YEAR':>4} {'SIM':>5}")
    print("-" * (30 + TITLE_WIDTH + 12))

    for ck, score in results:
        paper_file = papers_dir / f"{ck}.md"
        if paper_file.exists():
            meta, _ = read_frontmatter(paper_file)
            title = str(meta.get("title") or "")[:TITLE_WIDTH]
            year = meta.get("year") or ""
        else:
            title = f"({ck})"[:TITLE_WIDTH]
            year = ""
        print(f"{ck:<30} {title:<{TITLE_WIDTH}} {year:>4} {score:>5.3f}")

    return 0


# ── CLI ────────────────────────────────────────────────────────────────────────

def _build_parser() -> argparse.ArgumentParser:
    """Build the argparse parser for the query CLI."""
    parser = argparse.ArgumentParser(
        description="Query the literature index without reading the full graph.yaml.",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="Path to literature/ directory (default: auto-detect)",
    )

    subs = parser.add_subparsers(dest="command", required=True)

    # search
    p_search = subs.add_parser("search", help="Search papers by keyword")
    p_search.add_argument("keywords", nargs="+", help="Keywords to search for")

    # unread
    p_unread = subs.add_parser("unread", help="List unread papers")
    p_unread.add_argument(
        "--tags",
        default=None,
        help="Comma-separated tags to filter by",
    )

    # stats
    subs.add_parser("stats", help="Show collection statistics")

    # paper
    p_paper = subs.add_parser("paper", help="Show a paper's details")
    p_paper.add_argument("citekey", help="Citekey of the paper")

    # related
    p_related = subs.add_parser("related", help="Show papers related to a citekey")
    p_related.add_argument("citekey", help="Citekey of the paper")

    # similar
    p_similar = subs.add_parser("similar", help="Find papers similar by SPECTER2 embedding")
    p_similar.add_argument("citekey", help="Citekey of the query paper")
    p_similar.add_argument("--top", type=int, default=10, help="Number of results (default: 10)")

    return parser


def run(argv: list[str] | None = None, *, root: Path | None = None) -> int:
    """Run the query CLI.

    Args:
        argv: Command-line arguments (default: sys.argv[1:]).
        root: Path to the literature/ directory; overrides ``--root`` flag.

    Returns:
        Exit code.
    """
    parser = _build_parser()
    args = parser.parse_args(argv)

    effective_root = root or args.root or _find_literature_root()

    if args.command == "search":
        return cmd_search(args.keywords, effective_root)
    if args.command == "unread":
        tags = [t.strip() for t in args.tags.split(",")] if args.tags else None
        return cmd_unread(tags, effective_root)
    if args.command == "stats":
        return cmd_stats(effective_root)
    if args.command == "paper":
        return cmd_paper(args.citekey, effective_root)
    if args.command == "related":
        return cmd_related(args.citekey, effective_root)
    if args.command == "similar":
        return cmd_similar(args.citekey, effective_root, top_k=args.top)

    return 0  # unreachable but satisfies mypy


def main() -> None:
    """Entry point for the query CLI."""
    sys.exit(run())


if __name__ == "__main__":
    main()
