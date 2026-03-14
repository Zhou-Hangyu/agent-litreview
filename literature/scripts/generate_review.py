"""
Generate a NeurIPS-format LaTeX literature review from theme files.

Reads theme files from literature/themes/, renders the Jinja2 template,
and writes the output to literature/output/. Also copies references.bib
and neurips_2025.sty to the output directory.

Usage:
    uv run python literature/scripts/generate_review.py
    uv run python literature/scripts/generate_review.py --title "My Survey" --authors "Alice, Bob"
    uv run python literature/scripts/generate_review.py --root /path/to/literature/
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path


from jinja2 import Environment, FileSystemLoader

from literature.scripts.parse import read_frontmatter


def _find_literature_root(start: Path | None = None) -> Path:
    """Search upward from *start* for a directory containing literature/AGENTS.md."""
    current = (start or Path.cwd()).resolve()
    for parent in [current, *current.parents]:
        if (parent / "literature" / "AGENTS.md").is_file():
            return parent / "literature"
    return Path("./literature")


def load_themes(themes_dir: Path) -> list[dict]:
    """Load and sort theme files from themes_dir.

    Args:
        themes_dir: Path to the literature/themes/ directory.

    Returns:
        List of theme dicts with 'title', 'order', and 'content' keys,
        sorted by 'order'. Returns empty list if directory doesn't exist.
    """
    if not themes_dir.is_dir():
        return []

    themes: list[dict] = []
    for md_file in themes_dir.glob("*.md"):
        if md_file.name == ".gitkeep":
            continue
        meta, body = read_frontmatter(md_file)
        title = str(meta.get("title", md_file.stem))
        try:
            order = int(meta.get("order", 999))
        except (TypeError, ValueError):
            order = 999
        themes.append({"title": title, "order": order, "content": body.strip()})

    themes.sort(key=lambda t: (t["order"], t["title"]))
    return themes


def find_cite_keys(themes: list[dict]) -> set[str]:
    """Extract all \\cite{key} references from theme content."""
    keys: set[str] = set()
    pattern = re.compile(r"\\cite[tp]?\{([^}]+)\}")
    for theme in themes:
        for match in pattern.finditer(theme.get("content", "")):
            # Handle comma-separated keys: \cite{key1, key2}
            for key in match.group(1).split(","):
                keys.add(key.strip())
    return keys


def check_cite_keys(cite_keys: set[str], bib_path: Path) -> list[str]:
    """Return list of cite keys missing from the BibTeX file."""
    if not bib_path.exists():
        return sorted(cite_keys)
    bib_content = bib_path.read_text(encoding="utf-8")
    missing: list[str] = []
    for key in sorted(cite_keys):
        if f"{{{key}," not in bib_content:
            missing.append(key)
    return missing


def generate(
    root: Path,
    title: str = "Literature Review",
    authors: str = "",
    abstract: str = "A comprehensive literature review.",
) -> Path:
    """Generate the LaTeX review and copy supporting files to output/.

    Args:
        root: Path to the literature/ directory.
        title: Review title.
        authors: Author string.
        abstract: Abstract text.

    Returns:
        Path to the generated review.tex file.
    """
    themes_dir = root / "themes"
    output_dir = root / "output"
    index_dir = root / "index"
    templates_dir = root / "templates"

    output_dir.mkdir(parents=True, exist_ok=True)

    themes = load_themes(themes_dir)
    if not themes:
        print("Warning: no theme files found in themes/. Generating minimal document.", file=sys.stderr)
        themes = [{"title": "Introduction", "order": 1, "content": "No themes defined yet."}]

    # Warn about missing cite keys
    bib_src = index_dir / "references.bib"
    cite_keys = find_cite_keys(themes)
    if cite_keys:
        missing = check_cite_keys(cite_keys, bib_src)
        for key in missing:
            print(f"Warning: \\cite{{{key}}} has no matching BibTeX entry.", file=sys.stderr)

    # Render template
    env = Environment(
        loader=FileSystemLoader(str(templates_dir)),
        autoescape=False,
        keep_trailing_newline=True,
    )
    template = env.get_template("review_template.tex.j2")
    rendered = template.render(
        title=title,
        authors=authors,
        abstract=abstract,
        sections=themes,
    )

    tex_path = output_dir / "review.tex"
    tex_path.write_text(rendered, encoding="utf-8")
    print(f"Generated: {tex_path}")

    # Copy references.bib
    bib_dst = output_dir / "references.bib"
    if bib_src.exists():
        shutil.copy2(bib_src, bib_dst)
        print(f"Copied:    {bib_dst}")
    else:
        print(
            "Warning: literature/index/references.bib not found. "
            "Run rebuild_index.py first.",
            file=sys.stderr,
        )
        bib_dst.write_text("% Empty — run rebuild_index.py first\n", encoding="utf-8")

    # Copy neurips_2025.sty
    sty_src = templates_dir / "neurips_2025.sty"
    if sty_src.exists():
        sty_dst = output_dir / "neurips_2025.sty"
        shutil.copy2(sty_src, sty_dst)
        print(f"Copied:    {sty_dst}")

    print(
        "\nTo compile:\n"
        f"  cd {output_dir}\n"
        "  pdflatex review.tex && bibtex review && pdflatex review.tex && pdflatex review.tex"
    )
    return tex_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate a NeurIPS-format LaTeX literature review from theme files.",
    )
    parser.add_argument("--title", default="Literature Review", help="Review title")
    parser.add_argument("--authors", default="", help="Author string")
    parser.add_argument("--abstract", default="A comprehensive literature review.", help="Abstract text")
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="Path to literature/ directory (default: auto-detect)",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    root = args.root or _find_literature_root()
    generate(root, title=args.title, authors=args.authors, abstract=args.abstract)


if __name__ == "__main__":
    main()
