#!/usr/bin/env python3
"""Paper discovery CLI for the literature system.

Discovers new papers from Semantic Scholar via recommendations, search,
and citation gap analysis -- all without modifying the collection.

Usage:
    uv run python literature/scripts/scout.py recommend [--seeds k1,k2] [--limit N]
    uv run python literature/scripts/scout.py search "transformers attention" [--limit N]
    uv run python literature/scripts/scout.py gaps [--top N]
    uv run python literature/scripts/scout.py --root /path/to/lit/ search "query"
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


from ruamel.yaml import YAML

from literature.scripts.parse import read_frontmatter
from literature.scripts.s2_client import (
    S2Error,
    fetch_papers_batch,
    recommend_multi,
    recommend_papers,
    search_papers,
)

# ── Constants ──────────────────────────────────────────────────────────────────

TITLE_WIDTH: int = 60
MAX_RESULTS: int = 20


# ── Helpers ────────────────────────────────────────────────────────────────────


def _make_yaml() -> YAML:
    """Create a YAML instance for reading index files."""
    y = YAML()
    y.default_flow_style = False
    y.width = 4096
    return y


def _find_literature_root(start: Path | None = None) -> Path:
    """Search upward from *start* for a directory containing literature/AGENTS.md."""
    current = (start or Path.cwd()).resolve()
    for parent in [current, *current.parents]:
        candidate = parent / "literature" / "AGENTS.md"
        if candidate.is_file():
            return parent / "literature"
    return Path("./literature")


def _load_graph(lit_root: Path) -> dict:
    """Load graph.yaml from the index directory.

    Args:
        lit_root: Path to the literature/ directory.

    Returns:
        Dict with ``nodes`` and ``edges`` keys (or empty dict if not found).
    """
    path = lit_root / "index" / "graph.yaml"
    if not path.exists():
        return {}
    y = _make_yaml()
    data = y.load(path.read_text(encoding="utf-8"))
    return data or {"nodes": {}, "edges": []}


def _truncate(s: str, width: int) -> str:
    """Truncate *s* to *width* chars, appending ``...`` if cut."""
    if len(s) <= width:
        return s
    return s[: width - 3] + "..."


def _format_row(
    candidate_id: str, title: str, year: object, cites: int, extra: str = ""
) -> str:
    """Format one result row for compact tabular output."""
    title_col = _truncate(title, TITLE_WIDTH)
    year_str = str(year) if year is not None else ""
    row = f"{candidate_id:<30} {title_col:<{TITLE_WIDTH}} {year_str:>4} {cites:>6}"
    if extra:
        row += f"  {extra}"
    return row


def _load_collection_ids(papers_dir: Path) -> tuple[set[str], set[str]]:
    """Return (s2_ids, arxiv_ids) for all papers in collection.

    Args:
        papers_dir: Path to the papers/ directory.

    Returns:
        Tuple of (s2_ids set, arxiv_ids set).
    """
    s2_ids: set[str] = set()
    arxiv_ids: set[str] = set()
    if not papers_dir.is_dir():
        return s2_ids, arxiv_ids
    for f in papers_dir.glob("*.md"):
        meta, _ = read_frontmatter(f)
        if meta.get("s2_id"):
            s2_ids.add(str(meta["s2_id"]))
        if meta.get("arxiv_id"):
            arxiv_ids.add(str(meta["arxiv_id"]))
    return s2_ids, arxiv_ids


# ── Subcommands ────────────────────────────────────────────────────────────────


def _cmd_recommend(args: argparse.Namespace, lit_root: Path) -> int:
    """Recommend papers based on collection seeds."""
    papers_dir = lit_root / "papers"
    collection_s2_ids, collection_arxiv_ids = _load_collection_ids(papers_dir)

    # Select seed papers
    if args.seeds:
        seed_citekeys = [s.strip() for s in args.seeds.split(",")]
    else:
        # Default: top 5 by citation_count from collection
        all_papers: list[dict] = []
        if papers_dir.is_dir():
            for f in papers_dir.glob("*.md"):
                meta, _ = read_frontmatter(f)
                if meta:
                    all_papers.append(meta)
        sorted_papers = sorted(
            all_papers, key=lambda p: p.get("citation_count", 0) or 0, reverse=True
        )
        seed_citekeys = [
            str(p.get("doc_id", "")) for p in sorted_papers[:5] if p.get("s2_id")
        ]

    # Get s2_ids for seeds
    seed_s2_ids: list[str] = []
    for ck in seed_citekeys:
        if not ck:
            continue
        paper_file = papers_dir / f"{ck}.md"
        if not paper_file.exists():
            print(f"Warning: {ck} not found", file=sys.stderr)
            continue
        fm, _ = read_frontmatter(paper_file)
        if not fm.get("s2_id"):
            print(f"Warning: {ck} has no s2_id, skipping", file=sys.stderr)
            continue
        seed_s2_ids.append(str(fm["s2_id"]))

    if not seed_s2_ids:
        print("No valid seed papers found.", file=sys.stderr)
        return 1

    # Call S2 API
    fields = "paperId,title,year,citationCount,externalIds,authors"
    try:
        if len(seed_s2_ids) == 1:
            results = recommend_papers(
                seed_s2_ids[0], fields=fields, limit=args.limit, pool=args.pool
            )
        else:
            # Multi-seed: use other collection papers as negative seeds
            positive = seed_s2_ids
            negative = list(collection_s2_ids - set(seed_s2_ids))[:50]
            results = recommend_multi(positive, negative, fields=fields, limit=args.limit)
    except S2Error as exc:
        print(f"S2 API error: {exc}", file=sys.stderr)
        return 1

    # Filter out already-in-collection papers
    new_papers = [
        p
        for p in results
        if p.get("paperId") not in collection_s2_ids
        and (p.get("externalIds") or {}).get("ArXiv") not in collection_arxiv_ids
    ]

    if not new_papers:
        print("No new papers found.")
        return 0

    # Output compact table
    print(
        f"{'CANDIDATE':<30} {'TITLE':<{TITLE_WIDTH}} {'YEAR':>4} {'CITES':>6}"
    )
    print("-" * (30 + TITLE_WIDTH + 13))
    for p in new_papers[: args.limit]:
        arxiv = (p.get("externalIds") or {}).get("ArXiv", "")
        candidate_id = f"arXiv:{arxiv}" if arxiv else (p.get("paperId") or "")[:12]
        title = (p.get("title") or "")[: TITLE_WIDTH]
        year = p.get("year") or ""
        cites = p.get("citationCount") or 0
        print(f"{candidate_id:<30} {title:<{TITLE_WIDTH}} {year:>4} {cites:>6}")
    return 0


def _cmd_search(args: argparse.Namespace, lit_root: Path) -> int:
    """Search S2 for papers matching a query."""
    collection_s2_ids, collection_arxiv_ids = _load_collection_ids(
        lit_root / "papers"
    )

    fields = "paperId,title,year,citationCount,externalIds,authors"
    filters: dict = {}
    if hasattr(args, "year") and args.year:
        filters["publicationDateOrYear"] = args.year
    if hasattr(args, "venue") and args.venue:
        filters["venue"] = args.venue
    if hasattr(args, "min_citations") and args.min_citations:
        filters["minCitationCount"] = args.min_citations

    try:
        results = list(
            search_papers(
                query=args.query,
                fields=fields,
                sort=args.sort if hasattr(args, "sort") else "relevance",
                limit=args.limit,
                filters=filters or None,
            )
        )
    except S2Error as exc:
        print(f"S2 API error: {exc}", file=sys.stderr)
        return 1

    # Filter out already-in-collection papers
    new_papers = [
        p
        for p in results
        if p.get("paperId") not in collection_s2_ids
        and (p.get("externalIds") or {}).get("ArXiv") not in collection_arxiv_ids
    ]

    if not new_papers:
        print("No results found.")
        return 0

    # Output compact table
    print(
        f"{'CANDIDATE':<30} {'TITLE':<{TITLE_WIDTH}} {'YEAR':>4} {'CITES':>6}"
    )
    print("-" * (30 + TITLE_WIDTH + 13))
    for p in new_papers[: args.limit]:
        arxiv = (p.get("externalIds") or {}).get("ArXiv", "")
        candidate_id = f"arXiv:{arxiv}" if arxiv else (p.get("paperId") or "")[:12]
        title = (p.get("title") or "")[: TITLE_WIDTH]
        year = p.get("year") or ""
        cites = p.get("citationCount") or 0
        print(f"{candidate_id:<30} {title:<{TITLE_WIDTH}} {year:>4} {cites:>6}")
    return 0


def _cmd_gaps(args: argparse.Namespace, lit_root: Path) -> int:
    """Find citation gaps -- papers frequently cited but not in collection."""
    graph_data = _load_graph(lit_root)
    if not graph_data:
        print(
            "No graph.yaml found. Run rebuild_index.py first.", file=sys.stderr
        )
        return 1

    # Collect all papers in collection (citekeys)
    nodes_data = graph_data.get("nodes", {})
    collection_ids = set(nodes_data.keys())

    # Walk edges to find external references (cited papers not in collection)
    edges = graph_data.get("edges", [])
    cited_externally: dict[str, int] = {}  # target -> count of collection papers citing it
    cited_by_map: dict[str, list[str]] = {}  # target -> [citing citekeys]

    for edge in edges:
        target = str(edge.get("to", ""))
        source = str(edge.get("from", ""))
        if target and target not in collection_ids:
            cited_externally[target] = cited_externally.get(target, 0) + 1
            cited_by_map.setdefault(target, []).append(source)

    top_n = getattr(args, "top", 20)
    gaps = sorted(
        [(s2_id, count) for s2_id, count in cited_externally.items() if count >= 1],
        key=lambda x: x[1],
        reverse=True,
    )[:top_n]

    if not gaps:
        print("No citation gaps found.")
        return 0

    # Fetch metadata for top gap papers
    gap_ids = [g[0] for g in gaps]
    fields = "paperId,title,year,citationCount,externalIds"
    try:
        batch_results = fetch_papers_batch(gap_ids, fields=fields)
    except S2Error:
        batch_results = [None] * len(gap_ids)

    print(
        f"{'S2 ID':<15} {'TITLE':<{TITLE_WIDTH}} {'YEAR':>4} {'CITED BY':>8}"
    )
    print("-" * (15 + TITLE_WIDTH + 15))
    for (s2_id, count), meta in zip(gaps, batch_results):
        if meta:
            title = (meta.get("title") or s2_id)[: TITLE_WIDTH]
            year = meta.get("year") or ""
        else:
            title = s2_id[: TITLE_WIDTH]
            year = ""
        print(f"{s2_id[:15]:<15} {title:<{TITLE_WIDTH}} {year:>4} {count:>8}")
    return 0


# ── CLI entry point ────────────────────────────────────────────────────────────


def run(argv: list[str] | None = None, *, lit_root: Path | None = None) -> int:
    """Run the scout CLI.

    Args:
        argv: Command-line arguments (default: sys.argv[1:]).
        lit_root: Path to the literature/ directory; overrides ``--root`` flag.

    Returns:
        Exit code (0 for success, 1 for errors).
    """
    parser = argparse.ArgumentParser(
        prog="scout.py",
        description="Paper discovery for the literature system.",
    )
    parser.add_argument(
        "--root", type=Path, help="Path to literature/ directory"
    )
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    # recommend
    rec_p = subparsers.add_parser(
        "recommend", help="Get paper recommendations based on collection"
    )
    rec_p.add_argument("--seeds", help="Comma-separated citekeys to use as seeds")
    rec_p.add_argument("--limit", type=int, default=20)
    rec_p.add_argument(
        "--pool", default="all-cs", choices=["recent", "all-cs"]
    )

    # search
    srch_p = subparsers.add_parser("search", help="Search S2 for papers")
    srch_p.add_argument("query")
    srch_p.add_argument("--limit", type=int, default=20)
    srch_p.add_argument("--sort", default="citationCount:desc")
    srch_p.add_argument("--year", default=None)
    srch_p.add_argument("--venue", default=None)
    srch_p.add_argument("--min-citations", type=int, default=None, dest="min_citations")

    # gaps
    gaps_p = subparsers.add_parser("gaps", help="Find citation gaps")
    gaps_p.add_argument("--top", type=int, default=20)

    args = parser.parse_args(argv)
    if lit_root is None:
        lit_root = args.root or _find_literature_root()

    if args.subcommand == "recommend":
        return _cmd_recommend(args, lit_root)
    elif args.subcommand == "search":
        return _cmd_search(args, lit_root)
    elif args.subcommand == "gaps":
        return _cmd_gaps(args, lit_root)
    return 1


def main() -> None:
    """Entry point for the scout CLI."""
    sys.exit(run())


if __name__ == "__main__":
    main()
