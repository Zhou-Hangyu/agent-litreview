---
name: literature-review
description: "Lightweight literature review system. Zero dependencies, SQLite-only. Use when managing research papers — adding, searching, reading, summarizing, synthesizing. Run `lit init` to start."
---

# Literature Review System

Zero dependencies. SQLite-only. You are the intelligence — the system is data plumbing.

## Quick Start

```bash
lit init                    # creates papers.db
lit add "Paper Title" --year 2024 --abstract "..." --authors "Smith, Jones" --arxiv "2401.12345"
lit search "attention"      # BM25 search
lit recommend 5             # what to read next
```

## Adding Papers

You (the agent) read the paper or its arXiv page, then store the metadata:

```bash
lit add "Attention Is All You Need" \
  --id vaswani2017attention \
  --year 2017 \
  --authors "Vaswani, Shazeer, Parmar" \
  --abstract "The dominant sequence transduction models are based on complex recurrent or convolutional neural networks..." \
  --url "https://arxiv.org/abs/1706.03762" \
  --arxiv "1706.03762" \
  --tags "transformers,attention,nlp"
```

If `--id` is omitted, one is auto-generated from the title.

When `--arxiv` is provided, the PDF is auto-downloaded to `papers/` next to `papers.db`. Use `--no-pdf` to skip. For existing papers: `lit fetch-pdf <id>`.

## After Reading a Paper

```bash
lit status vaswani2017attention read

lit note vaswani2017attention "Key insight: self-attention replaces recurrence entirely. O(1) sequential ops for long-range deps."

lit summarize vaswani2017attention --l4 "Transformer replaces recurrence with self-attention, achieving BLEU SOTA with greater parallelism." --model "claude-opus-4-6"

lit summarize vaswani2017attention --l2 '["Self-attention O(1) vs RNN O(n)", "Multi-head attention for subspace diversity", "28.4 BLEU on WMT EN-DE"]' --model "claude-opus-4-6"

lit cite vaswani2017attention bahdanau2014attention --type extends
```

## Searching and Synthesis

```bash
lit search "limit order book simulation"

lit ask "What generative models exist for LOB data?" --depth 2
```

Depth controls token budget:
- `--depth 1`: titles + one-liners (~500 tokens)
- `--depth 2`: + abstracts for top-10 (~2.5K tokens) — DEFAULT
- `--depth 3`: + key claims for top-3 (~3.5K tokens)
- `--depth 4`: + full notes for top-1 (~5K tokens)

## Recommendations

```bash
lit recommend 5

lit purpose "Research on generative models for limit order book simulation, market microstructure, and agent-based financial systems"
lit recommend 5
```

## All Commands

| Command | What it does |
|---------|-------------|
| `lit init` | Create papers.db |
| `lit add <title> [opts]` | Add paper with metadata |
| `lit show <id>` | Paper details |
| `lit list [--status X]` | List papers |
| `lit search <query>` | BM25 search |
| `lit note <id> <text>` | Append notes |
| `lit summarize <id> --l4/--l2` | Store summary with provenance |
| `lit cite <from> <to>` | Add citation edge |
| `lit status <id> <status>` | Set reading status |
| `lit tag <id> <tags>` | Set tags |
| `lit recommend [N]` | Reading recommendations |
| `lit ask <question>` | Cross-paper synthesis |
| `lit stats` | Collection overview |
| `lit delete <id>` | Remove paper |
| `lit purpose <text>` | Set research purpose |
| `lit fetch-pdf <id>` | Download PDF for existing paper |
| `lit export` | Export as JSON |

All commands support `--json` for machine-readable output.

## Conventions

- **IDs**: lowercase, no spaces (e.g. `vaswani2017attention`). Auto-generated if omitted.
- **Status**: unread → skimmed → read → synthesized
- **Citation types**: cites, extends, contradicts, uses_method, uses_dataset, surveys
- **Provenance**: always pass `--model` when summarizing — it's tracked
- **PDFs**: auto-downloaded from arXiv when `--arxiv` is set. Stored in `papers/` next to `papers.db`
