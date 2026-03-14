# alit

Lightweight literature review system for AI coding agents.

Zero dependencies. SQLite-only. The agent is the intelligence — alit is data plumbing.

## Install

```bash
pip install alit
# or
uv add alit
```

## 30-Second Start

```bash
alit init                                              # create papers.db
alit add "https://arxiv.org/abs/1706.03762"            # add paper (auto-fetches metadata + PDF)
alit search "attention"                                # BM25 search
alit recommend 5                                       # what to read next
alit ask "What are the key transformer innovations?"   # cross-paper synthesis
```

## Using with AI Coding Agents

alit is designed to be used by AI coding agents (Claude Code, opencode, Cursor, etc.). The agent reads papers, generates summaries, builds citation graphs — alit stores and retrieves.

### Setup (one-time)

```bash
pip install alit
alit init
alit install-skill
```

### Give Your Agent This Prompt

Copy and paste the following into your agent session to get started:

---

> I have the `alit` literature review tool installed in this project (data stored in `.alit/`). Here's how it works:
>
> **Adding papers**: `alit add "https://arxiv.org/abs/XXXX.XXXXX"` — auto-fetches metadata + PDF from arXiv. Or `alit import papers.bib` for BibTeX from Zotero/Mendeley. Or `alit find "topic"` to search arXiv by keyword.
>
> **Reading workflow**: `alit recommend 5` shows what to read next (ranked by PageRank + relevance to my research purpose). After reading a paper, store your findings:
> - `alit status <id> read`
> - `alit note <id> "your observations"`
> - `alit summarize <id> --l4 "one sentence summary" --model "your-model-name"`
> - `alit cite <this_paper> <referenced_paper> --type extends`
>
> **Searching**: `alit search "query"` for BM25 search. `alit ask "research question" --depth 2` for cross-paper synthesis.
>
> **Progress**: `alit progress` shows a visual dashboard. `alit stats` for numbers.
>
> **Key concepts**: The database is at `.alit/papers.db`. PDFs are in `.alit/pdfs/`. Everything is SQLite — no external services. My research purpose is set via `alit purpose "..."`. Run `alit read <id>` to see full paper details before reading.
>
> Please help me with my literature review. Start by running `alit progress` to see where we are, then `alit recommend 5` to pick the next paper to read.

---

### How the Agent Workflow Works

1. **Agent runs `alit recommend 5`** — gets a ranked reading queue
2. **Agent runs `alit read <id>`** — sees the paper's abstract, citations, and what to do next
3. **Agent reads the PDF** (from `.alit/pdfs/`) or abstract and generates insights
4. **Agent stores findings**:
   - `alit note <id> "key insight: self-attention replaces recurrence..."`
   - `alit summarize <id> --l4 "Transformer replaces recurrence with self-attention." --model "claude-sonnet-4-20250514"`
   - `alit status <id> read`
5. **Agent builds citation graph**: `alit cite <from> <to> --type extends`
6. **Agent verifies citations**: `alit orphans` — for any missing cited papers, searches online and adds them
7. **Repeat** — `alit recommend 5` for the next batch

The agent does all the intelligence (reading, reasoning, summarizing). alit does the data plumbing (storing, searching, ranking).

## How It Works

```
You (or your agent) add papers → alit stores in SQLite → search/recommend/synthesize
                                                      → PDFs auto-downloaded from arXiv
                                                      → PageRank on citation graph
                                                      → BM25 full-text search via FTS5
```

**No servers. No API keys. No vector databases.** Everything lives in a single `.alit/` directory.

## Adding Papers

```bash
# From arXiv URL (auto-fetches title, abstract, authors, year + PDF + auto-tags)
alit add "https://arxiv.org/abs/1706.03762"

# With explicit metadata
alit add "Attention Is All You Need" \
  --id vaswani2017attention \
  --year 2017 \
  --authors "Vaswani, Shazeer, Parmar" \
  --abstract "The dominant sequence transduction models..." \
  --arxiv "1706.03762" \
  --tags "transformers,attention"

# Attach a local PDF
alit add "Some Paper" --id smith2024 --pdf /path/to/paper.pdf

# Bulk import from a file
alit import papers.txt --no-pdf
```

