"""
Migrate v1 YAML-indexed literature to v3 SQLite-backed system.

Since markdown files are already the source of truth, migration is:
1. Validate all paper .md files for required fields
2. Run sync_from_markdown to populate SQLite
3. Verify data integrity

Usage:
    uv run python literature/scripts/migrate.py --from-v1
    uv run python literature/scripts/lit.py migrate --from-v1
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


from literature.scripts.db import init_db, sync_from_markdown
from literature.scripts.parse import read_frontmatter
from literature.scripts.rebuild_index import _find_literature_root


def migrate_from_v1(root: Path, *, verbose: bool = True) -> dict:
    """Migrate v1 YAML-indexed literature to v3 SQLite-backed system.

    Since markdown files are already the source of truth, migration is:
    1. Validate all paper .md files for required fields
    2. Run sync_from_markdown to populate SQLite
    3. Verify data integrity

    Args:
        root: Path to the literature/ directory or any ancestor.
        verbose: If True, print warnings and progress.

    Returns:
        Dict with keys: papers, citations, warnings, paper_files_found.
    """
    lit_root = _find_literature_root(root)

    warnings: list[str] = []

    # Step 1: Validate all paper files
    papers_dir = lit_root / "papers"
    required_fields = {"doc_id", "title", "year"}
    paper_count = 0
    if papers_dir.is_dir():
        for md_path in papers_dir.glob("*.md"):
            try:
                meta, _ = read_frontmatter(md_path)
                missing = required_fields - set(meta.keys())
                if missing:
                    warnings.append(f"  {md_path.name}: missing fields {missing}")
                paper_count += 1
            except Exception as e:
                warnings.append(f"  {md_path.name}: parse error: {e}")

    # Step 2: Sync into SQLite
    db = init_db(root)
    sync_result = sync_from_markdown(root, db, verbose=verbose)
    db.close()

    # Step 3: Verify data integrity
    db = init_db(root)
    paper_db_count = db.execute("SELECT COUNT(*) FROM papers").fetchone()[0]
    citation_count = db.execute("SELECT COUNT(*) FROM citations").fetchone()[0]
    vaswani_check = db.execute(
        "SELECT citation_count FROM papers WHERE paper_id='vaswani2017attention'"
    ).fetchone()
    db.close()

    if vaswani_check and vaswani_check[0] != 169004:
        warnings.append(f"  vaswani2017attention citation_count mismatch: got {vaswani_check[0]}")

    return {
        "papers": paper_db_count,
        "citations": citation_count,
        "warnings": warnings,
        "paper_files_found": paper_count,
    }


def run(argv: list[str] | None = None, *, root: Path | None = None) -> int:
    """CLI entry point.

    Args:
        argv: Command-line arguments (default: sys.argv[1:]).
        root: Path to the literature/ directory; overrides ``--root`` flag.

    Returns:
        Exit code.
    """
    parser = argparse.ArgumentParser(prog="migrate.py")
    parser.add_argument("--from-v1", action="store_true", help="Migrate from v1 YAML system")
    parser.add_argument("--root", type=Path, default=None, help="Path to literature/ directory")
    args = parser.parse_args(argv)

    if root is None and args.root:
        root = args.root
    if root is None:
        root = Path.cwd()

    result = migrate_from_v1(root)
    print(f"Migration complete: {result['papers']} papers, {result['citations']} citations")
    if result["warnings"]:
        print("Warnings:")
        for w in result["warnings"]:
            print(w)
    return 0


def main() -> None:
    """Entry point for the migrate CLI."""
    sys.exit(run())


if __name__ == "__main__":
    main()
