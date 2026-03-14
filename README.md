# agent-litreview

Lightweight literature review system for AI coding agents. Zero dependencies. SQLite-only.

## Install

```bash
pip install agent-litreview
```

## Use

```bash
lit init
lit add "Attention Is All You Need" --year 2017 --abstract "..." --id vaswani2017attention
lit search "attention"
lit recommend 5
lit ask "What approaches exist for sequence modeling?" --depth 2
```

## Agent Integration

```bash
lit install-skill    # installs SKILL.md for opencode/Claude Code
```

See `lit --help` for all commands.