**papers.txt** format (one URL per line, `#` comments):
```
# Core papers
https://arxiv.org/abs/1706.03762
https://arxiv.org/abs/1810.04805

# LOB papers
https://arxiv.org/abs/2502.07071
```

### From Zotero / Mendeley / Google Scholar

Export your library as `.bib`, then:

```bash
alit import library.bib
```

## Reading Workflow

```bash
# 1. See what to read next (ranked by relevance + PageRank + recency)
alit recommend 5

# 2. Read a paper, then store your findings
alit status vaswani2017attention read
alit note vaswani2017attention "Self-attention replaces recurrence. O(1) sequential ops."
alit summarize vaswani2017attention \
  --l4 "Transformer replaces recurrence with self-attention, achieving BLEU SOTA." \
  --model "claude-opus-4-6"

# 3. Link papers
alit cite vaswani2017attention bahdanau2014attention --type extends

# 4. Verify cited papers exist in collection
alit orphans
```

## Searching & Synthesis

```bash
# BM25 full-text search
alit search "limit order book simulation"

# Cross-paper synthesis — agent reads the output and reasons
alit ask "What generative models exist for LOB data?" --depth 2
```

Depth controls token budget:
| Depth | What you get | ~Tokens |
|-------|-------------|---------|
| 1 | Titles + one-liners | 500 |
| 2 | + abstracts for top-10 (default) | 2,500 |
| 3 | + key claims for top-3 | 3,500 |
| 4 | + full notes for top-1 | 5,000 |

## Commands

| Command | What it does |
|---------|-------------|
| `alit init` | Create papers.db |
| `alit add <title-or-url>` | Add paper (auto-enriches arXiv URLs, auto-tags from abstract) |
| `alit find <query>` | Search arXiv/S2 for papers by topic |
| `alit import <file>` | Bulk-add from URL file or BibTeX |
| `alit read <id>` | Guided reading view |
| `alit progress` | Visual progress dashboard |
| `alit enrich` | Batch-fetch metadata for papers missing abstracts |
| `alit show <id>` | Full paper details + citations |
| `alit list` | List all papers (📄=PDF, ✓=summarized) |
| `alit search <query>` | BM25 full-text search |
| `alit recommend [N]` | Reading queue ranked by score |
| `alit ask <question>` | Cross-paper synthesis |
| `alit note <id> <text>` | Append reading notes |
| `alit summarize <id>` | Store L4/L2 summary with provenance |
| `alit cite <from> <to>` | Add citation edge |
| `alit status <id> <s>` | Set reading status |
| `alit tag <id> <tags>` | Set comma-separated tags |
| `alit purpose [text]` | Set or show research purpose |
| `alit stats` | Collection overview with coverage |
| `alit orphans` | Citations pointing to missing papers |
| `alit attach <id> <pdf>` | Attach local PDF to existing paper |
| `alit fetch-pdf <id>` | Download PDF from arXiv |
| `alit delete <id>` | Remove paper + its citations |
| `alit export [--format X]` | Export as JSON or markdown |
| `alit install-skill` | Install agent SKILL.md |

All commands support `--json` for machine-readable output.

## Architecture

Everything in one hidden directory:

```
your-project/
└── .alit/
    ├── papers.db        ← SQLite database (sole source of truth)
    └── pdfs/            ← downloaded PDFs
        ├── 1706.03762.pdf
        └── 2502.07071.pdf
```

Inside `papers.db`:

```
├── papers       — metadata, notes, summaries, pdf_path
├── papers_fts   — FTS5 index (auto-synced via triggers)
├── citations    — typed edges between papers
└── meta         — key-value store (purpose, settings)
```

- **Search**: BM25 via SQLite FTS5 — no vector DB
- **Ranking**: PageRank on citation graph — pure Python
- **Recommendations**: PageRank + recency + purpose keyword matching
- **Synthesis**: Multi-stage funnel retrieval (5K tokens for 10K papers)
- **Enrichment**: arXiv API (batched) with Semantic Scholar fallback
- **Backward compatible**: schema auto-migrates on upgrade, old layouts auto-detected

## Development

```bash
git clone https://github.com/Zhou-Hangyu/alit
cd alit
uv sync
uv run pytest
```

## License

MIT
