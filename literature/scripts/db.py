"""
SQLite schema and connection management for the literature v3 system.

Provides:
    get_db(root)   — open (or create) the SQLite DB, applying mandatory PRAGMAs
    init_db(root)  — create all tables / FTS5 virtual table if they don't exist
    close_db(conn) — close the connection

DB location: {lit_root}/index/papers.db

Usage:
    from literature.scripts.db import get_db, init_db, close_db
    from pathlib import Path

    root = Path("literature")
    conn = init_db(root)      # first-time setup (idempotent)
    conn = get_db(root)       # subsequent opens
    ...
    close_db(conn)
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path


# ── Helpers ────────────────────────────────────────────────────────────────────


def _find_db_path(root: Path) -> Path:
    """Resolve the absolute path to papers.db given a literature root.

    Mirrors _find_literature_root() from rebuild_index.py: if *root* already
    points to a directory containing AGENTS.md, use it directly; otherwise
    walk upward from cwd to find the literature/ directory.

    Args:
        root: A Path hint — either the literal literature/ directory, or any
              ancestor that contains it.

    Returns:
        Absolute path to ``{lit_root}/index/papers.db``.
    """
    resolved = root.resolve()

    # Case 1: caller passed the literature/ dir directly
    if (resolved / "AGENTS.md").is_file():
        return resolved / "index" / "papers.db"

    # Case 2: caller passed a parent — look for literature/AGENTS.md inside
    candidate = resolved / "literature" / "AGENTS.md"
    if candidate.is_file():
        return resolved / "literature" / "index" / "papers.db"

    # Case 3: walk upward from cwd (same strategy as _find_literature_root)
    for parent in [Path.cwd().resolve(), *Path.cwd().resolve().parents]:
        if (parent / "literature" / "AGENTS.md").is_file():
            return parent / "literature" / "index" / "papers.db"

    # Fallback: treat root as-is
    return resolved / "index" / "papers.db"


# ── DDL ────────────────────────────────────────────────────────────────────────

_DDL = """\
-- ============================================================
-- Main papers table — mirrors paper frontmatter fields
-- ============================================================
CREATE TABLE IF NOT EXISTS papers (
    paper_id                    TEXT PRIMARY KEY,
    title                       TEXT NOT NULL,
    authors                     TEXT,               -- JSON array
    year                        INTEGER,
    venue                       TEXT    DEFAULT '',
    doi                         TEXT    DEFAULT '',
    arxiv_id                    TEXT    DEFAULT '',
    s2_id                       TEXT    DEFAULT '',
    url                         TEXT    DEFAULT '',
    resource_type               TEXT    DEFAULT 'paper',
    et_al                       INTEGER DEFAULT 0,  -- boolean as int
    abstract                    TEXT    DEFAULT '',
    tldr                        TEXT    DEFAULT '',
    citation_count              INTEGER DEFAULT 0,
    influential_citation_count  INTEGER DEFAULT 0,
    reading_status_global       TEXT    DEFAULT 'unread',
    reading_status_json         TEXT,               -- full per-collaborator dict as JSON
    tags                        TEXT,               -- JSON array
    themes                      TEXT,               -- JSON array
    contribution_type           TEXT    DEFAULT '',
    provenance_json             TEXT,               -- JSON dict
    pdf_path                    TEXT    DEFAULT '',
    -- Progressive summaries
    summary_l4_text             TEXT    DEFAULT '',
    summary_l4_model            TEXT    DEFAULT '',
    summary_l4_generated_at     TEXT    DEFAULT '',
    summary_l2_claims           TEXT    DEFAULT '',  -- JSON array of claim strings
    summary_l2_model            TEXT    DEFAULT '',
    summary_l2_generated_at     TEXT    DEFAULT '',
    -- SPECTER2 embedding (optional, 768 float32 as raw bytes)
    embedding                   BLOB,
    pagerank_score              REAL    DEFAULT 0.0,
    -- Sync tracking
    file_path                   TEXT,               -- relative path to .md file
    synced_at                   REAL                -- file mtime at last sync
);

-- ============================================================
-- Typed citation edges
-- ============================================================
CREATE TABLE IF NOT EXISTS citations (
    citing_id   TEXT NOT NULL,
    cited_id    TEXT NOT NULL,
    edge_type   TEXT NOT NULL DEFAULT 'cites',
    -- edge_type: cites|extends|contradicts|uses_method|uses_dataset|surveys
    PRIMARY KEY (citing_id, cited_id)
);

-- ============================================================
-- Discovery inbox — papers found but not yet added to corpus
-- ============================================================
CREATE TABLE IF NOT EXISTS discovery_inbox (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    paper_id        TEXT,                   -- S2 paper ID or arXiv ID
    title           TEXT,
    abstract        TEXT,
    source          TEXT,                   -- 's2_recommend'|'arxiv_rss'|'s2_search'
    relevance_score REAL    DEFAULT 0.0,
    discovered_at   TEXT,                   -- ISO timestamp
    status          TEXT    DEFAULT 'pending',  -- pending|added|dismissed
    raw_json        TEXT                    -- full API response as JSON
);

