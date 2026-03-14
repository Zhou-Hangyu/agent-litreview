"""Tests for sync_from_markdown and lit rebuild."""

from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

import pytest

from literature.scripts.db import init_db, sync_from_markdown
from literature.scripts.lit import run
from literature.scripts.parse import write_paper_file

REAL_PAPERS_DIR = Path(__file__).parent.parent / "papers"

_MINIMAL_PAPER = """\
---
doc_id: {doc_id}
title: "{title}"
authors:
  - "Test, A."
year: 2024
resource_type: paper
reading_status:
  global: unread
tags: []
themes: []
cites: []
cited_by: []
citation_count: 0
influential_citation_count: 0
abstract: ""
tldr: ""
---
"""

_PAPER_WITH_CITES = """\
---
doc_id: paper_b
title: "Paper B"
authors:
  - "Author, B."
year: 2023
resource_type: paper
reading_status:
  global: read
tags: []
themes: []
cites:
  - id: paper_a
    type: extends
cited_by: []
citation_count: 5
influential_citation_count: 0
abstract: "Paper B abstract."
tldr: ""
---
"""

_PAPER_STATUS_STRING = """\
---
doc_id: paper_str_status
title: "Paper With String Status"
authors:
  - "Author, C."
year: 2022
resource_type: paper
reading_status: read
tags: []
themes: []
cites: []
cited_by: []
citation_count: 0
influential_citation_count: 0
abstract: ""
tldr: ""
---
"""

_PAPER_STATUS_DICT = """\
---
doc_id: paper_dict_status
title: "Paper With Dict Status"
authors:
  - "Author, D."
year: 2021
resource_type: paper
reading_status:
  global: synthesized
  hangyu:
    status: read
    date: "2026-01-01"
tags: []
themes: []
cites: []
cited_by: []
citation_count: 0
influential_citation_count: 0
abstract: ""
tldr: ""
---
"""


def _make_lit_root(tmp_path: Path) -> Path:
    lit_dir = tmp_path / "literature"
    (lit_dir / "papers").mkdir(parents=True)
    (lit_dir / "resources").mkdir()
    (lit_dir / "AGENTS.md").write_text("# Test")
    return lit_dir


def _add_paper(lit_dir: Path, content: str, filename: str) -> Path:
    p = lit_dir / "papers" / filename
    p.write_text(content, encoding="utf-8")
    return p


@pytest.fixture
def empty_lit(tmp_path: Path) -> Path:
    return _make_lit_root(tmp_path)


@pytest.fixture
def real_lit(tmp_path: Path) -> Path:
    lit_dir = _make_lit_root(tmp_path)
    for paper in sorted(REAL_PAPERS_DIR.glob("*.md")):
        shutil.copy(paper, lit_dir / "papers" / paper.name)
    return lit_dir


def test_sync_empty_dir(empty_lit: Path) -> None:
    db = init_db(empty_lit)
    result = sync_from_markdown(empty_lit, db)
    db.close()
    assert result["papers"] == 0
    assert result["citations"] == 0
    assert result["skipped"] == 0


def test_sync_single_paper(empty_lit: Path) -> None:
    _add_paper(empty_lit, _MINIMAL_PAPER.format(doc_id="paper_a", title="Paper A"), "paper_a.md")
    db = init_db(empty_lit)
    result = sync_from_markdown(empty_lit, db)
    count = db.execute("SELECT COUNT(*) FROM papers").fetchone()[0]
    db.close()
    assert result["papers"] == 1
    assert count == 1


def test_sync_paper_count(real_lit: Path) -> None:
    db = init_db(real_lit)
    sync_from_markdown(real_lit, db)
    count = db.execute("SELECT COUNT(*) FROM papers").fetchone()[0]
    db.close()
    assert count == 17


def test_sync_citation_count(real_lit: Path) -> None:
    db = init_db(real_lit)
    sync_from_markdown(real_lit, db)
    count = db.execute("SELECT COUNT(*) FROM citations").fetchone()[0]
    db.close()
    assert count == 16


def test_sync_field_values_vaswani(real_lit: Path) -> None:
    db = init_db(real_lit)
    sync_from_markdown(real_lit, db)
    row = db.execute(
        "SELECT citation_count FROM papers WHERE paper_id='vaswani2017attention'"
    ).fetchone()
    db.close()
    assert row is not None
    assert row["citation_count"] == 169004


def test_sync_field_values_tradefm(real_lit: Path) -> None:
    db = init_db(real_lit)
    sync_from_markdown(real_lit, db)
    row = db.execute(
        "SELECT title FROM papers WHERE paper_id='kawawa-beaudan2026tradefm'"
    ).fetchone()
    db.close()
    assert row is not None
    assert "TradeFM" in row["title"]


