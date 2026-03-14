"""
End-to-end integration test: enrich → rebuild → generate → compile.

Uses mocked S2 API responses (no real network calls).
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

import pytest
import responses as resp_lib

from literature.scripts.enrich import enrich_paper
from literature.scripts.rebuild_index import rebuild
from literature.scripts.generate_review import generate

FIXTURES_DIR = Path(__file__).parent / "fixtures"
S2_BASE = "https://api.semanticscholar.org/graph/v1/paper"
VASWANI_URL = re.compile(
    r"https://api\.semanticscholar\.org/graph/v1/paper/arXiv:1706\.03762"
)
DEVLIN_URL = re.compile(
    r"https://api\.semanticscholar\.org/graph/v1/paper/arXiv:1810\.04805"
)


def _vaswani_response() -> dict:
    return {
        "paperId": "204e3073870fae3d05bcbc2f6a8e263d9b72e776",
        "title": "Attention Is All You Need",
        "abstract": "The dominant sequence transduction models are based on complex recurrent or convolutional neural networks.",
        "authors": [{"authorId": "1", "name": "Ashish Vaswani"}, {"authorId": "2", "name": "Noam Shazeer"}],
        "year": 2017,
        "venue": "NeurIPS",
        "citationCount": 50000,
        "externalIds": {"ArXiv": "1706.03762", "DOI": "10.48550/arXiv.1706.03762"},
        "tldr": {"text": "A simple network architecture based solely on attention mechanisms."},
        "publicationVenue": {"name": "NeurIPS"},
    }


def _devlin_response() -> dict:
    return {
        "paperId": "df2b0e26d0599ce3e70df8a9da02e51594e0e992",
        "title": "BERT: Pre-training of Deep Bidirectional Transformers",
        "abstract": "We introduce a new language representation model called BERT.",
        "authors": [{"authorId": "3", "name": "Jacob Devlin"}, {"authorId": "4", "name": "Ming-Wei Chang"}],
        "year": 2019,
        "venue": "NAACL",
        "citationCount": 100000,
        "externalIds": {"ArXiv": "1810.04805", "DOI": "10.18653/v1/N19-1423"},
        "tldr": {"text": "BERT is designed to pre-train deep bidirectional representations."},
        "publicationVenue": {"name": "NAACL"},
    }


def _make_lit_dir(tmp_path: Path) -> Path:
    root = tmp_path / "literature"
    for d in ("papers", "resources", "themes", "index", "output", "templates"):
        (root / d).mkdir(parents=True)
    (root / "AGENTS.md").write_text("# Literature\n", encoding="utf-8")
    src = Path(__file__).parents[2] / "literature" / "templates"
    for f in src.glob("*"):
        shutil.copy2(f, root / "templates" / f.name)
    return root


@resp_lib.activate
def test_full_pipeline_enrich_rebuild_generate(tmp_path: Path) -> None:
    """Full pipeline: enrich 2 papers → add relationship → rebuild → generate."""
    root = _make_lit_dir(tmp_path)

    # Mock S2 API for both papers
    resp_lib.add(resp_lib.GET, VASWANI_URL, json=_vaswani_response(), status=200)
    resp_lib.add(resp_lib.GET, DEVLIN_URL, json=_devlin_response(), status=200)

    # Step 1: Enrich papers
    p1 = enrich_paper("https://arxiv.org/abs/1706.03762", root)
    p2 = enrich_paper("https://arxiv.org/abs/1810.04805", root)
    assert p1.exists(), "vaswani paper file should be created"
    assert p2.exists(), "devlin paper file should be created"

    # Step 2: Add relationship (BERT extends Attention)
    content = p2.read_text(encoding="utf-8")
    content = content.replace("cites: []", "cites:\n- id: vaswani2017attention\n  type: extends")
    p2.write_text(content, encoding="utf-8")

    # Step 3: Rebuild indexes
    rebuild(root)

    graph_path = root / "index" / "graph.yaml"
    status_path = root / "index" / "status.yaml"
    bib_path = root / "index" / "references.bib"
    assert graph_path.exists()
    assert status_path.exists()
    assert bib_path.exists()

    # Step 4: Verify graph has both nodes and the edge
    from ruamel.yaml import YAML
    y = YAML()
    graph = y.load(graph_path.read_text(encoding="utf-8"))
    assert "vaswani2017attention" in graph["nodes"]
    assert "devlin2019bert" in graph["nodes"]
    assert len(graph["edges"]) == 1
    edge = graph["edges"][0]
    assert edge["from"] == "devlin2019bert"
    assert edge["to"] == "vaswani2017attention"
    assert edge["type"] == "extends"

    # Step 5: Create a theme file with citations
    theme = root / "themes" / "01-transformers.md"
    theme.write_text(
        '---\ntitle: "Transformer Models"\norder: 1\n---\n\n'
        r'The Transformer \cite{vaswani2017attention} introduced self-attention. '
        r'BERT \cite{devlin2019bert} extended it.' + "\n",
        encoding="utf-8",
    )

    # Step 6: Generate review
    tex_path = generate(root, title="My Test Survey", authors="Test Author")
    assert tex_path.exists()
    content = tex_path.read_text(encoding="utf-8")

    # Verify required content
    assert "neurips_2025" in content, "Should use neurips_2025 package"
    assert r"\bibliographystyle{plainnat}" in content
    assert "Transformer Models" in content, "Theme section should appear"
    assert r"\cite{vaswani2017attention}" in content
    assert (root / "output" / "references.bib").exists()

    # Verify BibTeX has both entries
    bib_out = (root / "output" / "references.bib").read_text(encoding="utf-8")
    assert "vaswani2017attention" in bib_out
    assert "devlin2019bert" in bib_out


@resp_lib.activate
def test_duplicate_paper_not_overwritten(tmp_path: Path) -> None:
    """Second enrich with same arXiv ID prints warning, does not overwrite."""
    root = _make_lit_dir(tmp_path)
    resp_lib.add(resp_lib.GET, VASWANI_URL, json=_vaswani_response(), status=200)

    p1 = enrich_paper("https://arxiv.org/abs/1706.03762", root)
    mtime1 = p1.stat().st_mtime

    # Second call — no additional mock needed since it should short-circuit
    enrich_paper("https://arxiv.org/abs/1706.03762", root)
    assert p1.stat().st_mtime == mtime1, "File should not be modified on duplicate"


def test_rebuild_with_real_seeded_papers() -> None:
    """Verify the real seeded papers in literature/papers/ are valid."""
    repo_root = Path(__file__).parents[2]
    lit_root = repo_root / "literature"
    papers_dir = lit_root / "papers"

    if not papers_dir.exists() or not any(papers_dir.glob("*.md")):
        pytest.skip("No seeded papers found — run enrich.py first")

    # Run rebuild on real literature dir
    count = rebuild(lit_root)
    assert len(list((lit_root / "papers").glob("*.md"))) >= 3

    graph_path = lit_root / "index" / "graph.yaml"
    assert graph_path.exists()
    from ruamel.yaml import YAML
    y = YAML()
    graph = y.load(graph_path.read_text(encoding="utf-8"))
    assert len(graph["nodes"]) >= 3

    # Verify at least one edge exists (devlin2019bert extends vaswani2017attention)
    assert len(graph["edges"]) >= 1
