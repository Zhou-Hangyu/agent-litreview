# (-o-) alit

Your AI agent reads papers so you don't have to.

`pip install agent-lit` → zero dependencies, SQLite-only, works with any coding agent.

Same spirit as [autoresearch](https://github.com/karpathy/autoresearch) — but for the literature review that comes before experiments. Give your agent a research taste, point it at arXiv, and let it go. It reads papers, writes summaries, builds a citation graph, and ranks what to read next. You wake up to a structured knowledge base instead of 47 open browser tabs. The agent modifies the knowledge. You modify the taste. That's the whole loop.

Why not just web search? Your agent forgets everything next session. alit is persistent memory — one agent reads 50 papers, another queries that knowledge instantly. Knowledge compounds across sessions.

Tell your agent to set alit up:

```
Use alit to manage my literature review. See https://github.com/Zhou-Hangyu/alit
```

## How it works

Three things that matter:

- **`.alit/papers.db`** — one SQLite file. The entire knowledge base. Summaries, citations, PageRank scores, reading status. Agent reads and writes this.
- **`alit taste`** — your research program. What excites you, what to prioritize. You edit this, agent follows it. Like `program.md` but for literature.
- **`alit` CLI** — the agent's interface. Search, recommend, synthesize, add papers. All via Bash commands.

```
.alit/
├── papers.db    ← one file, entire knowledge base
└── pdfs/        ← auto-downloaded from arXiv
```

No servers. No API keys. No vector databases.

## Quick start

```bash
pip install agent-lit
alit init
alit taste "I'm into multimodal foundation models and how they learn cross-modal
representations. Love papers with clean ablations over pure benchmark chasing."
```

Then tell your agent to go:

```bash
alit add "https://arxiv.org/abs/1706.03762"     # fetches metadata + PDF
alit import library.bib                          # or dump your Zotero/Mendeley
alit recommend 5                                 # ranked by your taste
alit ask "What are the key attention mechanisms?" --depth 2
```

The agent reads papers, stores summaries with `alit summarize`, builds citations with `alit cite`, and checks what to read next with `alit recommend`. Repeat.

## Update

```bash
pip install --upgrade agent-lit
```

Run `alit --help` for the full command list.

## Under the hood

- **Search**: BM25 via SQLite FTS5
- **Ranking**: PageRank on citation graph (pure Python)
- **Recommendations**: PageRank + recency + taste matching
- **Synthesis**: multi-stage funnel retrieval (~5K tokens to query 10K papers)
- **Enrichment**: arXiv API (batched) with Semantic Scholar fallback
- **Backward compatible**: schema auto-migrates on upgrade

## License

MIT
