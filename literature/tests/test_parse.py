"""Tests for literature.scripts.parse — YAML frontmatter and citekey utilities."""

from __future__ import annotations

from pathlib import Path

import pytest

from literature.scripts.parse import (
    generate_citekey,
    get_summary,
    is_summary_stale,
    normalize_paper_id,
    read_frontmatter,
    resolve_citekey_collision,
    set_summary,
    write_paper_file,
)


# ── Fixture path ───────────────────────────────────────────────────────────────

FIXTURES_DIR = Path(__file__).parent / "fixtures"


# ── read_frontmatter / write_paper_file ────────────────────────────────────────

def test_roundtrip(tmp_path: Path) -> None:
    """write_paper_file → read_frontmatter preserves metadata."""
    meta = {
        "doc_id": "test2024roundtrip",
        "title": "Round-Trip Test",
        "authors": ["Doe, J."],
        "year": 2024,
        "tags": ["testing"],
    }
    body = "## Notes\n\nSome notes here.\n"
    p = tmp_path / "test.md"

    write_paper_file(p, meta, body)
    got_meta, got_body = read_frontmatter(p)

    assert got_meta["doc_id"] == "test2024roundtrip"
    assert got_meta["title"] == "Round-Trip Test"
    assert got_meta["authors"] == ["Doe, J."]
    assert got_meta["year"] == 2024
    assert got_meta["tags"] == ["testing"]
    assert "Some notes here." in got_body


def test_yaml_boolean_safety(tmp_path: Path) -> None:
    """Strings like 'no'/'yes' must survive round-trip as strings, not booleans."""
    meta = {
        "doc_id": "booltest",
        "title": "Boolean Safety",
        "reading_status": "no",
    }
    p = tmp_path / "bool.md"

    write_paper_file(p, meta)
    got_meta, _ = read_frontmatter(p)

    assert got_meta["reading_status"] == "no"
    assert isinstance(got_meta["reading_status"], str)


def test_read_frontmatter_no_delimiters(tmp_path: Path) -> None:
    """Files without --- delimiters return empty metadata and full text as body."""
    p = tmp_path / "plain.md"
    p.write_text("Just plain markdown.\n", encoding="utf-8")

    meta, body = read_frontmatter(p)

    assert meta == {}
    assert "Just plain markdown." in body


def test_read_fixture_sample_paper() -> None:
    """Read the bundled sample_paper.md fixture."""
    p = FIXTURES_DIR / "sample_paper.md"
    meta, body = read_frontmatter(p)

    assert meta["doc_id"] == "vaswani2017attention"
    assert meta["title"] == "Attention Is All You Need"
    assert meta["year"] == 2017
    assert "Transformer" in body


# ── generate_citekey ───────────────────────────────────────────────────────────

def test_citekey_normal() -> None:
    key = generate_citekey(["Vaswani, A."], 2017, "Attention Is All You Need")
    assert key == "vaswani2017attention"


def test_citekey_unicode() -> None:
    key = generate_citekey(["Müller, J."], 2020, "Deep Learning")
    assert key == "muller2020deep"


def test_citekey_latex_math() -> None:
    """LaTeX math ($...$) is stripped; the next real word is used."""
    key = generate_citekey(
        ["Smith, A."], 2021, "$\\alpha$ Divergence Minimization"
    )
    assert key == "smith2021divergence"


def test_citekey_stop_words() -> None:
    """Stop words at the start of the title are skipped."""
    key = generate_citekey(["Lee, B."], 2019, "The Art of Approximation")
    assert key == "lee2019art"


def test_citekey_first_last_format() -> None:
    """Author in 'First Last' format extracts lastname correctly."""
    key = generate_citekey(["Ashish Vaswani"], 2017, "Attention Is All You Need")
    assert key == "vaswani2017attention"


# ── resolve_citekey_collision ──────────────────────────────────────────────────

def test_citekey_collision(tmp_path: Path) -> None:
    """When {citekey}.md exists, returns {citekey}b."""
    (tmp_path / "vaswani2017attention.md").touch()

    result = resolve_citekey_collision("vaswani2017attention", tmp_path)
    assert result == "vaswani2017attentionb"


def test_citekey_no_collision(tmp_path: Path) -> None:
    """When no collision, return the citekey unchanged."""
    result = resolve_citekey_collision("brand_new_key", tmp_path)
    assert result == "brand_new_key"


# ── normalize_paper_id ─────────────────────────────────────────────────────────

def test_normalize_arxiv_url() -> None:
    assert normalize_paper_id("https://arxiv.org/abs/1706.03762") == (
        "arxiv",
        "1706.03762",
    )


def test_normalize_arxiv_pdf_with_version() -> None:
    assert normalize_paper_id("https://arxiv.org/pdf/1706.03762v3") == (
        "arxiv",
        "1706.03762",
    )


def test_normalize_arxiv_abs_with_version() -> None:
    assert normalize_paper_id("https://arxiv.org/abs/1706.03762v2") == (
        "arxiv",
        "1706.03762",
    )


def test_normalize_arxiv_prefix() -> None:
    assert normalize_paper_id("arXiv:1706.03762") == ("arxiv", "1706.03762")


def test_normalize_arxiv_prefix_lowercase() -> None:
    assert normalize_paper_id("arxiv:1706.03762") == ("arxiv", "1706.03762")


def test_normalize_bare_arxiv() -> None:
    assert normalize_paper_id("1706.03762") == ("arxiv", "1706.03762")


def test_normalize_doi() -> None:
    assert normalize_paper_id("10.1145/3442188.3445922") == (
        "doi",
        "10.1145/3442188.3445922",
    )


