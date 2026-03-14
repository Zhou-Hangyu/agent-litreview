# Literature Review System — User Manual

Agent-native literature review manager. Install via `pip install agent-litreview`, then `lit init` in any project.

**v3**: Primary interface is the `lit` CLI. SQLite-backed with BM25 search, PageRank recommendations, and cross-paper synthesis.

## Setup

```bash
# Install the package
pip install agent-litreview   # or: uv add agent-litreview

# Scaffold literature/ in your project
cd your-project
lit init

# Install agent skill (optional — for opencode/Claude Code)
lit install-skill
```

No server, no config. Scripts auto-detect the `literature/` root.

## Quick Start

```bash
# 1. Add a paper (fetches metadata from Semantic Scholar)
lit add "https://arxiv.org/abs/1706.03762"

# 2. Build the SQLite index
lit rebuild

# 3. See what to read next
lit recommend 5

# 4. Search for papers
lit search "attention mechanism"

# 5. Ask a synthesis question
lit ask "What are the key contributions of transformer models?" --depth 2
```

## Daily Workflow (v3)

```
Add paper   →  lit add "url"                    →  paper file created (unread)
Rebuild     →  lit rebuild                       →  SQLite index synced
Recommend   →  lit recommend 5                   →  what to read next
Search      →  lit search "topic"                →  BM25 full-text search
Ask         →  lit ask "question" --depth 2      →  cross-paper synthesis
Read paper  →  edit .md file                     →  add notes, status, summaries
Summarize   →  Python API: set_summary()         →  store L4/L2 with provenance
Rebuild     →  lit rebuild                       →  sync summaries to SQLite
Discover    →  lit discover --source s2          →  find new papers
Inbox       →  lit inbox                         →  review discovered candidates
Generate    →  lit generate --title "..."        →  NeurIPS LaTeX
Compile     →  pdflatex + bibtex                 →  PDF
```

## Data Model

Each paper is a single `.md` file in `papers/` with YAML frontmatter + markdown notes:

```yaml
---
title: "Attention Is All You Need"
authors: ["Vaswani, A.", "Shazeer, N."]
year: 2017
arxiv_id: "1706.03762"
reading_status:
  global: read              # unread | skimmed | read | synthesized
cites:
  - id: bahdanau2014attention
    type: extends           # cites | extends | contradicts | uses_method | uses_dataset | surveys
tags: [transformers]
themes: [foundation-models]
influential_citation_count: 0   # from S2 API, default 0
provenance:                      # how the paper was discovered (optional)
  method: "enrich"               # enrich | scout_recommend | scout_search | scout_gaps
  discovered_at: "2026-03-13"
summaries:                       # written by agent via set_summary() — do not edit manually
  l4:
    text: "Transformer replaces recurrence with self-attention, achieving BLEU state-of-the-art with better parallelism."
    model: "claude-opus-4-6"
    generated_at: "2026-03-13T10:00:00Z"
  l2:
    claims:
      - "Self-attention captures long-range dependencies in O(1) operations vs O(n) for RNNs"
      - "Multi-head attention attends to different representation subspaces jointly"
    model: "claude-opus-4-6"
    generated_at: "2026-03-13T10:00:00Z"
---

## Key Contributions
- Self-attention replaces recurrence entirely
```

One file per paper avoids git merge conflicts when collaborating.

## Scripts

### `lit.py` — Primary CLI (v3)

The `lit` command is the primary interface for all v3 operations.

