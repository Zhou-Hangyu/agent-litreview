"""
Batch updates to paper files (reading status, tags, themes).

Usage:
    python literature/scripts/update.py status <value> <citekey1> [citekey2 ...]
    python literature/scripts/update.py tags add <tags> <citekey1> [citekey2 ...]
    python literature/scripts/update.py tags remove <tags> <citekey1> [citekey2 ...]
    python literature/scripts/update.py themes add <themes> <citekey1> [citekey2 ...]
    python literature/scripts/update.py themes remove <themes> <citekey1> [citekey2 ...]

Examples:
    python literature/scripts/update.py status read paper1 paper2
    python literature/scripts/update.py tags add "diffusion,lob" paper1 paper2
    python literature/scripts/update.py themes remove "transformers" paper1
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


from literature.scripts.parse import read_frontmatter, write_paper_file

# ── Constants ──────────────────────────────────────────────────────────────────

VALID_STATUSES: tuple[str, ...] = ("unread", "skimmed", "read", "synthesized")


# ── Helpers ────────────────────────────────────────────────────────────────────


def _find_literature_root(start: Path | None = None) -> Path:
    """Search upward from *start* for a directory containing literature/AGENTS.md."""
    current = (start or Path.cwd()).resolve()
    for parent in [current, *current.parents]:
        candidate = parent / "literature" / "AGENTS.md"
        if candidate.is_file():
            return parent / "literature"
    return Path("./literature")


def _find_paper(root: Path, citekey: str) -> Path | None:
    """Locate a paper file by citekey, searching papers/ then resources/."""
    for subdir in ("papers", "resources"):
        p = root / subdir / f"{citekey}.md"
        if p.is_file():
            return p
    return None


def _parse_items(items_str: str) -> list[str]:
    """Split a comma-separated string into a list of stripped, non-empty strings."""
    return [item.strip() for item in items_str.split(",") if item.strip()]


def _resolve_papers(
    root: Path,
    citekeys: list[str],
) -> tuple[dict[str, Path], list[str]]:
    """Resolve citekeys to paths, returning (found_map, missing_keys)."""
    found: dict[str, Path] = {}
    missing: list[str] = []
    for citekey in citekeys:
        path = _find_paper(root, citekey)
        if path is None:
            missing.append(citekey)
        else:
            found[citekey] = path
    return found, missing


# ── Subcommand handlers ────────────────────────────────────────────────────────


def _cmd_status(args: argparse.Namespace, root: Path) -> int:
    """Set reading_status.global for one or more papers."""
    value: str = args.value
    if value not in VALID_STATUSES:
        print(
            f"Error: invalid status {value!r}. "
            f"Must be one of: {', '.join(VALID_STATUSES)}",
            file=sys.stderr,
        )
        return 1

    found, missing = _resolve_papers(root, args.citekeys)
    exit_code = 0

    if missing:
        for key in missing:
            print(f"Error: citekey {key!r} not found", file=sys.stderr)
        exit_code = 1

    for citekey, path in found.items():
        meta, body = read_frontmatter(path)
        rs = meta.get("reading_status")
        if not isinstance(rs, dict):
            rs = {}
        rs["global"] = value
        meta["reading_status"] = rs
        write_paper_file(path, meta, body)
        print(str(path))

    return exit_code


def _cmd_tags_add(args: argparse.Namespace, root: Path) -> int:
    """Add comma-separated tags to one or more papers (no duplicates)."""
    new_items = _parse_items(args.items)
    found, missing = _resolve_papers(root, args.citekeys)
    exit_code = 0

    if missing:
        for key in missing:
            print(f"Error: citekey {key!r} not found", file=sys.stderr)
        exit_code = 1

    for citekey, path in found.items():
        meta, body = read_frontmatter(path)
        existing = [str(t) for t in (meta.get("tags") or [])]
        for item in new_items:
            if item not in existing:
                existing.append(item)
        meta["tags"] = existing
        write_paper_file(path, meta, body)
        print(str(path))

    return exit_code


def _cmd_tags_remove(args: argparse.Namespace, root: Path) -> int:
    """Remove comma-separated tags from one or more papers."""
    remove_items = set(_parse_items(args.items))
    found, missing = _resolve_papers(root, args.citekeys)
    exit_code = 0

    if missing:
        for key in missing:
            print(f"Error: citekey {key!r} not found", file=sys.stderr)
        exit_code = 1

    for citekey, path in found.items():
        meta, body = read_frontmatter(path)
        existing = [str(t) for t in (meta.get("tags") or [])]
        meta["tags"] = [t for t in existing if t not in remove_items]
        write_paper_file(path, meta, body)
        print(str(path))

    return exit_code


def _cmd_themes_add(args: argparse.Namespace, root: Path) -> int:
    """Add comma-separated themes to one or more papers (no duplicates)."""
    new_items = _parse_items(args.items)
    found, missing = _resolve_papers(root, args.citekeys)
    exit_code = 0

    if missing:
        for key in missing:
            print(f"Error: citekey {key!r} not found", file=sys.stderr)
        exit_code = 1

    for citekey, path in found.items():
        meta, body = read_frontmatter(path)
        existing = [str(t) for t in (meta.get("themes") or [])]
        for item in new_items:
            if item not in existing:
                existing.append(item)
        meta["themes"] = existing
        write_paper_file(path, meta, body)
        print(str(path))

    return exit_code


def _cmd_themes_remove(args: argparse.Namespace, root: Path) -> int:
    """Remove comma-separated themes from one or more papers."""
    remove_items = set(_parse_items(args.items))
    found, missing = _resolve_papers(root, args.citekeys)
    exit_code = 0

    if missing:
        for key in missing:
            print(f"Error: citekey {key!r} not found", file=sys.stderr)
        exit_code = 1

    for citekey, path in found.items():
        meta, body = read_frontmatter(path)
        existing = [str(t) for t in (meta.get("themes") or [])]
        meta["themes"] = [t for t in existing if t not in remove_items]
        write_paper_file(path, meta, body)
        print(str(path))

    return exit_code


# ── CLI setup ──────────────────────────────────────────────────────────────────


def _build_parser() -> argparse.ArgumentParser:
    """Build the argparse parser for the update CLI."""
    parser = argparse.ArgumentParser(
        description="Batch updates to paper files (status, tags, themes).",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="Path to literature/ directory (default: auto-detect)",
    )
    subparsers = parser.add_subparsers(dest="command")

    # ── status subcommand ──────────────────────────────────────────────────────
    status_p = subparsers.add_parser(
        "status",
        help="Set reading_status.global for one or more papers.",
    )
    status_p.add_argument(
        "value",
        metavar="value",
        help=f"Status value: {', '.join(VALID_STATUSES)}",
    )
    status_p.add_argument(
        "citekeys",
        nargs="+",
        metavar="citekey",
        help="One or more paper citekeys.",
    )

    # ── tags subcommand ────────────────────────────────────────────────────────
    tags_p = subparsers.add_parser("tags", help="Add or remove tags.")
    tags_sub = tags_p.add_subparsers(dest="action")

    tags_add_p = tags_sub.add_parser("add", help="Add tags.")
    tags_add_p.add_argument(
        "items",
        metavar="tags",
        help="Comma-separated tags to add.",
    )
    tags_add_p.add_argument(
        "citekeys",
        nargs="+",
        metavar="citekey",
        help="One or more paper citekeys.",
    )

    tags_remove_p = tags_sub.add_parser("remove", help="Remove tags.")
    tags_remove_p.add_argument(
        "items",
        metavar="tags",
        help="Comma-separated tags to remove.",
    )
    tags_remove_p.add_argument(
        "citekeys",
        nargs="+",
        metavar="citekey",
        help="One or more paper citekeys.",
    )

    # ── themes subcommand ──────────────────────────────────────────────────────
    themes_p = subparsers.add_parser("themes", help="Add or remove themes.")
    themes_sub = themes_p.add_subparsers(dest="action")

    themes_add_p = themes_sub.add_parser("add", help="Add themes.")
    themes_add_p.add_argument(
        "items",
        metavar="themes",
        help="Comma-separated themes to add.",
    )
    themes_add_p.add_argument(
        "citekeys",
        nargs="+",
        metavar="citekey",
        help="One or more paper citekeys.",
    )

    themes_remove_p = themes_sub.add_parser("remove", help="Remove themes.")
    themes_remove_p.add_argument(
        "items",
        metavar="themes",
        help="Comma-separated themes to remove.",
    )
    themes_remove_p.add_argument(
        "citekeys",
        nargs="+",
        metavar="citekey",
        help="One or more paper citekeys.",
    )

    return parser


# ── Entry points ───────────────────────────────────────────────────────────────


def run(argv: list[str] | None = None, *, root: Path | None = None) -> int:
    """Run the update CLI.

    Args:
        argv: Argument list (default: sys.argv[1:]).
        root: Path to literature/ directory (default: auto-detect).

    Returns:
        Exit code (0 = success, 1 = error).
    """
    parser = _build_parser()
    args = parser.parse_args(argv)

    effective_root = root or args.root or _find_literature_root()

    if args.command == "status":
        return _cmd_status(args, effective_root)

    if args.command == "tags":
        if args.action == "add":
            return _cmd_tags_add(args, effective_root)
        if args.action == "remove":
            return _cmd_tags_remove(args, effective_root)
        parser.error("tags requires a subcommand: add or remove")

    if args.command == "themes":
        if args.action == "add":
            return _cmd_themes_add(args, effective_root)
        if args.action == "remove":
            return _cmd_themes_remove(args, effective_root)
        parser.error("themes requires a subcommand: add or remove")

    parser.print_help()
    return 1


def main() -> None:
    """Entry point for the update CLI."""
    sys.exit(run())


if __name__ == "__main__":
    main()
