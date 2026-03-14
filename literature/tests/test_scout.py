"""Tests for literature.scripts.scout -- paper discovery CLI."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import responses as responses_lib

from literature.scripts.scout import (
    _cmd_gaps,
    _cmd_recommend,
    _cmd_search,
    _load_collection_ids,
    run,
)
from literature.scripts.s2_client import (
    S2_GRAPH_BASE,
    S2_RECS_BASE,
    S2Error,
)

# ── Fixtures ──────────────────────────────────────────────────────────────────


def _write_paper(papers_dir: Path, citekey: str, s2_id: str = "", arxiv_id: str = "", citation_count: int = 0) -> Path:
    """Write a minimal paper .md file with frontmatter."""
    p = papers_dir / f"{citekey}.md"
    lines = [
        "---",
        f"doc_id: {citekey}",
        f"title: Paper {citekey}",
        "year: 2020",
    ]
    if s2_id:
        lines.append(f"s2_id: {s2_id}")
    if arxiv_id:
        lines.append(f"arxiv_id: {arxiv_id}")
    lines.append(f"citation_count: {citation_count}")
    lines.append("---")
    lines.append("# Notes\n")
    p.write_text("\n".join(lines), encoding="utf-8")
    return p


def _write_graph(index_dir: Path, nodes: dict, edges: list) -> Path:
    """Write a minimal graph.yaml file."""
    index_dir.mkdir(parents=True, exist_ok=True)
    g = index_dir / "graph.yaml"
    lines = ["nodes:"]
    for ck, data in nodes.items():
        lines.append(f"  {ck}:")
        for k, v in data.items():
            lines.append(f"    {k}: {v!r}")
    lines.append("edges:")
    for edge in edges:
        lines.append(f"  - from: {edge['from']}")
        lines.append(f"    to: {edge['to']}")
        lines.append(f"    type: {edge.get('type', 'cites')}")
    g.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return g


@pytest.fixture()
def lit_root(tmp_path: Path) -> Path:
    """A minimal literature/ root with papers/ and index/ directories."""
    root = tmp_path / "literature"
    (root / "papers").mkdir(parents=True)
    (root / "index").mkdir(parents=True)
    # Fake AGENTS.md so _find_literature_root can locate it
    (root / "AGENTS.md").write_text("# AGENTS", encoding="utf-8")
    return root


# ── Tests: _load_collection_ids ───────────────────────────────────────────────


def test_load_collection_ids_basic(lit_root: Path) -> None:
    papers_dir = lit_root / "papers"
    _write_paper(papers_dir, "vaswani2017", s2_id="abc123", arxiv_id="1706.03762")
    _write_paper(papers_dir, "devlin2018", s2_id="def456")

    s2_ids, arxiv_ids = _load_collection_ids(papers_dir)

    assert "abc123" in s2_ids
    assert "def456" in s2_ids
    assert "1706.03762" in arxiv_ids


def test_load_collection_ids_empty_dir(tmp_path: Path) -> None:
    empty = tmp_path / "papers"
    empty.mkdir()
    s2_ids, arxiv_ids = _load_collection_ids(empty)
    assert s2_ids == set()
    assert arxiv_ids == set()


# ── Tests: recommend subcommand ───────────────────────────────────────────────


@responses_lib.activate
def test_recommend_single_seed(lit_root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    papers_dir = lit_root / "papers"
    _write_paper(papers_dir, "vaswani2017", s2_id="seed_s2_id_001", citation_count=50000)

    responses_lib.add(
        responses_lib.GET,
        f"{S2_RECS_BASE}/papers/forpaper/seed_s2_id_001",
        json={
            "recommendedPapers": [
                {
                    "paperId": "new_paper_001",
                    "title": "A New Transformer Paper",
                    "year": 2023,
                    "citationCount": 100,
                    "externalIds": {"ArXiv": "2301.00001"},
                    "authors": [],
                }
            ]
        },
        status=200,
    )

    exit_code = run(["recommend", "--seeds", "vaswani2017"], lit_root=lit_root)
    assert exit_code == 0

    out = capsys.readouterr().out
    assert "A New Transformer Paper" in out
    assert "CANDIDATE" in out


@responses_lib.activate
def test_recommend_filters_existing_papers(lit_root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    papers_dir = lit_root / "papers"
    _write_paper(papers_dir, "vaswani2017", s2_id="seed_s2_id_001")
    _write_paper(papers_dir, "existing_paper", s2_id="already_in_collection")

    responses_lib.add(
        responses_lib.GET,
        f"{S2_RECS_BASE}/papers/forpaper/seed_s2_id_001",
        json={
            "recommendedPapers": [
                {
                    "paperId": "already_in_collection",
                    "title": "Already Here",
                    "year": 2022,
                    "citationCount": 50,
                    "externalIds": {},
                    "authors": [],
                }
            ]
        },
        status=200,
    )

    exit_code = run(["recommend", "--seeds", "vaswani2017"], lit_root=lit_root)
    assert exit_code == 0

    out = capsys.readouterr().out
    assert "Already Here" not in out
    assert "No new papers found" in out


@responses_lib.activate
def test_recommend_multi_seed(lit_root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """With 2+ seeds, recommend_multi should be called instead of recommend_papers."""
    papers_dir = lit_root / "papers"
    _write_paper(papers_dir, "paper_a", s2_id="s2_seed_aaa")
    _write_paper(papers_dir, "paper_b", s2_id="s2_seed_bbb")

    responses_lib.add(
        responses_lib.POST,
        f"{S2_RECS_BASE}/papers/",
        json={
            "recommendedPapers": [
                {
                    "paperId": "new_multi_001",
                    "title": "Multi-Seed Result",
                    "year": 2024,
                    "citationCount": 200,
                    "externalIds": {},
                    "authors": [],
                }
            ]
        },
        status=200,
    )

    exit_code = run(["recommend", "--seeds", "paper_a,paper_b"], lit_root=lit_root)
    assert exit_code == 0

    out = capsys.readouterr().out
    assert "Multi-Seed Result" in out


def test_recommend_no_seeds_with_no_s2_ids(lit_root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """When no papers have s2_id, graceful error is returned."""
    papers_dir = lit_root / "papers"
    # Paper has no s2_id
    _write_paper(papers_dir, "paper_no_s2id")

    exit_code = run(["recommend"], lit_root=lit_root)
    assert exit_code == 1

    err = capsys.readouterr().err
    assert "No valid seed papers" in err


def test_recommend_missing_seed_citekey(lit_root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Seed citekey that doesn't exist is skipped with a warning."""
    papers_dir = lit_root / "papers"
    _write_paper(papers_dir, "existing_paper", s2_id="some_s2_id")

    # "nonexistent" doesn't have a file
    with patch("literature.scripts.scout.recommend_papers") as mock_rec:
        mock_rec.return_value = []
        run(["recommend", "--seeds", "nonexistent,existing_paper"], lit_root=lit_root)

    err = capsys.readouterr().err
    assert "nonexistent" in err