```bash
# Rebuild SQLite index (run after ANY changes to paper files)
uv run python literature/scripts/lit.py rebuild

# BM25 full-text search
uv run python literature/scripts/lit.py search "limit order book simulation"
uv run python literature/scripts/lit.py search "diffusion models" --top-k 10
uv run python literature/scripts/lit.py search --similar vaswani2017attention

# Show paper details and summaries
uv run python literature/scripts/lit.py paper vaswani2017attention

# Reading recommendations (N is a positional number)
uv run python literature/scripts/lit.py recommend 5

# Cross-paper synthesis via funnel retrieval
uv run python literature/scripts/lit.py ask "What generative models exist for LOB data?" --depth 2
# depth 1: ~500 tokens (L4 scan only)
# depth 2: ~2.5K tokens (adds abstracts, DEFAULT)
# depth 3: ~3.5K tokens (adds key claims)
# depth 4: ~5K tokens (adds full notes)

# Discover new papers
uv run python literature/scripts/lit.py discover --source s2
uv run python literature/scripts/lit.py discover --source arxiv --categories cs.LG,q-fin.TR

# View and act on discovered papers
uv run python literature/scripts/lit.py inbox
uv run python literature/scripts/lit.py inbox add <paper_id>
uv run python literature/scripts/lit.py inbox dismiss <paper_id>

# Add a paper from URL
uv run python literature/scripts/lit.py add "https://arxiv.org/abs/1706.03762"

# Summarization queue
uv run python literature/scripts/lit.py ingest --list    # papers needing summaries
uv run python literature/scripts/lit.py ingest --status  # ingestion progress

# Reading queue status
uv run python literature/scripts/lit.py status

# Collection statistics
uv run python literature/scripts/lit.py stats

# Generate LaTeX review
uv run python literature/scripts/lit.py generate --title "My Survey" --authors "Author Name"

# Migrate from v1
uv run python literature/scripts/lit.py migrate --from-v1
```

### Summarization API (Python)

After reading a paper, store summaries with provenance:

```python
from literature.scripts.parse import read_frontmatter, write_paper_file, set_summary
from pathlib import Path

meta, body = read_frontmatter(Path("literature/papers/vaswani2017attention.md"))

# L4: one-liner (20-30 words)
set_summary(meta, "l4",
    "Transformer replaces recurrence with self-attention, achieving BLEU state-of-the-art with better parallelism.",
    "claude-opus-4-6")  # always include your model name

# L2: key claims list
set_summary(meta, "l2",
    ["Self-attention captures long-range dependencies in O(1) operations vs O(n) for RNNs",
     "Multi-head attention attends to different representation subspaces jointly"],
    "claude-opus-4-6")

write_paper_file(Path("literature/papers/vaswani2017attention.md"), meta, body)
# Then run: uv run python literature/scripts/lit.py rebuild
```

### `enrich.py` — Add a paper (legacy, prefer `lit add`)

```bash
# From arXiv URL
uv run python literature/scripts/enrich.py "https://arxiv.org/abs/2301.00001"

# From DOI
uv run python literature/scripts/enrich.py "10.1145/3292500.3330701"

# Non-paper resource (blog, talk, code, report)
uv run python literature/scripts/enrich.py --type blog "https://example.com/post" --title "My Blog"

# Re-fetch metadata for existing paper
uv run python literature/scripts/enrich.py --update vaswani2017attention

# Custom citekey
uv run python literature/scripts/enrich.py "https://arxiv.org/abs/1706.03762" --citekey my_custom_key
```

Calls the Semantic Scholar API to fetch title, authors, abstract, year, venue, citation count, and TLDR. Does **not** read PDFs or use LLMs.

### `rebuild_index.py` — Regenerate YAML indexes (legacy, prefer `lit rebuild`)

```bash
uv run python literature/scripts/rebuild_index.py
```

Reads all `papers/*.md` files and produces:

| File | Contents |
|---|---|
| `index/graph.yaml` | Citation graph — all papers as nodes, all relationships as edges |
| `index/status.yaml` | Reading progress — papers grouped by status |
| `index/references.bib` | BibTeX export for LaTeX |

Run this after **any** change to paper files. Never edit index files manually.

### `query.py` — Search and inspect papers (legacy, prefer `lit search` / `lit paper`)

```bash
# Search by keyword (matches title, abstract, tags, tldr)
uv run python literature/scripts/query.py search transformers

# List all unread papers
uv run python literature/scripts/query.py unread

# List unread papers filtered by tag
uv run python literature/scripts/query.py unread --tags ml,nlp

# Show collection statistics (counts, top tags)
uv run python literature/scripts/query.py stats

# Show a single paper's full metadata + first 500 chars of notes
uv run python literature/scripts/query.py paper vaswani2017attention

# Show all papers related to a given paper (both directions)
uv run python literature/scripts/query.py related vaswani2017attention

# Find papers most similar to a given paper by SPECTER2 embedding
uv run python literature/scripts/query.py similar vaswani2017attention --top 10
```

