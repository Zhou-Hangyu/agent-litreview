"""Tests for the literature index rebuild script."""

from __future__ import annotations

import shutil
from pathlib import Path
from unittest.mock import patch

import pytest
from ruamel.yaml import YAML

from literature.scripts.parse import read_frontmatter
from literature.scripts.rebuild_index import (
    _fetch_embeddings,
    build_graph,
    build_status,
    format_bibtex,
    main,
    rebuild,
    scan_documents,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "papers"


# ── Helpers ────────────────────────────────────────────────────────────────────


def _load_yaml(path: Path) -> dict:
    """Load a YAML file and return its contents as a dict."""
    y = YAML()
    return y.load(path.read_text(encoding="utf-8"))


def _setup_literature_dir(tmp_path: Path, *, copy_fixtures: bool = True) -> Path:
    """Create a minimal literature directory structure."""
    root = tmp_path / "literature"
    papers_dir = root / "papers"
    papers_dir.mkdir(parents=True)
    (root / "resources").mkdir()

    if copy_fixtures:
        for fixture in sorted(FIXTURES_DIR.glob("*.md")):
            shutil.copy(fixture, papers_dir / fixture.name)

    return root


# ── Tests ──────────────────────────────────────────────────────────────────────


def test_graph_yaml_nodes_correct(tmp_path: Path) -> None:
    """Two papers produce graph.yaml with both nodes and correct fields."""
    root = _setup_literature_dir(tmp_path)
    rebuild(root)

    graph = _load_yaml(root / "index" / "graph.yaml")

    assert "vaswani2017attention" in graph["nodes"]
    assert "devlin2019bert" in graph["nodes"]

    vaswani = graph["nodes"]["vaswani2017attention"]
    assert vaswani["title"] == "Attention Is All You Need"
    assert vaswani["year"] == 2017
    assert vaswani["resource_type"] == "paper"
    assert vaswani["citation_count"] == 50000
    assert vaswani["venue"] == "NeurIPS"
    assert "Vaswani, A." in vaswani["authors"]
    assert "transformers" in vaswani["tags"]
    assert "attention" in vaswani["themes"]

    devlin = graph["nodes"]["devlin2019bert"]
    assert devlin["title"] == "BERT: Pre-training of Deep Bidirectional Transformers"
    assert devlin["year"] == 2019
    assert devlin["citation_count"] == 10000


def test_graph_yaml_edges_correct(tmp_path: Path) -> None:
    """Paper B cites Paper A — edge should be present with correct keys."""
    root = _setup_literature_dir(tmp_path)
    rebuild(root)

    graph = _load_yaml(root / "index" / "graph.yaml")
    edges = graph["edges"]

    assert len(edges) == 1
    edge = edges[0]
    assert edge["from"] == "devlin2019bert"
    assert edge["to"] == "vaswani2017attention"
    assert edge["type"] == "extends"


def test_status_yaml_global_grouping(tmp_path: Path) -> None:
    """Global status should sort citekeys into correct buckets."""
    root = _setup_literature_dir(tmp_path)
    rebuild(root)

    status = _load_yaml(root / "index" / "status.yaml")
    g = status["global"]

    # Paper A global = synthesized, Paper B global = read
    assert "devlin2019bert" in g["read"]
    assert "vaswani2017attention" in g["synthesized"]
    assert not g["unread"]
    assert not g["skimmed"]


def test_status_yaml_per_collaborator(tmp_path: Path) -> None:
    """hangyu and junghun sections reflect per-paper reading status."""
    root = _setup_literature_dir(tmp_path)
    rebuild(root)

    status = _load_yaml(root / "index" / "status.yaml")

    # hangyu: read vaswani (explicit), unread devlin (missing entry)
    assert "hangyu" in status
    assert "vaswani2017attention" in status["hangyu"]["read"]
    assert "devlin2019bert" in status["hangyu"]["unread"]

    # junghun: skimmed devlin (explicit), unread vaswani (missing entry)
    assert "junghun" in status
    assert "devlin2019bert" in status["junghun"]["skimmed"]
    assert "vaswani2017attention" in status["junghun"]["unread"]


def test_references_bib_article_entry(tmp_path: Path) -> None:
    """Vaswani paper should produce @article entry with correct fields."""
    root = _setup_literature_dir(tmp_path)
    rebuild(root)

    bib = (root / "index" / "references.bib").read_text(encoding="utf-8")

    # Header
    assert bib.startswith("%")

    # Vaswani entry
    assert "@article{vaswani2017attention," in bib
    assert "title = {Attention Is All You Need}," in bib
    assert "author = {Vaswani, A. and Shazeer, N.}," in bib
    assert "journal = {NeurIPS}," in bib
    assert "year = {2017}," in bib
    assert "doi = {10.48550/arXiv.1706.03762}," in bib

    # Devlin entry should also be @article (has venue)
    assert "@article{devlin2019bert," in bib

    # Devlin comes before Vaswani alphabetically
    devlin_pos = bib.index("@article{devlin2019bert,")
    vaswani_pos = bib.index("@article{vaswani2017attention,")
    assert devlin_pos < vaswani_pos


def test_rebuild_deterministic(tmp_path: Path) -> None:
    """Running rebuild twice produces byte-identical output."""
    root = _setup_literature_dir(tmp_path)

    rebuild(root)
    graph1 = (root / "index" / "graph.yaml").read_bytes()
    status1 = (root / "index" / "status.yaml").read_bytes()
    bib1 = (root / "index" / "references.bib").read_bytes()

    rebuild(root)
    graph2 = (root / "index" / "graph.yaml").read_bytes()
    status2 = (root / "index" / "status.yaml").read_bytes()
    bib2 = (root / "index" / "references.bib").read_bytes()

    assert graph1 == graph2
    assert status1 == status2
    assert bib1 == bib2


def test_rebuild_empty_papers_dir(tmp_path: Path) -> None:
    """Empty papers directory produces valid but empty index files."""
    root = _setup_literature_dir(tmp_path, copy_fixtures=False)
    rebuild(root)

    # graph.yaml — empty nodes and edges
    graph = _load_yaml(root / "index" / "graph.yaml")
    assert len(graph["nodes"]) == 0
    assert len(graph["edges"]) == 0

    # status.yaml — global section with empty buckets
    status = _load_yaml(root / "index" / "status.yaml")
    assert "global" in status
    for bucket in ("read", "skimmed", "synthesized", "unread"):
        assert not status["global"][bucket]

    # references.bib — just the header
    bib = (root / "index" / "references.bib").read_text(encoding="utf-8")
    assert bib.startswith("%")
    assert "@" not in bib


def test_rebuild_backfills_cited_by_in_paper_files(tmp_path: Path) -> None:
    root = _setup_literature_dir(tmp_path)
    rebuild(root)

    vaswani_meta, _ = read_frontmatter(root / "papers" / "paper_a.md")
    cited_by = vaswani_meta.get("cited_by") or []
    assert len(cited_by) == 1
    entry = cited_by[0]
    assert str(entry["id"]) == "devlin2019bert"
    assert str(entry["type"]) == "extends"

    devlin_meta, _ = read_frontmatter(root / "papers" / "paper_b.md")
    assert (devlin_meta.get("cited_by") or []) == []


def test_rebuild_cited_by_idempotent(tmp_path: Path) -> None:
    root = _setup_literature_dir(tmp_path)
    rebuild(root)
    content_after_first = (root / "papers" / "paper_a.md").read_bytes()

    rebuild(root)
    content_after_second = (root / "papers" / "paper_a.md").read_bytes()

    assert content_after_first == content_after_second


def test_rebuild_skips_no_frontmatter(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """File without frontmatter delimiters is skipped with a warning."""
    root = _setup_literature_dir(tmp_path, copy_fixtures=False)

    no_fm = root / "papers" / "no_frontmatter.md"
    no_fm.write_text(
        "# Just a title\n\nNo YAML frontmatter here.\n",
        encoding="utf-8",
    )

    rebuild(root)

    captured = capsys.readouterr()
    assert "no frontmatter" in captured.err.lower()

    # Document was skipped — graph should be empty
    graph = _load_yaml(root / "index" / "graph.yaml")
    assert len(graph["nodes"]) == 0


# ── Embedding tests ───────────────────────────────────────────────────────────

_MOCK_VECTOR = [round(i * 0.001, 4) for i in range(768)]

_PAPER_WITH_S2ID = """\
---
doc_id: "test_paper_s2"
title: "Test Paper With S2 ID"
authors:
  - "Test, A."
year: 2024
resource_type: paper
s2_id: "abc123def456"
reading_status:
  global: "unread"
tags: []
themes: []
cites: []
cited_by: []
---

# Notes
"""

_PAPER_WITHOUT_S2ID = """\
---
doc_id: "test_paper_no_s2"
title: "Test Paper Without S2 ID"
authors:
  - "Test, B."
year: 2024
resource_type: paper
reading_status:
  global: "unread"
tags: []
themes: []
cites: []
cited_by: []
---

# Notes
"""


def _setup_with_s2_papers(
    tmp_path: Path, *, include_no_s2: bool = False,
) -> Path:
    """Create literature dir with paper(s) that have s2_id."""
    root = tmp_path / "literature"
    papers_dir = root / "papers"
    papers_dir.mkdir(parents=True)
    (root / "resources").mkdir()

    (papers_dir / "test_paper_s2.md").write_text(
        _PAPER_WITH_S2ID, encoding="utf-8",
    )
    if include_no_s2:
        (papers_dir / "test_paper_no_s2.md").write_text(
            _PAPER_WITHOUT_S2ID, encoding="utf-8",
        )
    return root


def _mock_batch_response(
    s2_id: str = "abc123def456",
) -> list[dict]:
    """Build a mock batch response with embedding for one paper."""
    return [
        {
            "paperId": s2_id,
            "embedding": {
                "model": "specter_v2",
                "vector": _MOCK_VECTOR,
            },
        },
    ]


def test_embeddings_generated_with_api_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When S2_API_KEY is set, embeddings.yaml is written with correct structure."""
    root = _setup_with_s2_papers(tmp_path)
    monkeypatch.setenv("S2_API_KEY", "test-key")

    with patch(
        "literature.scripts.rebuild_index.fetch_papers_batch",
        return_value=_mock_batch_response(),
    ):
        rebuild(root)

    emb_path = root / "index" / "embeddings.yaml"
    assert emb_path.exists()

    data = _load_yaml(emb_path)
    assert data["model"] == "specter_v2"
    assert data["dimensions"] == 768
    assert "test_paper_s2" in data["vectors"]
    assert len(data["vectors"]["test_paper_s2"]) == 768


def test_embeddings_skipped_without_api_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without S2_API_KEY, no embeddings.yaml is created."""
    root = _setup_with_s2_papers(tmp_path)
    monkeypatch.delenv("S2_API_KEY", raising=False)

    rebuild(root)

    emb_path = root / "index" / "embeddings.yaml"
    assert not emb_path.exists()


def test_embeddings_skipped_with_flag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """--skip-embeddings flag prevents embedding fetch even with API key."""
    root = _setup_with_s2_papers(tmp_path)
    monkeypatch.setenv("S2_API_KEY", "test-key")

    with patch(
        "literature.scripts.rebuild_index.fetch_papers_batch",
    ) as mock_fetch:
        rebuild(root, skip_embeddings=True)
        mock_fetch.assert_not_called()

    emb_path = root / "index" / "embeddings.yaml"
    assert not emb_path.exists()


def test_embeddings_skips_papers_without_s2_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Papers without s2_id are silently skipped in embedding fetch."""
    root = _setup_with_s2_papers(tmp_path, include_no_s2=True)
    monkeypatch.setenv("S2_API_KEY", "test-key")

    with patch(
        "literature.scripts.rebuild_index.fetch_papers_batch",
        return_value=_mock_batch_response(),
    ) as mock_fetch:
        rebuild(root)

    # Only the paper with s2_id should be in the batch call
    call_args = mock_fetch.call_args
    assert call_args[0][0] == ["abc123def456"]

    data = _load_yaml(root / "index" / "embeddings.yaml")
    assert "test_paper_s2" in data["vectors"]
    assert "test_paper_no_s2" not in data["vectors"]


def test_embeddings_handles_null_from_batch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Batch returning None for a paper does not crash."""
    root = _setup_with_s2_papers(tmp_path)
    monkeypatch.setenv("S2_API_KEY", "test-key")

    with patch(
        "literature.scripts.rebuild_index.fetch_papers_batch",
        return_value=[None],  # Paper not found in S2
    ):
        rebuild(root)

    emb_path = root / "index" / "embeddings.yaml"
    # No vectors => file not written
    assert not emb_path.exists()
