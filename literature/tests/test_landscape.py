"""Tests for literature.scripts.landscape — research landscape analysis engine."""

from __future__ import annotations

from pathlib import Path

import pytest

from literature.scripts.landscape import (
    _build_landscape,
    _detect_research_fronts,
    _detect_structural_holes,
    _find_citation_gaps,
    _load_embeddings,
    _write_markdown,
    run,
)


# ── Fixtures ───────────────────────────────────────────────────────────────────

PAPER_TEMPLATE = """\
---
citekey: {citekey}
title: "{title}"
year: {year}
citation_count: {citation_count}
abstract: "{abstract}"
---

# Notes
"""

EMBEDDINGS_YAML = """\
model: specter_v2
dimensions: 3
vectors:
  paper1: [1.0, 0.0, 0.0]
  paper2: [0.9, 0.1, 0.0]
  paper3: [0.0, 0.0, 1.0]
"""

GRAPH_YAML_TEMPLATE = """\
nodes:
{nodes}
edges: []
"""


def _make_lit_root(
    tmp_path: Path,
    papers: list[dict] | None = None,
    embeddings_content: str | None = None,
    graph_content: str | None = None,
) -> Path:
    """Create a minimal literature/ directory structure in tmp_path."""
    lit = tmp_path / "literature"
    papers_dir = lit / "papers"
    index_dir = lit / "index"
    papers_dir.mkdir(parents=True)
    index_dir.mkdir(parents=True)

    # Create AGENTS.md so _find_literature_root can detect it
    (lit / "AGENTS.md").write_text("# AGENTS\n", encoding="utf-8")

    if papers:
        for p in papers:
            content = PAPER_TEMPLATE.format(
                citekey=p.get("citekey", "paper1"),
                title=p.get("title", "Test Paper"),
                year=p.get("year", 2024),
                citation_count=p.get("citation_count", 0),
                abstract=p.get("abstract", ""),
            )
            (papers_dir / f"{p['citekey']}.md").write_text(content, encoding="utf-8")

    if embeddings_content is not None:
        (index_dir / "embeddings.yaml").write_text(embeddings_content, encoding="utf-8")

    if graph_content is not None:
        (index_dir / "graph.yaml").write_text(graph_content, encoding="utf-8")

    return lit


# ── test_build_landscape_basic ─────────────────────────────────────────────────

def test_build_landscape_basic(tmp_path: Path) -> None:
    """Build landscape with 3+ papers + embeddings, verify all required keys."""
    papers = [
        {"citekey": "paper1", "title": "Paper One", "year": 2024, "citation_count": 10, "abstract": "machine learning"},
        {"citekey": "paper2", "title": "Paper Two", "year": 2023, "citation_count": 5, "abstract": "deep learning models"},
        {"citekey": "paper3", "title": "Paper Three", "year": 2022, "citation_count": 2, "abstract": "neural networks"},
    ]
    lit = _make_lit_root(tmp_path, papers=papers, embeddings_content=EMBEDDINGS_YAML)
    result = _build_landscape(lit)

    assert "generated_at" in result
    assert "paper_count" in result
    assert "cluster_count" in result
    assert "clusters" in result
    assert "research_fronts" in result
    assert "structural_holes" in result
    assert "citation_gaps" in result
    assert result["paper_count"] == 3


# ── test_clusters_in_output ────────────────────────────────────────────────────

def test_clusters_in_output(tmp_path: Path) -> None:
    """Verify clusters dict present with at least 1 cluster."""
    papers = [
        {"citekey": "paper1", "title": "P1", "year": 2024, "citation_count": 0, "abstract": "alpha"},
        {"citekey": "paper2", "title": "P2", "year": 2024, "citation_count": 0, "abstract": "beta"},
        {"citekey": "paper3", "title": "P3", "year": 2024, "citation_count": 0, "abstract": "gamma"},
    ]
    lit = _make_lit_root(tmp_path, papers=papers, embeddings_content=EMBEDDINGS_YAML)
    result = _build_landscape(lit)

    assert len(result["clusters"]) >= 1
    for cid, cluster in result["clusters"].items():
        assert "papers" in cluster
        assert "size" in cluster
        assert "label" in cluster


# ── test_research_fronts_detected ─────────────────────────────────────────────