Reads from pre-built index files — fast, compact output designed for agent context windows. The `similar` subcommand requires `index/embeddings.yaml`.

### `update.py` — Batch update papers

```bash
# Set reading status on one or more papers
uv run python literature/scripts/update.py status read paper1 paper2

# Add tags (comma-separated) to papers
uv run python literature/scripts/update.py tags add "diffusion,lob" paper1 paper2

# Remove tags from papers
uv run python literature/scripts/update.py tags remove "transformers" paper1

# Add themes to papers
uv run python literature/scripts/update.py themes add "world-models" paper1 paper2

# Remove themes from papers
uv run python literature/scripts/update.py themes remove "old-theme" paper1
```

Modifies paper files directly. Run `rebuild_index.py` after batch updates.

### `summarize.py` — Extract text from PDFs

```bash
# Print extracted text to stdout
uv run python literature/scripts/summarize.py kawawa-beaudan2026tradefm

# Write extracted text into the paper's .md body (sets status to "skimmed")
uv run python literature/scripts/summarize.py kawawa-beaudan2026tradefm --write
```

Requires a `pdf_path` field in the paper's frontmatter (auto-set by `enrich.py` for arXiv papers with matching PDFs in `papers/`). Uses pymupdf for extraction.

### `scout.py` — Discover papers (legacy, prefer `lit discover`)

```bash
# Search for papers by keyword (S2 bulk search)
uv run python literature/scripts/scout.py search "transformer attention mechanism" --limit 20

# Get recommendations based on current collection
uv run python literature/scripts/scout.py recommend --limit 20

# Find papers cited by ≥2 collection papers but not in collection
uv run python literature/scripts/scout.py gaps
```

Discovers new papers via the Semantic Scholar API. Does **not** add papers automatically — outputs a ranked list for human or agent review. Use `enrich.py` to add any candidates you want to keep.

### `landscape.py` — Research landscape analysis

```bash
uv run python literature/scripts/landscape.py
```

Clusters your collection by SPECTER2 embeddings, detects research fronts, structural holes, and citation gaps. Outputs:

| File | Contents |
|---|---|
| `landscape.yaml` | Clusters, research fronts, structural holes, citation gaps |
| `landscape.md` | Narrative report with reading recommendations |

Requires `index/embeddings.yaml` for clustering (generated by `rebuild_index.py` with an S2 API key). Falls back to basic stats if no embeddings are available.

### `generate_review.py` — Produce LaTeX

```bash
uv run python literature/scripts/generate_review.py \
  --title "Survey of Foundation Models" \
  --authors "Alice, Bob"
```

Reads theme files from `themes/` and generates `output/review.tex` using a NeurIPS template.

## Theme Files

Themes define the narrative sections of your review. Create them in `themes/`:

```
literature/themes/01-foundation-models.md
literature/themes/02-diffusion-methods.md
```

Each theme is markdown with `\cite{}` references:

```yaml
---
title: "Foundation Models"
order: 1
---

TradeFM \cite{kawawa-beaudan2026tradefm} trains on trade events,
building on universal price formation \cite{sirignano2018universal}.
```

The `order` field controls section ordering in the generated review.

## Relationship Types

| Type | Meaning |
|---|---|
| `cites` | Directly cites the referenced paper |
| `extends` | Builds on or improves the referenced work |
| `contradicts` | Disagrees with or refutes the referenced work |
| `uses_method` | Applies a method from the referenced paper |
| `uses_dataset` | Uses a dataset from the referenced paper |
| `surveys` | Reviews or surveys the referenced work |

## Reading Statuses

| Status | Meaning |
|---|---|
| `unread` | Not yet read |
| `skimmed` | Quick skim of abstract/intro |
| `read` | Full read with notes |
| `synthesized` | Integrated into your understanding |

## Legacy Workflow (v1 — prefer v3 commands above)