-- ============================================================
-- Batch job queue — for resumable summarisation
-- ============================================================
CREATE TABLE IF NOT EXISTS jobs (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    job_type     TEXT NOT NULL,             -- 'summarize_l4'|'summarize_l2'|'fetch_embeddings'
    paper_id     TEXT NOT NULL,
    status       TEXT    DEFAULT 'pending', -- pending|done|failed
    error        TEXT,
    created_at   TEXT,
    completed_at TEXT
);
"""

_FTS5_DDL = """\
CREATE VIRTUAL TABLE IF NOT EXISTS papers_fts USING fts5(
    paper_id        UNINDEXED,
    title,
    abstract,
    tldr,
    summary_l4_text,
    summary_l2_claims,
    content='papers',
    content_rowid='rowid',
    tokenize="unicode61 tokenchars '-_'"
)"""


# ── Public API ─────────────────────────────────────────────────────────────────


def get_db(root: Path) -> sqlite3.Connection:
    """Open (or create) the SQLite DB for the literature system.

    Applies mandatory PRAGMAs:
        - journal_mode = WAL        (concurrent readers)
        - busy_timeout = 5000       (ms, avoids SQLITE_BUSY on contention)
        - synchronous = NORMAL      (safe + fast under WAL)
        - foreign_keys = ON         (referential integrity)

    PRAGMAs are set outside any transaction (required by SQLite).

    Args:
        root: Path to the literature/ directory (or any ancestor containing it).

    Returns:
        An open ``sqlite3.Connection`` with ``row_factory = sqlite3.Row``.
    """
    db_path = _find_db_path(root)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    # PRAGMAs must be outside any transaction
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")

    return conn


def init_db(root: Path) -> sqlite3.Connection:
    """Create all tables and the FTS5 virtual table if they do not exist.

    Idempotent — safe to call multiple times on the same DB.

    Args:
        root: Path to the literature/ directory (or any ancestor containing it).

    Returns:
        An open ``sqlite3.Connection`` with ``row_factory = sqlite3.Row``.
    """
    conn = get_db(root)

    # Execute each statement separately (executescript commits implicitly,
    # but we want to stay in our own transaction control)
    for statement in _DDL.split(";"):
        stmt = statement.strip()
        if stmt:
            conn.execute(stmt)

    # FTS5 virtual table — single statement
    conn.execute(_FTS5_DDL.strip())

    conn.commit()
    return conn


def close_db(conn: sqlite3.Connection) -> None:
    """Close the database connection.

    Args:
        conn: An open ``sqlite3.Connection`` returned by :func:`get_db` or
              :func:`init_db`.
    """
    if conn is not None:
        conn.close()


# ── Sync ───────────────────────────────────────────────────────────────────────


def _upsert_paper(
    db: sqlite3.Connection,
    meta: dict,
    file_path: str,
    mtime: float,
) -> None:
    """Map a frontmatter dict to a papers table row and upsert.

    Args:
        db: Open database connection.
        meta: Frontmatter dict from :func:`literature.scripts.parse.read_frontmatter`.
        file_path: Relative path to the ``.md`` file from the repo root.
        mtime: File modification time (seconds since epoch).
    """
    # Handle reading_status: can be a string ("unread") OR a dict ({"global": "unread"})
    rs = meta.get("reading_status") or {}
    if isinstance(rs, dict):
        global_status = str(rs.get("global", "unread"))
    else:
        global_status = str(rs) if rs else "unread"

    summaries = meta.get("summaries") or {}
    l4 = summaries.get("l4") or {}
    l2 = summaries.get("l2") or {}

    db.execute(
        """
        INSERT OR REPLACE INTO papers (
            paper_id, title, authors, year, venue, doi, arxiv_id, s2_id, url,
            resource_type, et_al, abstract, tldr, citation_count,
            influential_citation_count, reading_status_global, reading_status_json,
            tags, themes, contribution_type, provenance_json, pdf_path,
            summary_l4_text, summary_l4_model, summary_l4_generated_at,
            summary_l2_claims, summary_l2_model, summary_l2_generated_at,
            file_path, synced_at
        ) VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?,
            ?, ?, ?,
            ?, ?, ?, ?, ?,
            ?, ?, ?,
            ?, ?, ?,
            ?, ?
        )
        """,
        (
            str(meta.get("doc_id", "")),
            str(meta.get("title", "")),
            json.dumps([str(a) for a in (meta.get("authors") or [])]),
            meta.get("year"),
            str(meta.get("venue") or ""),
            str(meta.get("doi") or ""),
            str(meta.get("arxiv_id") or ""),
            str(meta.get("s2_id") or ""),
            str(meta.get("url") or ""),
            str(meta.get("resource_type") or "paper"),
            int(bool(meta.get("et_al", False))),
            str(meta.get("abstract") or ""),
            str(meta.get("tldr") or ""),
            int(meta.get("citation_count") or 0),
            int(meta.get("influential_citation_count") or 0),
            global_status,
            json.dumps(meta.get("reading_status") or {}),
            json.dumps([str(t) for t in (meta.get("tags") or [])]),
            json.dumps([str(t) for t in (meta.get("themes") or [])]),
            str(meta.get("contribution_type") or ""),
            json.dumps(meta.get("provenance") or {}),
            str(meta.get("pdf_path") or ""),
            str(l4.get("text") or ""),
            str(l4.get("model") or ""),
            str(l4.get("generated_at") or ""),
            json.dumps([str(c) for c in (l2.get("claims") or [])]),
            str(l2.get("model") or ""),
            str(l2.get("generated_at") or ""),
            file_path,
            mtime,
        ),
    )


def _rebuild_citations(db: sqlite3.Connection, lit_root: Path) -> int:
    """Rebuild the citations table from all markdown files.

    Deletes all existing rows then re-inserts forward edges (``cites`` field)
    from every paper and resource file.

    Args:
        db: Open database connection.
        lit_root: The ``literature/`` directory.

    Returns:
        Number of citation edges inserted.
    """
    from literature.scripts.parse import read_frontmatter

    db.execute("DELETE FROM citations")

    count = 0
    for subdir in ("papers", "resources"):
        dir_path = lit_root / subdir
        if not dir_path.is_dir():
            continue
        for md_path in sorted(dir_path.glob("*.md")):
            try:
                meta, _ = read_frontmatter(md_path)
                if not meta:
                    continue
                citing_id = str(meta.get("doc_id", md_path.stem))
                for cite_entry in (meta.get("cites") or []):
                    if isinstance(cite_entry, dict):
                        cited_id = str(cite_entry.get("id", ""))
                        edge_type = str(cite_entry.get("type", "cites"))
                        if cited_id:
                            db.execute(
                                "INSERT OR IGNORE INTO citations "
                                "(citing_id, cited_id, edge_type) VALUES (?, ?, ?)",
                                (citing_id, cited_id, edge_type),
                            )
                            count += 1
            except Exception:
                pass

    return count


def sync_from_markdown(
    root: Path,
    db: sqlite3.Connection,
    *,
    verbose: bool = False,
) -> dict:
    """Scan all paper/resource markdown files and upsert into SQLite.

    Reads YAML frontmatter from every ``.md`` file in ``papers/`` and
    ``resources/``, upserts each into the ``papers`` table, rebuilds the
    ``citations`` table, and refreshes the FTS5 index.

    Incremental: files whose modification time matches the stored ``synced_at``
    timestamp are skipped (parsed count only reflects newly synced files).

    Args:
        root: Path to the ``literature/`` directory (or any ancestor).
        db: Open database connection (from :func:`init_db`).
        verbose: If ``True``, print warnings for skipped files to stderr.

    Returns:
        Dict with keys ``"papers"`` (upserted count), ``"citations"`` (total
        edge count after rebuild), and ``"skipped"`` (error count).
    """
    from literature.scripts.parse import read_frontmatter

    lit_root = _find_db_path(root).parent.parent  # literature/ directory
    papers_dir = lit_root / "papers"
    resources_dir = lit_root / "resources"

    papers_count = 0
    skipped = 0

    md_files: list[Path] = []
    if papers_dir.exists():
        md_files.extend(sorted(papers_dir.glob("*.md")))
    if resources_dir.exists():
        md_files.extend(sorted(resources_dir.glob("*.md")))

    for md_path in md_files:
        try:
            mtime = md_path.stat().st_mtime

            # Incremental sync: skip if file hasn't changed since last sync
            existing = db.execute(
                "SELECT synced_at FROM papers WHERE paper_id = ?",
                (md_path.stem,),
            ).fetchone()
            if (
                existing
                and existing["synced_at"] is not None
                and abs(existing["synced_at"] - mtime) < 0.001
            ):
                continue

            meta, _body = read_frontmatter(md_path)
            if not meta:
                if verbose:
                    print(
                        f"Warning: {md_path} has no frontmatter, skipping",
                        file=sys.stderr,
                    )
                skipped += 1
                continue

            file_path = str(md_path.relative_to(lit_root.parent))
            _upsert_paper(db, meta, file_path, mtime)
            papers_count += 1

        except Exception as e:
            if verbose:
                print(f"Warning: skipping {md_path}: {e}", file=sys.stderr)
            skipped += 1

    # Rebuild citations from all files (always — edges are fully derived)
    citations_count = _rebuild_citations(db, lit_root)

    # Refresh FTS5 content table from the base papers table
    db.execute("INSERT INTO papers_fts(papers_fts) VALUES('rebuild')")
    db.commit()

    return {"papers": papers_count, "citations": citations_count, "skipped": skipped}
