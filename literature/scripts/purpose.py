"""Purpose document loader and keyword extractor for relevance scoring."""
from __future__ import annotations

import re
from pathlib import Path


# Common English stopwords (not the full NLTK set — just enough)
_STOPWORDS = frozenset({
    "a", "an", "the", "of", "in", "on", "at", "to", "for", "with",
    "and", "or", "but", "is", "are", "was", "were", "be", "been",
    "have", "has", "had", "do", "does", "did", "will", "would",
    "can", "could", "should", "may", "might", "this", "that",
    "these", "those", "i", "we", "you", "it", "its", "they", "their",
    "what", "how", "when", "where", "which", "who", "from", "as",
    "by", "not", "no", "more", "also", "than", "into", "about",
    "use", "using", "used", "paper", "papers", "model", "models",
    "method", "methods", "approach", "e", "g", "etc",
})


def load_purpose(root: Path) -> str:
    """Load PURPOSE.md content. Returns empty string if not found."""
    # Find literature/ root the same way other scripts do
    lit_root = _find_literature_root(root)
    purpose_path = lit_root / "PURPOSE.md"
    if not purpose_path.exists():
        return ""
    return purpose_path.read_text(encoding="utf-8")


def extract_keywords(purpose_text: str) -> list[str]:
    """Extract meaningful keywords from purpose text for BM25 matching.
    
    Returns lowercase tokens, stopwords removed, length ≥ 3.
    Preserves hyphenated terms (e.g. 'order-book') as single tokens.
    """
    # Lowercase
    text = purpose_text.lower()
    # Remove markdown syntax but keep hyphens in compound words
    text = re.sub(r"#+\s+", " ", text)      # headings
    text = re.sub(r"[*_`\[\]()]", " ", text)  # markdown punctuation
    text = re.sub(r"\bhttps?://\S+", " ", text)  # URLs
    # Split on whitespace and non-word chars (preserving hyphens)
    tokens = re.findall(r"[a-z][a-z0-9-]*[a-z0-9]|[a-z]{3,}", text)
    # Filter stopwords and short tokens
    return [t for t in tokens if t not in _STOPWORDS and len(t) >= 3]


def _find_literature_root(start: Path) -> Path:
    """Walk up from start to find the literature/ directory."""
    current = start.resolve()
    for _ in range(6):
        candidate = current / "literature"
        if candidate.is_dir():
            return candidate
        if current.parent == current:
            break
        current = current.parent
    # Fallback: assume start IS the literature root
    if (start / "papers").is_dir():
        return start
    return start