```
Explore     →  scout.py search/recommend/gaps  →  discover new candidates
Find paper  →  enrich.py "url"                 →  paper file created (unread)
Extract     →  summarize.py key --write        →  PDF text into .md body
Read paper  →  edit .md file                   →  add notes, status, cites, tags
Batch edit  →  update.py status/tags/...       →  bulk updates across papers
Query       →  query.py search/stats/...       →  compact index lookups
Group       →  create themes/*.md              →  organize papers into narrative
Build       →  rebuild_index.py                →  regenerate graph + bib
Write       →  generate_review.py              →  NeurIPS LaTeX
Compile     →  pdflatex + bibtex               →  PDF
```

## Exploration Workflow

When you want to grow the collection or map the research space:

```
Discover →  lit discover --source s2    →  S2 recommendations
Inbox    →  lit inbox                   →  review candidates
Add      →  lit inbox add <id>          →  pull into collection
Rebuild  →  lit rebuild                 →  sync to SQLite
Search   →  lit search "topic"          →  BM25 full-text search
Ask      →  lit ask "question"          →  cross-paper synthesis
```

Legacy exploration (still works):
```
Explore  →  scout.py search "topic"     →  ranked candidate list
Expand   →  scout.py recommend          →  recommendations from collection
Gaps     →  scout.py gaps               →  missing influential papers
Add      →  enrich.py "arXiv:..."       →  paper added to collection
Index    →  rebuild_index.py            →  embeddings + graph updated
Analyze  →  landscape.py               →  landscape.yaml + landscape.md
Similar  →  query.py similar <key>      →  papers ranked by embedding similarity
```

## Directory Structure

```
literature/
├── papers/           # One .md per paper (you create/edit these)
├── themes/           # Review sections (you create these)
├── PURPOSE.md        # Your research goals (edit to improve recommendations)
├── papers.db         # SQLite index (auto-generated by lit rebuild; DO NOT EDIT)
├── index/            # Legacy YAML indexes (auto-generated by rebuild_index.py)
│   ├── graph.yaml
│   ├── status.yaml
│   ├── references.bib
│   └── embeddings.yaml      # SPECTER2 embedding vectors (auto-generated)
├── landscape.yaml            # Research landscape report (auto-generated)
├── landscape.md              # Narrative landscape report (auto-generated)
├── output/           # Auto-generated (review.tex, review.pdf)
├── templates/        # LaTeX template + NeurIPS style file
├── scripts/
│   ├── lit.py                # PRIMARY CLI (v3) — rebuild, search, ask, recommend, etc.
│   ├── enrich.py
│   ├── rebuild_index.py      # Legacy: rebuild YAML indexes
│   ├── query.py              # Legacy: search and inspect
│   ├── update.py
│   ├── summarize.py
│   ├── generate_review.py
│   ├── ingest.py             # Summarization queue manager
│   ├── scout.py              # Paper discovery
│   ├── landscape.py          # Landscape analysis
│   ├── s2_client.py          # S2 API client
│   ├── cluster.py            # Clustering utilities
│   ├── db.py                 # SQLite database layer
│   ├── pagerank.py           # PageRank scoring
│   └── parse.py
├── tests/            # pytest test suite
├── AGENTS.md         # Full schema reference for AI agents
└── README.md         # This file
```

## Running Tests

```bash
uv run python -m pytest literature/tests/ -v
```

## Tips

- **Citekeys** are auto-generated as `{firstauthor}{year}{titleword}` (e.g., `vaswani2017attention`)
- **`lit rebuild` is incremental** by default — delete `papers.db` for a full rebuild from scratch
- **`lit recommend N`** takes a positional number, not "next N" — use `lit recommend 5` not `lit recommend next 5`
- **S2 rate limits**: space out `enrich.py` calls by ~10 seconds when adding many papers
- **Collaboration**: each person can add their own reading status under `reading_status.{username}`
- **Portability**: use `--root /path/to/literature/` flag if running scripts from outside the repo
- **Agent-friendly**: load the `literature-review` opencode skill for AI agent interaction
- **PURPOSE.md**: edit this file to describe your research goals and improve `lit recommend` relevance scoring
- **Summaries require provenance**: always pass your model name to `set_summary()` — it's stored in frontmatter