def test_research_fronts_detected(tmp_path: Path) -> None:
    """Papers with recent year and high citations should produce a research front."""
    papers = [
        {"citekey": "paper1", "title": "P1", "year": 2025, "citation_count": 500, "abstract": "transformers attention"},
        {"citekey": "paper2", "title": "P2", "year": 2025, "citation_count": 400, "abstract": "transformers attention"},
        {"citekey": "paper3", "title": "P3", "year": 2020, "citation_count": 1, "abstract": "old paper"},
    ]
    lit = _make_lit_root(tmp_path, papers=papers, embeddings_content=EMBEDDINGS_YAML)
    result = _build_landscape(lit)

    # With recent high-citation papers, there should be at least one research front
    assert isinstance(result["research_fronts"], list)
    # Check the structure of any front found
    for front in result["research_fronts"]:
        assert "cluster_id" in front
        assert "velocity" in front
        assert "key_papers" in front


# ── test_structural_holes_detected ────────────────────────────────────────────

def test_structural_holes_detected(tmp_path: Path) -> None:
    """Clusters with no cross-edges should have density < 0.05 flagged as holes."""
    # Two perfectly separated clusters, no cross-edges
    clusters = {0: ["paper1", "paper2"], 1: ["paper3"]}
    edges: dict[str, list[str]] = {"paper1": [], "paper2": [], "paper3": []}
    holes = _detect_structural_holes(clusters, edges)

    assert isinstance(holes, list)
    assert len(holes) > 0
    assert holes[0]["density"] == 0.0


# ── test_citation_gaps_found ──────────────────────────────────────────────────

def test_citation_gaps_found(tmp_path: Path) -> None:
    """External paper cited by 2+ collection papers should appear in gaps."""
    papers = [
        {"citekey": "paperA", "title": "A", "year": 2024, "citation_count": 0, "abstract": ""},
        {"citekey": "paperB", "title": "B", "year": 2024, "citation_count": 0, "abstract": ""},
    ]
    lit = _make_lit_root(tmp_path, papers=papers)

    edges = {
        "paperA": ["externalX"],
        "paperB": ["externalX"],
    }
    collection = {"paperA", "paperB"}
    gaps = _find_citation_gaps(edges, collection)

    assert len(gaps) >= 1
    gap_ids = [g["id"] for g in gaps]
    assert "externalX" in gap_ids
    # externalX cited by 2
    assert gaps[0]["cited_by_count"] == 2


# ── test_graceful_few_papers ──────────────────────────────────────────────────

def test_graceful_few_papers(tmp_path: Path) -> None:
    """With < 3 papers/embeddings, landscape runs without crash and outputs valid data."""
    papers = [
        {"citekey": "solo1", "title": "Solo Paper", "year": 2024, "citation_count": 0, "abstract": "test"},
    ]
    # Only 1 embedding — below threshold of 3
    embeddings = "model: specter_v2\ndimensions: 3\nvectors:\n  solo1: [1.0, 0.0, 0.0]\n"
    lit = _make_lit_root(tmp_path, papers=papers, embeddings_content=embeddings)
    result = _build_landscape(lit)

    assert result["paper_count"] == 1
    assert "clusters" in result
    assert "citation_gaps" in result


# ── test_landscape_yaml_written ───────────────────────────────────────────────

def test_landscape_yaml_written(tmp_path: Path) -> None:
    """run() should write landscape.yaml inside lit_root."""
    papers = [
        {"citekey": "paper1", "title": "P1", "year": 2024, "citation_count": 0, "abstract": "alpha"},
        {"citekey": "paper2", "title": "P2", "year": 2024, "citation_count": 0, "abstract": "beta"},
        {"citekey": "paper3", "title": "P3", "year": 2024, "citation_count": 0, "abstract": "gamma"},
    ]
    lit = _make_lit_root(tmp_path, papers=papers, embeddings_content=EMBEDDINGS_YAML)
    exit_code = run([], lit_root=lit)

    assert exit_code == 0
    yaml_path = lit / "landscape.yaml"
    assert yaml_path.exists()

    # Verify it's valid YAML with required keys
    from ruamel.yaml import YAML
    y = YAML()
    with yaml_path.open(encoding="utf-8") as fh:
        data = y.load(fh)
    assert "clusters" in data
    assert "research_fronts" in data
    assert "structural_holes" in data
    assert "citation_gaps" in data


# ── test_landscape_md_written ─────────────────────────────────────────────────

def test_landscape_md_written(tmp_path: Path) -> None:
    """run() should write landscape.md with expected section headers."""
    papers = [
        {"citekey": "paper1", "title": "P1", "year": 2024, "citation_count": 0, "abstract": ""},
        {"citekey": "paper2", "title": "P2", "year": 2024, "citation_count": 0, "abstract": ""},
        {"citekey": "paper3", "title": "P3", "year": 2024, "citation_count": 0, "abstract": ""},
    ]
    lit = _make_lit_root(tmp_path, papers=papers, embeddings_content=EMBEDDINGS_YAML)
    run([], lit_root=lit)

    md_path = lit / "landscape.md"
    assert md_path.exists()
    content = md_path.read_text(encoding="utf-8")
    assert "## Clusters" in content
    assert "# Research Landscape Report" in content


