# Setting Up a Literature Review in a New Project

Drop-in guide. Takes 5 minutes to set up, then agents handle the rest.

## Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) package manager

## 1. Copy the System Into Your Project

```bash
# From the mcduck repo (or wherever you have the literature system)
cp -r literature/ /path/to/your-project/literature/

# Clear the example papers — start fresh
rm -rf literature/papers/*.md literature/resources/*.md
rm -f literature/index/papers.db literature/index/graph.yaml literature/index/status.yaml
rm -f literature/index/references.bib literature/index/embeddings.yaml
rm -f literature/landscape.yaml literature/landscape.md
rm -rf literature/output/*
rm -f literature/themes/*.md
```

## 2. Install Dependencies

```bash
cd /path/to/your-project

# Core (needed for all features)
uv add ruamel.yaml requests jinja2 pymupdf

# Dev (for running tests)
uv add --dev pytest responses
```

No servers, no databases, no config files. Everything runs locally with stdlib `sqlite3`.

## 3. Define Your Research Purpose

Edit `literature/PURPOSE.md` — this tells the system what you care about:

```markdown
# Research Purpose

## Research Questions

1. How can we generate realistic limit order book simulations?
2. What role do foundation models play in financial market microstructure?

## Key Topics

- limit order book simulation
- market microstructure
- generative models for financial time series
- agent-based market simulation

## Methodology Focus

- transformer architectures
- diffusion models
- reinforcement learning for trading

## Exclusions

- high-frequency trading strategy alpha
- sentiment analysis from social media
```

This file drives the recommendation engine. Without it, recommendations still work (using PageRank + recency), but with it, papers relevant to your research questions rank higher.

## 4. Add Your First Papers

```bash
# From arXiv URL
uv run python literature/scripts/lit.py add "https://arxiv.org/abs/1706.03762"

# From DOI
uv run python literature/scripts/enrich.py "10.1145/3442188.3445922"

# From bare arXiv ID
uv run python literature/scripts/enrich.py "2301.00001"

# Non-paper resource (blog, talk, code)
uv run python literature/scripts/enrich.py --type blog "https://example.com/post" --title "Great Blog Post"
```

Each paper gets a markdown file in `literature/papers/` with metadata fetched from Semantic Scholar (title, authors, year, abstract, TLDR, citation count).

## 5. Build the Index

```bash
uv run python literature/scripts/lit.py rebuild
```

This creates `literature/index/papers.db` — a SQLite database with BM25 full-text search, citation graph, and PageRank scores. Takes <1 second for typical collections. Rebuild after every change to paper files.

## 6. Start Working

```bash
# What should I read next?
uv run python literature/scripts/lit.py recommend 5

# Search for papers on a topic
uv run python literature/scripts/lit.py search "transformer attention mechanism"

# Ask a synthesis question across all papers
uv run python literature/scripts/lit.py ask "What approaches exist for LOB simulation?" --depth 2

# Find new papers to add
uv run python literature/scripts/lit.py discover --source s2
uv run python literature/scripts/lit.py inbox
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

## How Agents Use This System

The system is designed for coding agents (opencode, Claude Code, etc.). The agent loads the `literature-review` skill and knows the full API.

### Reading a Paper (Agent Workflow)

1. Agent runs `lit recommend 5` to pick the most important unread paper
2. Agent reads the paper's abstract from frontmatter
3. Agent optionally extracts PDF text: `uv run python literature/scripts/summarize.py <citekey>`
4. Agent generates summaries and stores them with provenance:

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
```

5. Agent runs `lit rebuild` to sync summaries into the search index
6. Agent updates `reading_status.global` to `"read"` in the markdown file

### Answering Research Questions

```bash
# Agent runs funnel retrieval
uv run python literature/scripts/lit.py ask "What are the tradeoffs between diffusion and autoregressive models for LOB generation?" --depth 2
```

The system returns the most relevant papers with their summaries. The agent synthesizes the answer from the retrieved context and cites papers by citekey.

**Depth controls token budget:**
- `--depth 1`: ~500 tokens (fast scan of titles + one-liners)
- `--depth 2`: ~2.5K tokens (adds abstracts for top-10) — **recommended default**
- `--depth 3`: ~3.5K tokens (adds key claims for top-3)
- `--depth 4`: ~5K tokens (adds full notes for top-1)

## Paper File Format

Each paper is a markdown file with YAML frontmatter:

```yaml
---
doc_id: "vaswani2017attention"
title: "Attention Is All You Need"
authors: ["Vaswani, A.", "Shazeer, N."]
year: 2017
arxiv_id: "1706.03762"
abstract: "The dominant sequence transduction models..."
tldr: "A new architecture based entirely on attention mechanisms..."
citation_count: 169004
reading_status:
  global: unread      # unread | skimmed | read | synthesized
cites:
  - id: bahdanau2014attention
    type: extends     # cites | extends | contradicts | uses_method | uses_dataset | surveys
tags: [transformers, attention]
themes: [foundation-models]
summaries:            # written by agents via set_summary()
  l4:
    text: "Transformer replaces recurrence with self-attention..."
    model: "claude-opus-4-6"
    generated_at: "2026-03-14T10:00:00Z"
---

## Notes

Your reading notes go here.
```

## Linking Papers

After reading a paper, add relationships to its `cites` field:

```yaml
cites:
  - id: vaswani2017attention
    type: extends           # this paper extends the transformer
  - id: devlin2019bert
    type: uses_method       # this paper uses BERT's pretraining approach
```

Run `lit rebuild` to update the citation graph and PageRank scores.

## Generating a LaTeX Review

1. Create theme files in `literature/themes/` — each is a section of the review:

```markdown
---
title: "Foundation Models for Market Microstructure"
order: 1
---

TradeFM \cite{kawawa-beaudan2026tradefm} introduces a generative transformer
for trade-flow data, building on universal price formation
\cite{sirignano2018universal}.
```

2. Generate the review:
```bash
uv run python literature/scripts/lit.py generate --title "My Survey" --authors "Your Name"
cd literature/output && pdflatex review.tex && bibtex review && pdflatex review.tex && pdflatex review.tex
```

## Command Reference

| Command | What it does |
|---------|-------------|
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

All commands support `--json` for machine-readable output (add before the subcommand: `lit --json search "query"`).

`lit` is shorthand for `uv run python literature/scripts/lit.py`.

## Architecture (for the curious)

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
