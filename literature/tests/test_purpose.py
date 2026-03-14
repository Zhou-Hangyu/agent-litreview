"""Tests for literature.scripts.purpose — PURPOSE.md loader and keyword extractor."""

from __future__ import annotations

from pathlib import Path

import pytest

from literature.scripts.purpose import extract_keywords, load_purpose


def test_load_purpose_returns_empty_when_missing(tmp_path: Path) -> None:
    """load_purpose returns empty string when PURPOSE.md doesn't exist."""
    # Create a fake literature root without PURPOSE.md
    lit_root = tmp_path / "literature"
    lit_root.mkdir()
    (lit_root / "papers").mkdir()
    
    result = load_purpose(lit_root)
    assert result == ""


def test_load_purpose_returns_content(tmp_path: Path) -> None:
    """load_purpose reads and returns PURPOSE.md content."""
    # Create a fake literature root with PURPOSE.md
    lit_root = tmp_path / "literature"
    lit_root.mkdir()
    (lit_root / "papers").mkdir()
    
    purpose_content = "# Research Purpose\n\nTest content here."
    (lit_root / "PURPOSE.md").write_text(purpose_content, encoding="utf-8")
    
    result = load_purpose(lit_root)
    assert result == purpose_content


def test_extract_keywords_basic() -> None:
    """extract_keywords extracts meaningful tokens from text."""
    text = "limit order book simulation"
    result = extract_keywords(text)
    # All four words should be present (none are stopwords, all >= 3 chars)
    assert "limit" in result
    assert "order" in result
    assert "book" in result
    assert "simulation" in result


def test_extract_keywords_removes_stopwords() -> None:
    """extract_keywords filters out common stopwords."""
    text = "in the for a"
    result = extract_keywords(text)
    # All are stopwords, should be empty
    assert result == []


def test_extract_keywords_handles_empty() -> None:
    """extract_keywords returns empty list for empty input."""
    result = extract_keywords("")
    assert result == []


def test_extract_keywords_preserves_hyphens() -> None:
    """extract_keywords preserves hyphenated compound words."""
    text = "self-attention mechanism"
    result = extract_keywords(text)
    # "self-attention" should be preserved as a single token
    assert "self-attention" in result
    assert "mechanism" in result


def test_extract_keywords_min_length() -> None:
    """extract_keywords filters tokens shorter than 3 characters."""
    text = "go to do be"
    result = extract_keywords(text)
    # All are < 3 chars or stopwords, should be empty
    assert result == []


def test_extract_keywords_removes_markdown() -> None:
    """extract_keywords removes markdown syntax."""
    text = "# Research Questions\n\n- **transformer** architectures\n- *diffusion* models"
    result = extract_keywords(text)
    # Should extract transformer and diffusion, not markdown chars
    assert "transformer" in result
    assert "diffusion" in result
    assert "#" not in result
    assert "*" not in result


def test_extract_keywords_case_insensitive() -> None:
    """extract_keywords converts to lowercase."""
    text = "Transformer ATTENTION Self-Attention"
    result = extract_keywords(text)
    # All should be lowercase
    assert all(t.islower() for t in result)
    assert "transformer" in result
    assert "attention" in result
    assert "self-attention" in result


def test_extract_keywords_removes_urls() -> None:
    """extract_keywords removes URLs."""
    text = "See https://example.com/paper for details on transformers"
    result = extract_keywords(text)
    # Should have transformers but not URL parts
    assert "transformers" in result
    assert "https" not in result
    assert "example" not in result


def test_extract_keywords_complex_purpose() -> None:
    """extract_keywords handles realistic PURPOSE.md content."""
    text = """
# Research Purpose

## Research Questions
1. How do limit order books evolve?
2. What are market microstructure effects?

## Key Topics
- limit order book simulation
- market microstructure
- generative models for financial time series

## Methodology Focus
- transformer architectures
- diffusion models
- agent-based simulation
"""
    result = extract_keywords(text)
    # Check for key domain terms
    assert "limit" in result
    assert "order" in result
    assert "book" in result
    assert "market" in result
    assert "microstructure" in result
    assert "generative" in result
    assert "financial" in result
    assert "transformer" in result
    assert "diffusion" in result
    assert "agent-based" in result  # hyphenated terms preserved
    assert "simulation" in result
    # Should not have markdown or stopwords
    assert "#" not in result
    assert "the" not in result
    assert "and" not in result