def test_recommend_seed_without_s2_id(lit_root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Seed paper that has no s2_id is skipped with a warning."""
    papers_dir = lit_root / "papers"
    _write_paper(papers_dir, "paper_no_s2")  # no s2_id

    exit_code = run(["recommend", "--seeds", "paper_no_s2"], lit_root=lit_root)
    assert exit_code == 1

    err = capsys.readouterr().err
    assert "paper_no_s2" in err
    assert "s2_id" in err.lower() or "skipping" in err.lower()


@responses_lib.activate
def test_recommend_s2_error(lit_root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """S2Error raised during recommend → exit code 1."""
    papers_dir = lit_root / "papers"
    _write_paper(papers_dir, "seed_paper", s2_id="seed_id_xyz")

    responses_lib.add(
        responses_lib.GET,
        f"{S2_RECS_BASE}/papers/forpaper/seed_id_xyz",
        json={"error": "server error"},
        status=500,
    )

    exit_code = run(["recommend", "--seeds", "seed_paper"], lit_root=lit_root)
    assert exit_code == 1

    err = capsys.readouterr().err
    assert "S2 API error" in err


# ── Tests: search subcommand ──────────────────────────────────────────────────


@responses_lib.activate
def test_search_returns_results(lit_root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    responses_lib.add(
        responses_lib.GET,
        f"{S2_GRAPH_BASE}/paper/search/bulk",
        json={
            "data": [
                {
                    "paperId": "search_result_001",
                    "title": "Searching Transformers",
                    "year": 2023,
                    "citationCount": 42,
                    "externalIds": {"ArXiv": "2303.00001"},
                    "authors": [],
                }
            ],
            "token": None,
        },
        status=200,
    )

    exit_code = run(["search", "transformers attention"], lit_root=lit_root)
    assert exit_code == 0

    out = capsys.readouterr().out
    assert "Searching Transformers" in out
    assert "CANDIDATE" in out


@responses_lib.activate
def test_search_filters_existing_papers(lit_root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    papers_dir = lit_root / "papers"
    _write_paper(papers_dir, "known_paper", arxiv_id="2303.00001")

    responses_lib.add(
        responses_lib.GET,
        f"{S2_GRAPH_BASE}/paper/search/bulk",
        json={
            "data": [
                {
                    "paperId": "already_known_001",
                    "title": "Already In Collection",
                    "year": 2023,
                    "citationCount": 10,
                    "externalIds": {"ArXiv": "2303.00001"},
                    "authors": [],
                }
            ],
            "token": None,
        },
        status=200,
    )

    exit_code = run(["search", "transformers"], lit_root=lit_root)
    assert exit_code == 0

    out = capsys.readouterr().out
    assert "Already In Collection" not in out
    assert "No results found" in out


@responses_lib.activate
def test_search_no_results(lit_root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    responses_lib.add(
        responses_lib.GET,
        f"{S2_GRAPH_BASE}/paper/search/bulk",
        json={"data": [], "token": None},
        status=200,
    )

    exit_code = run(["search", "xyzzy no results query"], lit_root=lit_root)
    assert exit_code == 0

    out = capsys.readouterr().out
    assert "No results found" in out


@responses_lib.activate
def test_search_s2_error(lit_root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    responses_lib.add(
        responses_lib.GET,
        f"{S2_GRAPH_BASE}/paper/search/bulk",
        json={"error": "service unavailable"},
        status=503,
    )

    exit_code = run(["search", "test query"], lit_root=lit_root)
    assert exit_code == 1

    err = capsys.readouterr().err
    assert "S2 API error" in err


# ── Tests: gaps subcommand ────────────────────────────────────────────────────


@responses_lib.activate
def test_gaps_finds_missing_papers(lit_root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Papers cited in edges but not in nodes appear as gaps."""
    index_dir = lit_root / "index"
    nodes = {
        "paperA": {"title": "Paper A", "year": 2020},
        "paperB": {"title": "Paper B", "year": 2021},
    }
    edges = [
        {"from": "paperA", "to": "external_xyz", "type": "cites"},
        {"from": "paperB", "to": "external_xyz", "type": "cites"},
    ]
    _write_graph(index_dir, nodes, edges)

    responses_lib.add(
        responses_lib.POST,
        f"{S2_GRAPH_BASE}/paper/batch",
        json=[
            {
                "paperId": "external_xyz",
                "title": "The Missing Paper",
                "year": 2019,
                "citationCount": 500,
            }
        ],
        status=200,
    )

    exit_code = run(["gaps", "--top", "5"], lit_root=lit_root)
    assert exit_code == 0

    out = capsys.readouterr().out
    assert "The Missing Paper" in out


@responses_lib.activate
def test_gaps_cited_by_2_shown(lit_root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Paper cited by 2 collection papers appears with count 2."""
    index_dir = lit_root / "index"
    nodes = {
        "paperA": {"title": "Paper A", "year": 2020},
        "paperB": {"title": "Paper B", "year": 2021},
    }
    edges = [
        {"from": "paperA", "to": "gap_paper_id", "type": "cites"},
        {"from": "paperB", "to": "gap_paper_id", "type": "cites"},
    ]
    _write_graph(index_dir, nodes, edges)

    responses_lib.add(
        responses_lib.POST,
        f"{S2_GRAPH_BASE}/paper/batch",
        json=[{"paperId": "gap_paper_id", "title": "Cited Twice", "year": 2018, "citationCount": 200}],
        status=200,
    )

    exit_code = run(["gaps"], lit_root=lit_root)
    assert exit_code == 0

    out = capsys.readouterr().out
    assert "Cited Twice" in out
    assert "2" in out  # cited-by count appears somewhere in the row


def test_gaps_no_graph(lit_root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """When graph.yaml is missing, error message is shown and exit code is 1."""
    # Don't write any graph.yaml
    exit_code = run(["gaps"], lit_root=lit_root)
    assert exit_code == 1

    err = capsys.readouterr().err
    assert "graph.yaml" in err.lower() or "rebuild_index" in err.lower()


# ── Tests: CLI scaffold ───────────────────────────────────────────────────────


def test_run_no_subcommand(lit_root: Path) -> None:
    """Missing subcommand results in non-zero exit (argparse raises SystemExit)."""
    with pytest.raises(SystemExit) as exc_info:
        run([], lit_root=lit_root)
    assert exc_info.value.code != 0


@responses_lib.activate
def test_recommend_default_seeds_from_collection(lit_root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """When no --seeds given, top papers by citation_count are used as seeds."""
    papers_dir = lit_root / "papers"
    _write_paper(papers_dir, "top_paper", s2_id="top_s2_id", citation_count=10000)

    responses_lib.add(
        responses_lib.GET,
        f"{S2_RECS_BASE}/papers/forpaper/top_s2_id",
        json={
            "recommendedPapers": [
                {
                    "paperId": "fresh_001",
                    "title": "Fresh Discovery",
                    "year": 2024,
                    "citationCount": 5,
                    "externalIds": {},
                    "authors": [],
                }
            ]
        },
        status=200,
    )

    exit_code = run(["recommend"], lit_root=lit_root)
    assert exit_code == 0

    out = capsys.readouterr().out
    assert "Fresh Discovery" in out
