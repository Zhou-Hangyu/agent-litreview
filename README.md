# agent-litreview

Agent-native literature review system. BM25 search, citation PageRank, funnel retrieval, and progressive summarization over 10K+ papers.

No server, no GPU, no vector database. Pure SQLite + Python. Runs locally in any project.

## Installation

```bash
pip install agent-litreview
# or
uv add agent-litreview
```

## Quick Start

```bash
# 1. Scaffold a literature/ directory in your project
lit init

# 2. Define your research goals
edit literature/PURPOSE.md

# 3. Add papers
lit add "https://arxiv.org/abs/1706.03762"

# 4. Build the index
lit rebuild

# 5. See what to read next
lit recommend 5

# 6. Search
lit search "attention mechanism"

# 7. Ask synthesis questions
lit ask "What are the key contributions of transformer models?" --depth 2
```

## Agent Integration

Install the skill for AI agents (opencode, Claude Code):

```bash
lit install-skill
```

This copies `SKILL.md` to `~/.agents/skills/literature-review/` so agents auto-detect the literature system.

## Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) (recommended) or pip

## Setup

### 1. Initialize a Literature Directory

```bash
cd /path/to/your-project
lit init
```

This creates `literature/` with scaffold files (PURPOSE.md, AGENTS.md, empty directories).

### 2. Define Your Research Purpose

Edit `literature/PURPOSE.md`:

```markdown
# Research Purpose

## Research Questions

1. How can we build more efficient attention mechanisms?
2. What role do foundation models play in scientific discovery?

## Key Topics

- transformer architectures
- self-attention mechanisms
- large language models

## Methodology Focus

- efficient transformers
- sparse attention

## Exclusions

- non-transformer sequence models
```

This file drives the recommendation engine. Without it, recommendations still work (using PageRank + recency), but with it, papers relevant to your research questions rank higher.

### 3. Add Your First Papers

```bash
# From arXiv URL
lit add "https://arxiv.org/abs/1706.03762"

# From DOI
lit add "10.1145/3442188.3445922"

# Non-paper resource (blog, talk, code)
uv run python -m literature.scripts.enrich --type blog "https://example.com/post" --title "Great Blog Post"
```

Each paper gets a markdown file in `literature/papers/` with metadata fetched from Semantic Scholar.

### 4. Build the Index

```bash
lit rebuild
```

Creates `literature/index/papers.db` — a SQLite database with BM25 full-text search, citation graph, and PageRank scores. Rebuild after every change to paper files.

### 5. Start Working

```bash
# What should I read next?
lit recommend 5

# Search for papers on a topic
lit search "transformer attention mechanism"

# Ask a synthesis question across all papers
lit ask "What approaches exist for efficient attention?" --depth 2

# Find new papers to add
lit discover --source s2
lit inbox
```

## Daily Workflow

```
Add paper   →  lit add "url"              →  paper file created (unread)
Rebuild     →  lit rebuild                 →  SQLite index synced
Recommend   →  lit recommend 5             →  what to read next
Search      →  lit search "topic"          →  BM25 full-text search
Read        →  edit the .md file           →  add notes, update reading_status
Summarize   →  Python API (see below)      →  store L4/L2 with model provenance
Rebuild     →  lit rebuild                 →  sync summaries into search index
Ask         →  lit ask "question"          →  funnel retrieval for cross-paper synthesis
Discover    →  lit discover --source s2    →  find new relevant papers
Generate    →  lit generate --title "..."  →  NeurIPS LaTeX review
```

## Summarization API

After reading a paper, store summaries with provenance:

```python
from literature.scripts.parse import read_frontmatter, write_paper_file, set_summary
from pathlib import Path

meta, body = read_frontmatter(Path("literature/papers/vaswani2017attention.md"))

# L4: one-sentence synthesis (20-30 words)
set_summary(meta, "l4",
    "Transformer replaces recurrence entirely with self-attention for sequence transduction, achieving state-of-the-art BLEU with greater parallelism.",
    "claude-opus-4-6")  # always record the model name

# L2: key claims (3-5 bullet points)
set_summary(meta, "l2",
    ["Self-attention captures long-range dependencies in O(1) sequential operations",
     "Multi-head attention jointly attends to different representation subspaces",
     "Achieves 28.4 BLEU on WMT 2014 EN-DE, surpassing all prior models"],
    "claude-opus-4-6")

write_paper_file(Path("literature/papers/vaswani2017attention.md"), meta, body)
# Then run: lit rebuild
```

## Command Reference

| Command | What it does |
|---------|-------------|
| `lit init` | Scaffold a new `literature/` directory |
| `lit install-skill` | Install agent SKILL.md to `~/.agents/skills/` |
| `lit rebuild` | Sync markdown files → SQLite (run after any change) |
| `lit search "query"` | BM25 full-text search |
| `lit recommend N` | Top-N reading recommendations |
| `lit ask "question" --depth 2` | Cross-paper synthesis via funnel retrieval |
| `lit paper <citekey>` | Show paper details |
| `lit add "url"` | Add paper from arXiv/DOI |
| `lit discover --source s2` | Find new papers via Semantic Scholar |
| `lit discover --source arxiv` | Find new papers via arXiv RSS |
| `lit inbox` | Review discovered paper candidates |
| `lit ingest --list` | Papers needing summarization |
| `lit ingest --status` | Summarization progress |
| `lit generate --title "..."` | Generate LaTeX review |
| `lit migrate --from-v1` | Migrate from v1 YAML system |
| `lit stats` | Collection overview |
| `lit status` | Reading queue status |

All commands support `--json` for machine-readable output.

## How Agents Use This System

The system is designed for coding agents (opencode, Claude Code, etc.). After `lit install-skill`, the agent loads the `literature-review` skill and knows the full API.

### Answering Research Questions

```bash
# Agent runs funnel retrieval
lit ask "What are the tradeoffs between different attention mechanisms?" --depth 2
```

**Depth controls token budget:**
- `--depth 1`: ~500 tokens (fast scan of titles + one-liners)
- `--depth 2`: ~2.5K tokens (adds abstracts for top-10) — **recommended default**
- `--depth 3`: ~3.5K tokens (adds key claims for top-3)
- `--depth 4`: ~5K tokens (adds full notes for top-1)

## Generating a LaTeX Review

1. Create theme files in `literature/themes/` — each is a section of the review.

2. Generate the review:
```bash
lit generate --title "My Survey" --authors "Your Name"
cd literature/output && pdflatex review.tex && bibtex review && pdflatex review.tex && pdflatex review.tex
```

## Architecture

- **Source of truth**: One markdown file per paper in `literature/papers/`
- **Index**: SQLite + FTS5 at `literature/index/papers.db` — derived, rebuildable
- **Search**: BM25 via SQLite FTS5 (no vector database, no embeddings required)
- **Ranking**: PageRank on citation graph via scipy sparse matrices
- **Recommendations**: 4-signal scoring (project relevance + co-citation + recency + PageRank)
- **Synthesis**: Multi-stage funnel retrieval (~5K tokens to query 10K papers)
- **Summarization**: Agent-driven with model+timestamp provenance tracking
- **Discovery**: Semantic Scholar Recommendations API + arXiv RSS feeds
- **LaTeX**: Jinja2 templates with NeurIPS style

No external services required at runtime. No GPU. No vector database. Scales to 10K+ papers.

## Running Tests

```bash
uv run pytest literature/tests/ -q
```

## License

MIT — see [LICENSE](LICENSE).
