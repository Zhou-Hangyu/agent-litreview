#!/usr/bin/env python3
"""lit — unified CLI for the literature v3 system.

Usage:
    lit <command> [options]
    uv run python literature/scripts/lit.py <command> [options]

Commands:
    rebuild         Sync markdown files into SQLite index
    search          BM25 full-text search across papers
    paper           Show paper details and summaries
    recommend       Get "what to read next" recommendations
    discover        Find new papers via S2 or arXiv RSS
    ask             Cross-paper synthesis (funnel retrieval)
    stats           Collection overview
    migrate         Import v1 papers into v3 schema
    add             Add a paper from URL (wraps enrich.py)
    status          Reading queue status
    ingest          Manage progressive summarization queue
    inbox           View/act on discovered papers
    init            Scaffold a new literature/ directory
    install-skill   Install agent SKILL.md to ~/.agents/skills/
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


from literature.scripts.rebuild_index import _find_literature_root


def _cmd_rebuild(args: argparse.Namespace, lit_root: Path) -> int:
    from literature.scripts.db import init_db, sync_from_markdown
    from literature.scripts.pagerank import compute_pagerank, store_pagerank_scores

    conn = init_db(lit_root)
    result = sync_from_markdown(lit_root, conn, verbose=True)

    scores = compute_pagerank(conn)
    store_pagerank_scores(conn, scores)

    conn.close()
    if getattr(args, "json", False):
        import json as _json
        print(_json.dumps(result))
    else:
        print(f"Rebuilt: {result['papers']} papers, {result['citations']} citations synced")
        if result["skipped"]:
            print(f"  ({result['skipped']} files skipped due to errors)")
    return 0


def _cmd_search(args: argparse.Namespace, lit_root: Path) -> int:
    """BM25 full-text search across papers (or similarity search)."""
    from literature.scripts.search import search, similar
    import json as _json

    top_k = getattr(args, "top_k", 20)

    if getattr(args, "similar", None):
        results = similar(args.similar, lit_root, top_k=top_k)
    else:
        query = getattr(args, "query", "")
        results = search(query, lit_root, top_k=top_k)

    if getattr(args, "json", False):
        print(_json.dumps(results, ensure_ascii=False))
    else:
        if not results:
            print("No results found.")
            return 0
        for r in results:
            status = r.get("reading_status", "unread") or "unread"
            year = r.get("year") or ""
            print(
                f"[{status:12s}] {r['paper_id']:<40s} ({year})  "
                f"{(r.get('title') or '')[:60]}"
            )
            if r.get("snippet"):
                print(f"             {r['snippet'][:80]}")
    return 0


def _cmd_paper(args: argparse.Namespace, lit_root: Path) -> int:
    """Stub: Show paper details and summaries."""
    print("lit paper: Not yet implemented. See Task 8 (paper_details).")
    return 0


def _cmd_recommend(args: argparse.Namespace, lit_root: Path) -> int:
    from literature.scripts.recommend import recommend_next
    import json as _json

    raw_args = getattr(args, "args", []) or []
    nums = [a for a in raw_args if a != "next"]
    top_k = int(nums[0]) if nums else 10
    results = recommend_next(lit_root, top_k=top_k)

    if getattr(args, "json", False):
        print(_json.dumps(results, ensure_ascii=False))
    else:
        if not results:
            print("No recommendations. All papers read or corpus empty.")
            return 0
        for r in results:
            bd = r.get("score_breakdown", {})
            print(f"[{r['score']:.3f}] {r['paper_id']:<40s} ({r['year']})")
            print(
                f"         pr={bd.get('project_relevance', 0):.2f} "
                f"cc={bd.get('co_citation', 0):.2f} "
                f"re={bd.get('recency', 0):.2f} "
                f"pa={bd.get('pagerank', 0):.2f}"
            )
    return 0


def _cmd_discover(args: argparse.Namespace, lit_root: Path) -> int:
    """Find new papers via S2 recommendations or arXiv RSS."""
    from literature.scripts.discover import discover_arxiv, discover_s2

    import json as _json

    source = getattr(args, "source", "all")
    limit = getattr(args, "limit", 20)
    found: list[dict] = []

    if source in ("s2", "all"):
        found.extend(discover_s2(lit_root, limit=limit))
    if source in ("arxiv", "all"):
        cats: list[str] = list((getattr(args, "categories", None) or "cs.LG").split(","))
        found.extend(discover_arxiv(lit_root, cats, limit=limit))

    if getattr(args, "json", False):
        print(_json.dumps(found))
    else:
        print(f"Discovered {len(found)} new papers added to inbox.")
    return 0


def _cmd_ask(args: argparse.Namespace, lit_root: Path) -> int:
    """Cross-paper synthesis via funnel retrieval."""
    from literature.scripts.synthesize import funnel_retrieve, format_funnel_output
    import json as _json

    depth = getattr(args, "depth", 2)
    result = funnel_retrieve(args.question, lit_root, depth=depth)

    if getattr(args, "json", False):
        print(_json.dumps(result, ensure_ascii=False))
    else:
        print(format_funnel_output(result))
    return 0


def _cmd_stats(args: argparse.Namespace, lit_root: Path) -> int:
    """Stub: Collection overview."""
    print("lit stats: Not yet implemented. See Task 12 (collection_stats).")
    return 0


def _cmd_generate(args: argparse.Namespace, lit_root: Path) -> int:
    """Generate LaTeX literature review from theme files."""
    from literature.scripts.generate_review import generate
    
    title = getattr(args, "title", "Literature Review")
    authors = getattr(args, "authors", "")
    abstract = getattr(args, "abstract", "A comprehensive literature review.")
    
    generate(lit_root, title=title, authors=authors, abstract=abstract)
    return 0


def _cmd_migrate(args: argparse.Namespace, lit_root: Path) -> int:
    """Import v1 papers into v3 schema."""
    from literature.scripts.migrate import migrate_from_v1
    import json as _json

    result = migrate_from_v1(lit_root)
    if getattr(args, "json", False):
        print(_json.dumps(result))
    else:
        print(f"Migration complete: {result['papers']} papers, {result['citations']} citations")
        if result["warnings"]:
            print("Warnings:")
            for w in result["warnings"]:
                print(w)
    return 0


def _cmd_add(args: argparse.Namespace, lit_root: Path) -> int:
    """Stub: Add a paper from URL (wraps enrich.py)."""
    print("lit add: Not yet implemented. See Task 14 (add_paper).")
    return 0


def _cmd_status(args: argparse.Namespace, lit_root: Path) -> int:
    """Stub: Reading queue status."""
    print("lit status: Not yet implemented. See Task 15 (reading_status).")
    return 0


def _cmd_ingest(args: argparse.Namespace, lit_root: Path) -> int:
    """Manage progressive summarization queue."""
    from literature.scripts.ingest import get_ingest_queue, get_ingest_status
    import json as _json

    if getattr(args, "show_status", False):
        status = get_ingest_status(lit_root)
        if getattr(args, "json", False):
            print(_json.dumps(status))
        else:
            print(f"L4 summaries: {status['l4_done']}/{status['total']} done ({status['l4_needed']} needed)")
            print(f"L2 summaries: {status['l2_done']}/{status['total']} done ({status['l2_needed']} needed)")
        return 0

    queue = get_ingest_queue(lit_root, level="l4")
    if getattr(args, "json", False):
        print(_json.dumps(queue))
    else:
        print(f"{len(queue)} papers need L4 summarization (by PageRank importance):")
        for item in queue[:20]:
            print(f"  [{item['pagerank_score']:.4f}] {item['paper_id']}: {item['title'][:60]}")
        if len(queue) > 20:
            print(f"  ... and {len(queue) - 20} more")
    return 0


def _cmd_inbox(args: argparse.Namespace, lit_root: Path) -> int:
    """View and act on discovered papers."""
    from literature.scripts.discover import add_from_inbox, get_inbox

    import json as _json

    action = getattr(args, "action", None)
    paper_id = getattr(args, "paper_id", None)

    if action == "add" and paper_id:
        citekey = add_from_inbox(int(paper_id), lit_root)
        print(f"Added: {citekey}")
        return 0

    if action == "dismiss" and paper_id:
        from literature.scripts.db import init_db

        db = init_db(lit_root)
        db.execute(
            "UPDATE discovery_inbox SET status = 'dismissed' WHERE id = ?",
            (int(paper_id),),
        )
        db.commit()
        print(f"Dismissed inbox item {paper_id}")
        return 0

    items = get_inbox(lit_root)
    if getattr(args, "json", False):
        print(_json.dumps(items))
    else:
        if not items:
            print("No pending discoveries in inbox.")
        else:
            for item in items:
                score = item.get("relevance_score", 0) or 0
                title = (item.get("title") or "")[:60]
                print(
                    f"[{score:.2f}] #{item['id']} {item['paper_id']}: {title}"
                )
    return 0


def _cmd_init(args: argparse.Namespace, _lit_root: Path) -> int:
    """Scaffold a new literature/ directory in the current project."""
    import shutil

    target = Path(getattr(args, "path", None) or ".") / "literature"
    if target.exists() and any(target.iterdir()):
        print(f"Error: {target} already exists and is not empty.")
        return 1

    # Find scaffold directory inside the installed package
    scaffold_dir = Path(__file__).resolve().parent.parent / "scaffold"
    if not scaffold_dir.exists():
        print(f"Error: scaffold directory not found at {scaffold_dir}")
        return 1

    target.mkdir(parents=True, exist_ok=True)

    # Copy scaffold contents
    for item in scaffold_dir.rglob("*"):
        rel = item.relative_to(scaffold_dir)
        dest = target / rel
        if item.is_dir():
            dest.mkdir(parents=True, exist_ok=True)
        else:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, dest)

    # Copy templates from the package
    templates_src = Path(__file__).resolve().parent.parent / "templates"
    if templates_src.exists():
        templates_dest = target / "templates"
        shutil.copytree(templates_src, templates_dest, dirs_exist_ok=True)

    print(f"Initialized literature/ at {target.resolve()}")
    print()
    print("Next steps:")
    print("  1. Edit literature/PURPOSE.md with your research goals")
    print("  2. Add papers:  lit add 'https://arxiv.org/abs/1706.03762'")
    print("  3. Build index: lit rebuild")
    print("  4. Get recommendations: lit recommend 5")
    print()
    print("For agent integration: lit install-skill")
    return 0


def _cmd_install_skill(args: argparse.Namespace, _lit_root: Path) -> int:
    """Install the SKILL.md file for agent integration."""
    import shutil

    skill_src = Path(__file__).resolve().parent.parent / "skill" / "SKILL.md"
    if not skill_src.exists():
        print(f"Error: SKILL.md not found at {skill_src}")
        return 1

    skill_dest = Path.home() / ".agents" / "skills" / "literature-review"
    skill_dest.mkdir(parents=True, exist_ok=True)

    shutil.copy2(skill_src, skill_dest / "SKILL.md")
    print(f"Installed SKILL.md to {skill_dest / 'SKILL.md'}")
    print("Agents will now auto-detect the literature-review skill.")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    """Build the argparse parser for the lit CLI."""
    parser = argparse.ArgumentParser(
        prog="lit",
        description="Literature v3 — agent-native paper management system",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="Path to literature/ directory (auto-detected if omitted)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output JSON instead of human-readable tables",
    )

    sub = parser.add_subparsers(dest="cmd", metavar="COMMAND")
    sub.required = False

    # rebuild
    p = sub.add_parser("rebuild", help="Sync markdown files into SQLite index")
    p.add_argument(
        "--fetch-embeddings",
        action="store_true",
        help="Also fetch SPECTER2 embeddings (requires S2_API_KEY)",
    )

    # search
    p = sub.add_parser("search", help="BM25 full-text search across papers")
    p.add_argument("query", help="Search query string")
    p.add_argument(
        "--top-k",
        type=int,
        default=20,
        help="Number of results (default: 20)",
    )
    p.add_argument(
        "--similar",
        metavar="CITEKEY",
        help="Find papers similar to this citekey instead of query",
    )

    # paper
    p = sub.add_parser("paper", help="Show paper details and summaries")
    p.add_argument("citekey", help="Paper citekey (e.g. vaswani2017attention)")

    # recommend
    p = sub.add_parser("recommend", help="Get reading recommendations")
    p.add_argument(
        "args",
        nargs="*",
        metavar="[next] N",
        help="Number of recommendations (default: 10). Accepts: 'recommend 5' or 'recommend next 5'",
    )

    # discover
    p = sub.add_parser("discover", help="Find new papers via S2 or arXiv RSS")
    p.add_argument(
        "--source",
        choices=["s2", "arxiv", "all"],
        default="all",
    )
    p.add_argument(
        "--categories",
        help="arXiv categories (comma-separated, e.g. cs.LG,q-fin.TR)",
    )
    p.add_argument("--limit", type=int, default=20)

    # ask
    p = sub.add_parser("ask", help="Cross-paper synthesis via funnel retrieval")
    p.add_argument("question", help="Question to answer from the literature")
    p.add_argument(
        "--depth",
        type=int,
        default=2,
        choices=[1, 2, 3, 4],
        help="Funnel depth: 1=L4 scan only, 4=full paper details (default: 2)",
    )

    # stats
    sub.add_parser("stats", help="Collection overview")

    # generate
    p = sub.add_parser("generate", help="Generate LaTeX literature review")
    p.add_argument("--title", default="Literature Review", help="Review title")
    p.add_argument("--authors", default="", help="Author names")
    p.add_argument("--abstract", default="A comprehensive literature review.", help="Abstract text")

    # migrate
    p = sub.add_parser("migrate", help="Import v1 papers into v3 schema")
    p.add_argument(
        "--from-v1",
        action="store_true",
        help="Migrate from v1 YAML-based system",
    )

    # add
    p = sub.add_parser("add", help="Add a paper from URL (wraps enrich.py)")
    p.add_argument("url", help="arXiv URL, DOI, or other URL")
    p.add_argument(
        "--type",
        dest="resource_type",
        choices=["paper", "preprint", "blog", "talk", "code", "report"],
        default=None,
    )
    p.add_argument("--citekey", default=None)

    # status
    sub.add_parser("status", help="Reading queue status")

    # ingest
    p = sub.add_parser("ingest", help="Manage progressive summarization queue")
    p.add_argument("--list", action="store_true", help="List papers needing summaries")
    p.add_argument(
        "--status",
        action="store_true",
        dest="show_status",
        help="Show ingestion progress",
    )

    # inbox
    p = sub.add_parser("inbox", help="View and act on discovered papers")
    p.add_argument(
        "action",
        nargs="?",
        choices=["add", "dismiss"],
        help="Action on a discovered paper",
    )
    p.add_argument("paper_id", nargs="?", help="Paper ID for add/dismiss actions")

    # init
    p = sub.add_parser("init", help="Scaffold a new literature/ directory")
    p.add_argument(
        "--path",
        type=str,
        default=None,
        help="Target directory (default: current working directory)",
    )

    # install-skill
    sub.add_parser("install-skill", help="Install agent SKILL.md to ~/.agents/skills/")

    return parser


def run(argv: list[str] | None = None, *, root: Path | None = None) -> int:
    """Run the lit CLI.

    Args:
        argv: Command-line arguments (default: sys.argv[1:]).
        root: Path to the literature/ directory; overrides ``--root`` flag.

    Returns:
        Exit code.
    """
    parser = _build_parser()
    args = parser.parse_args(argv)

    cmd = getattr(args, "cmd", None)

    # init and install-skill don't need a literature root
    if cmd == "init":
        return _cmd_init(args, Path.cwd())
    if cmd == "install-skill":
        return _cmd_install_skill(args, Path.cwd())

    if cmd is None:
        parser.print_help()
        return 0

    lit_root = root or args.root or _find_literature_root(Path.cwd())

    handlers = {
        "rebuild": _cmd_rebuild,
        "search": _cmd_search,
        "paper": _cmd_paper,
        "recommend": _cmd_recommend,
        "discover": _cmd_discover,
        "ask": _cmd_ask,
        "stats": _cmd_stats,
        "generate": _cmd_generate,
        "migrate": _cmd_migrate,
        "add": _cmd_add,
        "status": _cmd_status,
        "ingest": _cmd_ingest,
        "inbox": _cmd_inbox,
    }
    handler = handlers.get(cmd)
    if handler is None:
        parser.print_help()
        return 1
    return handler(args, lit_root)


def main() -> None:
    """Entry point for the lit CLI."""
    sys.exit(run())


if __name__ == "__main__":
    main()
