# Setting Up a Literature Review in a New Project

Takes 2 minutes. Then agents handle the rest.

## Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) (recommended) or pip

## 1. Install

```bash
pip install agent-litreview
# or
uv add agent-litreview
```

## 2. Scaffold

```bash
cd your-project
lit init
```

This creates a `literature/` directory with:
- `PURPOSE.md` — your research goals (edit this first)
- `AGENTS.md` — schema reference for AI agents
- `papers/` — one markdown file per paper
- `templates/` — LaTeX templates for review generation
- Empty directories for themes, output, index

## 3. Define Your Research Purpose

Edit `literature/PURPOSE.md`:

```markdown
# Research Purpose

## Research Questions

1. How can we generate realistic limit order book simulations?
2. What role do foundation models play in market microstructure?

## Key Topics

- limit order book simulation
- market microstructure
- generative models for financial time series

## Methodology Focus

- transformer architectures
- diffusion models

## Exclusions

- high-frequency trading strategy alpha
- sentiment analysis
```

This drives the recommendation engine. Without it, recommendations use PageRank + recency only.

## 4. Add Papers

```bash
# From arXiv
lit add "https://arxiv.org/abs/1706.03762"

# From DOI
lit add "10.1145/3442188.3445922"
```

Each paper gets a markdown file in `literature/papers/` with metadata from Semantic Scholar.

## 5. Build the Index

```bash
lit rebuild
```

Creates `literature/index/papers.db` — SQLite with BM25 search, citation graph, PageRank. Takes <1s. Run after every change.

## 6. Start Working

```bash
lit recommend 5                    # what to read next
lit search "transformer attention" # BM25 search
lit ask "What approaches exist for LOB simulation?" --depth 2  # cross-paper synthesis
lit discover --source s2           # find new papers
lit inbox                          # review candidates
```

## Agent Integration

```bash
lit install-skill
```

Copies `SKILL.md` to `~/.agents/skills/literature-review/`. Agents (opencode, Claude Code) auto-detect it and know the full API.

## Daily Workflow

```
Add       →  lit add "url"              →  paper created (unread)
Rebuild   →  lit rebuild                →  SQLite synced
Recommend →  lit recommend 5            →  what to read next
Search    →  lit search "topic"         →  BM25 full-text search
Read      →  edit the .md file          →  add notes, set reading_status
Summarize →  Python API: set_summary()  →  store L4/L2 with provenance
Rebuild   →  lit rebuild                →  sync summaries to index
Ask       →  lit ask "question"         →  funnel retrieval
Discover  →  lit discover --source s2   →  find new papers
Generate  →  lit generate --title "..." →  NeurIPS LaTeX
```

## How Agents Read Papers

1. `lit recommend 5` — pick most important unread paper
2. Read the abstract from frontmatter
3. Optional: extract PDF text via `uv run python -m literature.scripts.summarize <citekey>`
4. Generate summaries with provenance:

```python
from literature.scripts.parse import read_frontmatter, write_paper_file, set_summary
from pathlib import Path

meta, body = read_frontmatter(Path("literature/papers/vaswani2017attention.md"))

# L4: one-sentence synthesis
set_summary(meta, "l4",
    "Transformer replaces recurrence with self-attention for sequence transduction, achieving BLEU SOTA with greater parallelism.",
    "claude-opus-4-6")

# L2: key claims
set_summary(meta, "l2",
    ["Self-attention captures long-range dependencies in O(1) operations",
     "Multi-head attention jointly attends to different representation subspaces",
     "Achieves 28.4 BLEU on WMT 2014 EN-DE"],
    "claude-opus-4-6")

write_paper_file(Path("literature/papers/vaswani2017attention.md"), meta, body)
```

5. `lit rebuild` to sync summaries into the search index

## Cross-Paper Synthesis

```bash
lit ask "What are the tradeoffs between diffusion and autoregressive models?" --depth 2
```

Depth controls token budget:
- `--depth 1`: ~500 tokens (titles + one-liners)
- `--depth 2`: ~2.5K tokens (adds abstracts for top-10) — default
- `--depth 3`: ~3.5K tokens (adds key claims for top-3)
- `--depth 4`: ~5K tokens (adds full notes for top-1)

## Command Reference

| Command | What it does |
|---------|-------------|
| `lit init` | Scaffold `literature/` in any project |
| `lit install-skill` | Install agent SKILL.md |
| `lit rebuild` | Sync markdown → SQLite |
| `lit search "query"` | BM25 full-text search |
| `lit recommend N` | Top-N reading recommendations |
| `lit ask "question" --depth 2` | Cross-paper synthesis |
| `lit paper <citekey>` | Show paper details |
| `lit add "url"` | Add paper from arXiv/DOI |
| `lit discover --source s2` | Find papers via Semantic Scholar |
| `lit discover --source arxiv` | Find papers via arXiv RSS |
| `lit inbox` | Review discovered candidates |
| `lit ingest --list` | Papers needing summarization |
| `lit ingest --status` | Summarization progress |
| `lit generate --title "..."` | Generate LaTeX review |
| `lit stats` | Collection overview |

All commands support `--json` for machine-readable output.

## Architecture

- **Source of truth**: Markdown files in `literature/papers/`
- **Index**: SQLite + FTS5 (derived, rebuildable)
- **Search**: BM25 via FTS5 (no vector DB)
- **Ranking**: PageRank on citation graph
- **Recommendations**: 4-signal scoring
- **Synthesis**: Multi-stage funnel retrieval (~5K tokens for 10K papers)
- **Summarization**: Agent-driven with model+timestamp provenance

No external services at runtime. No GPU. Scales to 10K+ papers.