def test_sync_idempotent(real_lit: Path) -> None:
    db = init_db(real_lit)
    sync_from_markdown(real_lit, db)
    count_papers_1 = db.execute("SELECT COUNT(*) FROM papers").fetchone()[0]
    count_cites_1 = db.execute("SELECT COUNT(*) FROM citations").fetchone()[0]

    sync_from_markdown(real_lit, db)
    count_papers_2 = db.execute("SELECT COUNT(*) FROM papers").fetchone()[0]
    count_cites_2 = db.execute("SELECT COUNT(*) FROM citations").fetchone()[0]
    db.close()

    assert count_papers_1 == count_papers_2
    assert count_cites_1 == count_cites_2


def test_sync_incremental_skip(empty_lit: Path) -> None:
    _add_paper(empty_lit, _MINIMAL_PAPER.format(doc_id="paper_a", title="Paper A"), "paper_a.md")
    _add_paper(empty_lit, _MINIMAL_PAPER.format(doc_id="paper_b", title="Paper B"), "paper_b.md")

    db = init_db(empty_lit)
    result1 = sync_from_markdown(empty_lit, db)
    assert result1["papers"] == 2

    result2 = sync_from_markdown(empty_lit, db)
    assert result2["papers"] == 0

    paper_b = empty_lit / "papers" / "paper_b.md"
    paper_b.write_text(
        _MINIMAL_PAPER.format(doc_id="paper_b", title="Paper B Updated"),
        encoding="utf-8",
    )
    result3 = sync_from_markdown(empty_lit, db)
    assert result3["papers"] == 1

    row = db.execute("SELECT title FROM papers WHERE paper_id='paper_b'").fetchone()
    db.close()
    assert row["title"] == "Paper B Updated"


def test_sync_reading_status_string(empty_lit: Path) -> None:
    _add_paper(empty_lit, _PAPER_STATUS_STRING, "paper_str_status.md")
    db = init_db(empty_lit)
    sync_from_markdown(empty_lit, db)
    row = db.execute(
        "SELECT reading_status_global FROM papers WHERE paper_id='paper_str_status'"
    ).fetchone()
    db.close()
    assert row is not None
    assert row["reading_status_global"] == "read"


def test_sync_reading_status_dict(empty_lit: Path) -> None:
    _add_paper(empty_lit, _PAPER_STATUS_DICT, "paper_dict_status.md")
    db = init_db(empty_lit)
    sync_from_markdown(empty_lit, db)
    row = db.execute(
        "SELECT reading_status_global, reading_status_json "
        "FROM papers WHERE paper_id='paper_dict_status'"
    ).fetchone()
    db.close()
    assert row is not None
    assert row["reading_status_global"] == "synthesized"
    rs = json.loads(row["reading_status_json"])
    assert rs["global"] == "synthesized"
    assert rs["hangyu"]["status"] == "read"


def test_sync_citations_forward_edge(empty_lit: Path) -> None:
    _add_paper(empty_lit, _MINIMAL_PAPER.format(doc_id="paper_a", title="Paper A"), "paper_a.md")
    _add_paper(empty_lit, _PAPER_WITH_CITES, "paper_b.md")
    db = init_db(empty_lit)
    sync_from_markdown(empty_lit, db)
    row = db.execute(
        "SELECT citing_id, cited_id, edge_type FROM citations"
    ).fetchone()
    db.close()
    assert row is not None
    assert row["citing_id"] == "paper_b"
    assert row["cited_id"] == "paper_a"
    assert row["edge_type"] == "extends"


def test_sync_fts5_populated(empty_lit: Path) -> None:
    _add_paper(
        empty_lit,
        _MINIMAL_PAPER.format(doc_id="attn_paper", title="Attention Is All You Need"),
        "attn_paper.md",
    )
    db = init_db(empty_lit)
    sync_from_markdown(empty_lit, db)
    rows = db.execute(
        "SELECT paper_id FROM papers_fts WHERE papers_fts MATCH 'attention'"
    ).fetchall()
    db.close()
    paper_ids = [r[0] for r in rows]
    assert "attn_paper" in paper_ids


def test_rebuild_cli_integration(empty_lit: Path) -> None:
    exit_code = run(["rebuild"], root=empty_lit)
    assert exit_code == 0
    assert (empty_lit / "index" / "papers.db").exists()


def test_rebuild_json_output(empty_lit: Path, capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = run(["--json", "rebuild"], root=empty_lit)
    assert exit_code == 0
    out = capsys.readouterr().out
    data = json.loads(out)
    assert "papers" in data
    assert "citations" in data
    assert "skipped" in data


def test_sync_authors_as_json(empty_lit: Path) -> None:
    _add_paper(empty_lit, _MINIMAL_PAPER.format(doc_id="paper_a", title="Paper A"), "paper_a.md")
    db = init_db(empty_lit)
    sync_from_markdown(empty_lit, db)
    row = db.execute("SELECT authors FROM papers WHERE paper_id='paper_a'").fetchone()
    db.close()
    assert row is not None
    authors = json.loads(row["authors"])
    assert isinstance(authors, list)
    assert authors == ["Test, A."]
