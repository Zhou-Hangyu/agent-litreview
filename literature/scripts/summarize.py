#!/usr/bin/env python3
"""
Extract text from a paper's linked PDF.

Usage:
    uv run python literature/scripts/summarize.py kawawa-beaudan2026tradefm
    uv run python literature/scripts/summarize.py kawawa-beaudan2026tradefm --write
    uv run python literature/scripts/summarize.py kawawa-beaudan2026tradefm --root /path/to/literature/
"""

from __future__ import annotations

import argparse
import statistics
import sys
from pathlib import Path


import pymupdf

from literature.scripts.parse import read_frontmatter, write_paper_file

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LIT_ROOT = REPO_ROOT / "literature"


def extract_pdf_text(pdf_path: Path) -> str:
    doc = pymupdf.open(str(pdf_path))
    pages: list[str] = []
    for page_num, page in enumerate(doc, 1):
        text = page.get_text()
        pages.append(f"--- Page {page_num} ---\n{text}")
    doc.close()
    return "\n".join(pages)


def extract_structured(pdf_path: Path) -> dict:
    """Extract structured content from PDF using font-size based heading detection.

    Uses pymupdf's page.get_text("dict") to get per-block font metadata.

    Returns:
        dict with keys:
            "sections": list of {"heading": str, "text": str, "page": int}
            "abstract": str  (text of abstract section, empty if not found)
            "conclusion": str  (text of conclusion section, empty if not found)
            "section_headings": list[str]  (just heading names)
    """
    doc = pymupdf.open(str(pdf_path))

    # Collect all block data in a single pass
    all_sizes: list[float] = []
    blocks_data: list[tuple[int, str, float]] = []  # (page_num, text, max_size)

    for page_num, page in enumerate(doc, 1):
        data = page.get_text("dict")
        for block in data["blocks"]:
            if block["type"] != 0:  # skip image blocks
                continue
            parts: list[str] = []
            max_size = 0.0
            for line in block["lines"]:
                line_texts: list[str] = []
                for span in line["spans"]:
                    line_texts.append(span["text"])
                    if span["text"].strip():
                        all_sizes.append(span["size"])
                        if span["size"] > max_size:
                            max_size = span["size"]
                line_text = "".join(line_texts).strip()
                if line_text:
                    parts.append(line_text)
            text = " ".join(parts)
            if text:
                blocks_data.append((page_num, text, max_size))

    doc.close()

    if not all_sizes:
        return {
            "sections": [],
            "abstract": "",
            "conclusion": "",
            "section_headings": [],
        }

    median_size = statistics.median(all_sizes)
    threshold = median_size * 1.2

    # Build sections by detecting headings
    sections: list[dict] = []
    cur_heading = ""
    cur_texts: list[str] = []
    cur_page = 1

    for pg, text, max_sz in blocks_data:
        if max_sz > threshold and len(text) < 120:
            # New heading — save previous section
            if cur_heading or cur_texts:
                sections.append(
                    {
                        "heading": cur_heading,
                        "text": "\n".join(cur_texts).strip(),
                        "page": cur_page,
                    }
                )
            cur_heading = text
            cur_texts = []
            cur_page = pg
        else:
            cur_texts.append(text)

    # Save last section
    if cur_heading or cur_texts:
        sections.append(
            {
                "heading": cur_heading,
                "text": "\n".join(cur_texts).strip(),
                "page": cur_page,
            }
        )

    # Filter out references/acknowledgments
    _SKIP = {"references", "bibliography", "acknowledgments", "acknowledgements"}
    filtered: list[dict] = []
    for s in sections:
        low = s["heading"].lower().strip()
        if low in ("references", "bibliography"):
            break  # skip everything from references onward
        if low in _SKIP:
            continue  # skip just this section
        filtered.append(s)

    # Extract abstract and conclusion
    abstract = ""
    conclusion = ""
    for s in filtered:
        low = s["heading"].lower()
        if "abstract" in low and not abstract:
            abstract = s["text"]
        elif low in ("conclusion", "conclusions", "discussion") and not conclusion:
            conclusion = s["text"]

    # Fallback: use first paragraph as abstract
    if not abstract:
        for s in filtered:
            if s["text"]:
                abstract = s["text"]
                break

    headings = [s["heading"] for s in filtered if s["heading"]]

    return {
        "sections": filtered,
        "abstract": abstract,
        "conclusion": conclusion,
        "section_headings": headings,
    }


def run(argv: list[str] | None = None, *, lit_root: Path | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="summarize.py",
        description="Extract text from a paper's linked PDF.",
    )
    parser.add_argument("citekey", help="Citekey of the paper to summarize.")
    parser.add_argument(
        "--write",
        action="store_true",
        help="Write extracted text into the .md file body instead of printing to stdout.",
    )
    parser.add_argument(
        "--root",
        default=None,
        help="Path to the literature/ directory root.",
    )
    args = parser.parse_args(argv)

    _lit_root = lit_root or (Path(args.root) if args.root else DEFAULT_LIT_ROOT)
    paper_path = _lit_root / "papers" / f"{args.citekey}.md"

    if not paper_path.exists():
        print(
            f"Error: Paper '{args.citekey}' not found at {paper_path}",
            file=sys.stderr,
        )
        return 1

    meta, body = read_frontmatter(paper_path)

    pdf_path_str: str = str(meta.get("pdf_path") or "")
    if not pdf_path_str:
        print(
            f"Error: Paper '{args.citekey}' has no pdf_path in frontmatter. "
            "Run enrich.py to detect the PDF or manually set pdf_path.",
            file=sys.stderr,
        )
        return 1

    pdf_path = REPO_ROOT / pdf_path_str
    if not pdf_path.exists():
        print(
            f"Error: PDF file not found at {pdf_path}",
            file=sys.stderr,
        )
        return 1

    if not args.write:
        extracted_text = extract_pdf_text(pdf_path)
        print(extracted_text)
        return 0

    structured = extract_structured(pdf_path)
    abstract_text = structured["abstract"] or "(Not extracted)"
    conclusion_text = structured["conclusion"] or "(Not extracted)"
    headings_text = "\n".join(structured["section_headings"])

    new_body = (
        "## Abstract\n\n"
        f"{abstract_text}\n\n"
        "## Conclusion\n\n"
        f"{conclusion_text}\n\n"
        "## Section Outline\n\n"
        f"{headings_text}\n"
    )

    reading_status = dict(meta.get("reading_status") or {})
    reading_status["global"] = "skimmed"
    meta["reading_status"] = reading_status

    write_paper_file(paper_path, meta, new_body)
    print(str(paper_path))
    return 0


def main() -> None:
    sys.exit(run())


if __name__ == "__main__":
    main()