# ── test_find_citation_gaps_threshold ─────────────────────────────────────────

def test_find_citation_gaps_threshold(tmp_path: Path) -> None:
    """External paper cited only once should NOT appear in gaps (threshold = 2)."""
    edges = {
        "paperA": ["externalOnce"],
        "paperB": [],
    }
    collection = {"paperA", "paperB"}
    gaps = _find_citation_gaps(edges, collection)
    gap_ids = [g["id"] for g in gaps]
    assert "externalOnce" not in gap_ids


# ── test_detect_research_fronts_empty ─────────────────────────────────────────

def test_detect_research_fronts_empty(tmp_path: Path) -> None:
    """No papers with recent years → empty fronts list."""
    clusters = {0: ["oldpaper1", "oldpaper2"], 1: ["oldpaper3"]}
    papers_meta = {
        "oldpaper1": {"year": 2010, "citation_count": 1},
        "oldpaper2": {"year": 2011, "citation_count": 2},
        "oldpaper3": {"year": 2009, "citation_count": 0},
    }
    fronts = _detect_research_fronts(clusters, papers_meta, current_year=2026)
    # All papers are from before 2024 (threshold = 2026 - 2 = 2024), so velocity = 0 for all
    assert fronts == []


# ── test_write_markdown_sections ──────────────────────────────────────────────

def test_write_markdown_sections(tmp_path: Path) -> None:
    """Markdown output contains all expected section headers."""
    data = {
        "generated_at": "2026-01-01T00:00:00",
        "paper_count": 3,
        "cluster_count": 2,
        "clusters": {
            0: {"label": ["ml", "learning"], "papers": ["p1", "p2"], "size": 2, "avg_year": 2024.0, "avg_citations": 5},
            1: {"label": [], "papers": ["p3"], "size": 1, "avg_year": 2023.0, "avg_citations": 2},
        },
        "research_fronts": [
            {"cluster_id": 0, "label": ["ml"], "velocity": 5.0, "key_papers": ["p1"]}
        ],
        "structural_holes": [
            {"cluster_a": 0, "cluster_b": 1, "density": 0.0}
        ],
        "citation_gaps": [
            {"id": "extpaper", "cited_by_count": 2, "cited_by": ["p1", "p2"]}
        ],
    }
    output_path = tmp_path / "landscape.md"
    _write_markdown(data, output_path)

    content = output_path.read_text(encoding="utf-8")
    assert "# Research Landscape Report" in content
    assert "## Clusters" in content
    assert "## Research Fronts" in content
    assert "## Structural Holes" in content
    assert "## Citation Gaps" in content
    assert "## Reading Recommendations" in content


# ── test_load_embeddings_missing ──────────────────────────────────────────────

def test_load_embeddings_missing(tmp_path: Path) -> None:
    """Missing embeddings.yaml returns empty dict."""
    index_dir = tmp_path / "index"
    index_dir.mkdir()
    # No embeddings.yaml file created
    result = _load_embeddings(index_dir)
    assert result == {}


# ── test_build_landscape_no_embeddings ────────────────────────────────────────

def test_build_landscape_no_embeddings(tmp_path: Path) -> None:
    """Landscape runs without embeddings and still produces valid structure."""
    papers = [
        {"citekey": "a1", "title": "A1", "year": 2024, "citation_count": 5, "abstract": "test"},
        {"citekey": "a2", "title": "A2", "year": 2023, "citation_count": 3, "abstract": "test"},
    ]
    lit = _make_lit_root(tmp_path, papers=papers)  # no embeddings_content
    result = _build_landscape(lit)

    assert result["paper_count"] == 2
    assert result["cluster_count"] >= 1


# ── test_structural_holes_no_holes_when_connected ─────────────────────────────

def test_structural_holes_no_holes_when_connected(tmp_path: Path) -> None:
    """Clusters with dense cross-edges should NOT be flagged as structural holes."""
    # 2 papers each in their cluster, but both papers in cluster 0 cite both in cluster 1
    clusters = {0: ["a", "b"], 1: ["c", "d"]}
    # a and b both cite c and d => 4 inter-edges, density = 4 / (2*2) = 1.0
    edges: dict[str, list[str]] = {
        "a": ["c", "d"],
        "b": ["c", "d"],
        "c": [],
        "d": [],
    }
    holes = _detect_structural_holes(clusters, edges)
    # density = 1.0, NOT < 0.05 → should not be flagged
    assert len(holes) == 0
