---
name: literature-review
description: Agent-native literature review system v3. Use when working with a literature/ directory to manage papers, track reading, search, synthesize, and discover new work. The system uses a SQLite index (papers.db) rebuilt from markdown files. Primary interface is `lit` (literature/scripts/lit.py).
---

# Literature Review System v3

This skill teaches you how to manage academic papers, track reading, and synthesize research. The system lives in `literature/` at the repository root.

**Philosophy**: The system is data plumbing. YOU are the intelligence. You read papers, generate summaries, and synthesize findings — the system stores, indexes, and retrieves for you.

**Full schema reference**: Read `literature/AGENTS.md` for complete frontmatter field documentation.

## Quick Start (2 commands to get going)

```bash
# Step 1: Build the SQLite index from markdown files
uv run python literature/scripts/lit.py rebuild

# Step 2: See what to read next
uv run python literature/scripts/lit.py recommend 5
```

## Command Reference

All commands use `uv run python literature/scripts/lit.py <COMMAND>`. The shorthand `lit` refers to this invocation throughout.

### Core Commands

```bash
# Rebuild SQLite index from markdown files (run after ANY changes)
uv run python literature/scripts/lit.py rebuild

# Rebuild and also fetch SPECTER2 embeddings (requires S2_API_KEY)
uv run python literature/scripts/lit.py rebuild --fetch-embeddings

# BM25 full-text search across papers
uv run python literature/scripts/lit.py search "limit order book simulation"
uv run python literature/scripts/lit.py search "diffusion models" --top-k 10

# Find papers similar to a given paper (embedding-based)
uv run python literature/scripts/lit.py search --similar vaswani2017attention

# Show paper details and summaries
uv run python literature/scripts/lit.py paper kawawa-beaudan2026tradefm

# Collection statistics
uv run python literature/scripts/lit.py stats

# Reading queue status
uv run python literature/scripts/lit.py status
```

### Recommendations

```bash
# Get N reading recommendations (positional arg is a number, NOT "next N")
uv run python literature/scripts/lit.py recommend 5
uv run python literature/scripts/lit.py recommend 10   # default

# Scoring: cold start uses PageRank + recency
# With literature/PURPOSE.md: adds relevance scoring to your research goals
```

### Cross-Paper Synthesis

```bash
# Ask a question across the collection (depth 2 is default and recommended)
uv run python literature/scripts/lit.py ask "What generative models exist for LOB data?" --depth 2

# Depth controls how much context is retrieved:
#   depth 1: ~500 tokens  — BM25 top-20 with L4 summaries only (fastest)
#   depth 2: ~2.5K tokens — adds abstracts for top-10 (DEFAULT)
#   depth 3: ~3.5K tokens — adds key claims for top-3
#   depth 4: ~5K tokens   — adds full notes for top-1 (most detail)
```

### Discovery

```bash
# Discover new papers via Semantic Scholar
uv run python literature/scripts/lit.py discover --source s2

# Discover via arXiv RSS feed
uv run python literature/scripts/lit.py discover --source arxiv --categories cs.LG,q-fin.TR

# Discover from both sources
uv run python literature/scripts/lit.py discover --source all --limit 20

# View discovered papers waiting for review
uv run python literature/scripts/lit.py inbox

# Add a discovered paper to the collection
uv run python literature/scripts/lit.py inbox add <paper_id>

# Dismiss a discovered paper
uv run python literature/scripts/lit.py inbox dismiss <paper_id>
```

### Adding Papers

```bash
# Add a paper from arXiv URL (wraps enrich.py)
uv run python literature/scripts/lit.py add "https://arxiv.org/abs/1706.03762"

# Add with custom type or citekey
uv run python literature/scripts/lit.py add "https://arxiv.org/abs/1706.03762" --citekey my_key
uv run python literature/scripts/lit.py add "https://github.com/user/repo" --type code

# Or use enrich.py directly for more options
uv run python literature/scripts/enrich.py "https://arxiv.org/abs/1706.03762"
uv run python literature/scripts/enrich.py "10.1145/3442188.3445922"   # from DOI
uv run python literature/scripts/enrich.py --update vaswani2017attention  # re-fetch metadata
```