def test_normalize_doi_url() -> None:
    assert normalize_paper_id("https://doi.org/10.1145/3442188.3445922") == (
        "doi",
        "10.1145/3442188.3445922",
    )


def test_normalize_invalid() -> None:
    with pytest.raises(ValueError, match="Unrecognized"):
        normalize_paper_id("not-a-valid-url")


# ── set_summary / get_summary / is_summary_stale ────────────────────────────────

def test_set_summary_l4_creates_provenance() -> None:
    """set_summary with l4 level stores text, model, and generated_at."""
    meta: dict = {"doc_id": "test2024summary"}
    set_summary(meta, "l4", "Transformer architecture using only attention.", "claude-opus-4-6")

    assert "summaries" in meta
    assert "l4" in meta["summaries"]
    summary = meta["summaries"]["l4"]
    assert summary["text"] == "Transformer architecture using only attention."
    assert summary["model"] == "claude-opus-4-6"
    assert "generated_at" in summary
    assert summary["generated_at"].endswith("Z")  # ISO 8601 format


def test_set_summary_l2_stores_list() -> None:
    """set_summary with l2 level stores claims list, model, and generated_at."""
    meta: dict = {"doc_id": "test2024claims"}
    claims = ["Self-attention replaces recurrence.", "Parallelizable architecture.", "State-of-the-art results."]
    set_summary(meta, "l2", claims, "claude-sonnet-4-20250514")

    assert "summaries" in meta
    assert "l2" in meta["summaries"]
    summary = meta["summaries"]["l2"]
    assert summary["claims"] == claims
    assert summary["model"] == "claude-sonnet-4-20250514"
    assert "generated_at" in summary


def test_get_summary_returns_none_when_missing() -> None:
    """get_summary returns None when paper has no summaries key."""
    meta: dict = {"doc_id": "test2024nosummary"}
    result = get_summary(meta, "l4")
    assert result is None


def test_get_summary_returns_none_for_missing_level() -> None:
    """get_summary returns None when summaries dict exists but level is missing."""
    meta: dict = {"summaries": {"l4": {"text": "...", "model": "test", "generated_at": "2026-03-14T00:00:00Z"}}}
    result = get_summary(meta, "l2")
    assert result is None


def test_summary_survives_yaml_roundtrip(tmp_path: Path) -> None:
    """Summary with provenance survives write_paper_file → read_frontmatter roundtrip."""
    meta = {
        "doc_id": "test2024roundtrip",
        "title": "Summary Roundtrip Test",
        "authors": ["Doe, J."],
        "year": 2024,
    }
    set_summary(meta, "l4", "A concise summary.", "test-model-v1")
    set_summary(meta, "l2", ["Claim 1", "Claim 2"], "test-model-v2")

    p = tmp_path / "roundtrip.md"
    write_paper_file(p, meta, "## Notes\n\nTest notes.")
    got_meta, got_body = read_frontmatter(p)

    # Verify l4 summary
    l4 = get_summary(got_meta, "l4")
    assert l4 is not None
    assert l4["text"] == "A concise summary."
    assert l4["model"] == "test-model-v1"
    assert "generated_at" in l4

    # Verify l2 summary
    l2 = get_summary(got_meta, "l2")
    assert l2 is not None
    assert l2["claims"] == ["Claim 1", "Claim 2"]
    assert l2["model"] == "test-model-v2"
    assert "generated_at" in l2


def test_is_summary_stale_true_when_missing() -> None:
    """is_summary_stale returns True when summary is not present."""
    meta: dict = {"doc_id": "test2024nostale"}
    assert is_summary_stale(meta, "l4") is True
    assert is_summary_stale(meta, "l2") is True


def test_is_summary_stale_false_when_fresh() -> None:
    """is_summary_stale returns False when summary was just created."""
    meta: dict = {"doc_id": "test2024fresh"}
    set_summary(meta, "l4", "Fresh summary.", "test-model")
    assert is_summary_stale(meta, "l4", max_age_days=90) is False


def test_set_summary_invalid_level_raises() -> None:
    """set_summary raises ValueError for invalid level."""
    meta: dict = {"doc_id": "test2024invalid"}
    with pytest.raises(ValueError, match="Unknown summary level"):
        set_summary(meta, "l3", "Invalid level.", "test-model")


def test_summary_roundtrip_real_paper(tmp_path: Path) -> None:
    """Integration test: set summary on real paper file, roundtrip, verify."""
    # Copy vaswani2017attention.md to tmp_path
    real_paper = FIXTURES_DIR / "sample_paper.md"
    test_paper = tmp_path / "vaswani2017attention.md"
    test_paper.write_text(real_paper.read_text(encoding="utf-8"), encoding="utf-8")

    # Read frontmatter
    meta, body = read_frontmatter(test_paper)

    # Set summaries
    set_summary(meta, "l4", "Transformer architecture using only attention.", "claude-opus-4-6")
    set_summary(meta, "l2", ["Self-attention mechanism", "Parallelizable", "SOTA results"], "claude-sonnet-4-20250514")

    # Write back
    write_paper_file(test_paper, meta, body)

    # Read again
    meta2, body2 = read_frontmatter(test_paper)

    # Verify l4
    l4 = get_summary(meta2, "l4")
    assert l4 is not None
    assert l4["text"] == "Transformer architecture using only attention."
    assert l4["model"] == "claude-opus-4-6"

    # Verify l2
    l2 = get_summary(meta2, "l2")
    assert l2 is not None
    assert l2["claims"] == ["Self-attention mechanism", "Parallelizable", "SOTA results"]
    assert l2["model"] == "claude-sonnet-4-20250514"

    # Verify body is preserved
    assert "Transformer" in body2