### Summarization Queue

```bash
# List papers needing L4 or L2 summaries (sorted by PageRank)
uv run python literature/scripts/lit.py ingest --list

# Show ingestion progress (how many papers have L4/L2 summaries)
uv run python literature/scripts/lit.py ingest --status
```

### LaTeX Review Generation

```bash
# Generate NeurIPS-format LaTeX review from theme files
uv run python literature/scripts/lit.py generate --title "My Survey" --authors "Author Name"

# Compile to PDF
cd literature/output && pdflatex review.tex && bibtex review && pdflatex review.tex && pdflatex review.tex
```

### Migration

```bash
# Migrate from v1 YAML-based system
uv run python literature/scripts/lit.py migrate --from-v1
```

## Reading Workflow

When you read a paper:

1. `lit paper <citekey>` — load paper details and existing notes
2. Read the abstract and any existing notes
3. Optional: extract PDF text via `uv run python literature/scripts/summarize.py <citekey>`
4. Generate summaries (see Summarization Workflow below)
5. Edit the paper `.md` file — add notes, set `reading_status.global` to `"read"`
6. `lit rebuild` — sync changes to SQLite

## Summarization Workflow

After reading a paper, store your summaries with provenance using the Python API:

```python
from literature.scripts.parse import read_frontmatter, write_paper_file, set_summary
from pathlib import Path

# Load paper
meta, body = read_frontmatter(Path("literature/papers/vaswani2017attention.md"))

# Write L4 (1-sentence synthesis) — use your best available model
set_summary(meta, "l4",
    "Transformer introduces self-attention as a complete replacement for recurrence in sequence transduction, achieving BLEU state-of-the-art while being more parallelizable.",
    "claude-opus-4-6")  # <-- put YOUR model name here

# Write L2 (key claims list)
set_summary(meta, "l2",
    ["Self-attention captures long-range dependencies in O(1) operations vs O(n) for RNNs",
     "Multi-head attention attends to different representation subspaces jointly",
     "Positional encoding preserves sequence order information without recurrence"],
    "claude-opus-4-6")

# Save back to file
write_paper_file(Path("literature/papers/vaswani2017attention.md"), meta, body)

# Sync to SQLite
# run: uv run python literature/scripts/lit.py rebuild
```

The `summaries` field in frontmatter looks like this after writing:

```yaml
summaries:
  l4:
    text: "Transformer introduces self-attention..."
    model: "claude-opus-4-6"
    generated_at: "2026-03-13T10:00:00Z"
  l2:
    claims:
      - "Self-attention captures long-range dependencies in O(1) operations vs O(n) for RNNs"
      - "Multi-head attention attends to different representation subspaces jointly"
      - "Positional encoding preserves sequence order information without recurrence"
    model: "claude-opus-4-6"
    generated_at: "2026-03-13T10:00:00Z"
```

### Prompt Templates

Use these prompts with your best model for consistent summaries:

**L4 Summary Prompt** (one-liner):
```
Generate a single sentence (20-30 words) summarizing this paper's core contribution.
Be specific about WHAT was built/discovered and WHY it matters.
Do NOT start with "The paper" or "This paper".

Paper: {title}
Abstract: {abstract}

Output format: One sentence only.
```

**L2 Key Claims Prompt** (structured claims):
```
Extract 3-5 key claims from this paper as a bullet list.
Each claim should be a complete, standalone statement about the paper's findings or methods.
Be specific and avoid vague phrases like "improves performance".

Paper: {title}
Abstract: {abstract}

Output format: A Python list of strings, one claim per item.
```

## Search and Synthesis

`lit ask` uses a 4-stage funnel retrieval to answer research questions:

- **depth 1**: ~500 tokens — BM25 top-20 with L4 summaries (fastest scan)
- **depth 2**: ~2.5K tokens — adds abstracts for top-10 (DEFAULT, recommended)
- **depth 3**: ~3.5K tokens — adds key claims for top-3
- **depth 4**: ~5K tokens — adds full notes for top-1 (deepest dive)

```bash
uv run python literature/scripts/lit.py ask "What diffusion models exist for LOB simulation?" --depth 2
```

After seeing the retrieved context, YOU synthesize the answer and cite papers by citekey.

## Discovery

Two sources for finding new papers:

- **Semantic Scholar** (`--source s2`): recommendations based on your collection's citation graph
- **arXiv RSS** (`--source arxiv`): recent papers from specified categories

Discovered papers land in the inbox. Review with `lit inbox`, then `lit inbox add <id>` to pull into the collection or `lit inbox dismiss <id>` to skip.

## Project Purpose (improves recommendations)

Edit `literature/PURPOSE.md` to describe your research goals. The `lit recommend` command reads this file to score paper relevance when deciding what to read next. Without it, recommendations use PageRank + recency only.

## Conventions

- **Citekey format**: `{lastname}{year}{titleword}` (e.g. `vaswani2017attention`)
- **One `.md` file per paper** in `literature/papers/`
- **Run `lit rebuild` after any changes** — SQLite is derived from markdown files
- **Provenance required**: always include your model name when calling `set_summary()`
- **Markdown files are source of truth**; `papers.db` is derived and rebuildable
- **Incremental rebuild by default** — delete `papers.db` for a full rebuild from scratch
- **All scripts via `uv run python`** — never `python` directly

## Example Agent Session

```python
# 1. Rebuild index
run_bash("uv run python literature/scripts/lit.py rebuild")

# 2. See what to read
run_bash("uv run python literature/scripts/lit.py recommend 5")

# 3. Search for related papers
run_bash('uv run python literature/scripts/lit.py search "diffusion LOB"')

# 4. Ask a synthesis question
run_bash('uv run python literature/scripts/lit.py ask "What are the best generative approaches for LOB?" --depth 2')

# 5. After reading a paper, store your summary (use Python API)
from literature.scripts.parse import read_frontmatter, write_paper_file, set_summary
from pathlib import Path
meta, body = read_frontmatter(Path("literature/papers/berti2025trades.md"))
set_summary(meta, "l4", "TRADES generates realistic LOB dynamics using score-based diffusion conditioned on market context.", "claude-opus-4-6")
set_summary(meta, "l2", ["Score-based diffusion models LOB state transitions", "Conditioning on market context improves realism"], "claude-opus-4-6")
write_paper_file(Path("literature/papers/berti2025trades.md"), meta, body)
run_bash("uv run python literature/scripts/lit.py rebuild")  # sync to SQLite

# 6. Discover new papers
run_bash("uv run python literature/scripts/lit.py discover --source s2")
run_bash("uv run python literature/scripts/lit.py inbox")  # review candidates
```

## Legacy Commands (v1 — prefer `lit` command)

These v1 scripts still work but the `lit` command is preferred for all new workflows:

```bash
# Legacy: rebuild indexes (prefer: lit rebuild)
uv run python literature/scripts/rebuild_index.py

# Legacy: search (prefer: lit search "query")
uv run python literature/scripts/query.py search transformers

# Legacy: reading status (prefer: lit status)
uv run python literature/scripts/query.py unread

# Legacy: paper details (prefer: lit paper <citekey>)
uv run python literature/scripts/query.py paper vaswani2017attention

# Legacy: stats (prefer: lit stats)
uv run python literature/scripts/query.py stats

# Legacy: discover (prefer: lit discover)
uv run python literature/scripts/scout.py search "topic" --limit 20
uv run python literature/scripts/scout.py recommend --limit 20
uv run python literature/scripts/scout.py gaps
```
