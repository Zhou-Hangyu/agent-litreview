#!/usr/bin/env python3
"""Research landscape analysis — clusters papers by SPECTER2 embeddings,
detects research fronts, structural holes, and citation gaps.

Usage:
    uv run python literature/scripts/landscape.py [--root DIR]
"""
from __future__ import annotations

import argparse
import datetime
import sys
from pathlib import Path


from ruamel.yaml import YAML

from literature.scripts.cluster import auto_k, cosine_similarity, kmeans, label_clusters
from literature.scripts.parse import read_frontmatter


# ── YAML setup ─────────────────────────────────────────────────────────────────

def _make_yaml() -> YAML:
    """Create a YAML instance for reading/writing files."""
    y = YAML()
    y.default_flow_style = False
    y.preserve_quotes = True
    y.width = 4096
    return y


# ── Helpers ─────────────────────────────────────────────────────────────────────

def _find_literature_root(start: Path | None = None) -> Path:
    """Search upward from *start* for a directory containing literature/AGENTS.md."""
    current = (start or Path.cwd()).resolve()
    for parent in [current, *current.parents]:
        candidate = parent / "literature" / "AGENTS.md"
        if candidate.is_file():
            return parent / "literature"
    return Path("./literature")


# ── Data loaders ────────────────────────────────────────────────────────────────

def _load_embeddings(index_dir: Path) -> dict[str, list[float]]:
    """Load index/embeddings.yaml, return {citekey: vector}. Empty dict if not found."""
    embeddings_path = index_dir / "embeddings.yaml"
    if not embeddings_path.exists():
        return {}
    yaml = _make_yaml()
    with embeddings_path.open(encoding="utf-8") as fh:
        data = yaml.load(fh)
    return dict(data.get("vectors") or {})


def _load_papers_metadata(papers_dir: Path) -> dict[str, dict]:
    """Read all paper frontmatter. Returns {citekey: metadata_dict}."""
    result = {}
    for path in sorted(papers_dir.glob("*.md")):
        meta, _ = read_frontmatter(path)  # read_frontmatter returns (meta, body) TUPLE
        ck = meta.get("citekey") or meta.get("doc_id")
        if ck:
            result[ck] = dict(meta)
    return result


def _load_citation_edges(graph_data: dict) -> dict[str, list[str]]:
    """Extract {citekey: [cited_citekeys]} from graph.yaml nodes section."""
    # graph.yaml uses "nodes:" key (not "papers:")
    edges: dict[str, list[str]] = {}
    for citekey, node_data in (graph_data.get("nodes") or {}).items():
        raw_cites = node_data.get("cites") or []
        # cites can be a list of strings OR list of dicts with 'id' key
        resolved: list[str] = []
        for item in raw_cites:
            if isinstance(item, dict):
                resolved.append(item.get("id", ""))
            else:
                resolved.append(str(item))
        edges[citekey] = [c for c in resolved if c]
    return edges


# ── Analysis functions ─────────────────────────────────────────────────────────

def _find_citation_gaps(edges: dict[str, list[str]], collection: set[str]) -> list[dict]:
    """Papers cited by >=2 collection papers but not in collection."""
    cited_count: dict[str, int] = {}
    cited_by_map: dict[str, list[str]] = {}
    for citekey, cited_list in edges.items():
        for cited in cited_list:
            if cited not in collection:
                cited_count[cited] = cited_count.get(cited, 0) + 1
                cited_by_map.setdefault(cited, []).append(citekey)
    gaps = [
        {"id": cid, "cited_by_count": cnt, "cited_by": cited_by_map[cid]}
        for cid, cnt in sorted(cited_count.items(), key=lambda x: -x[1])
        if cnt >= 2
    ]
    return gaps


def _detect_research_fronts(
    clusters: dict[int, list[str]],
    papers_meta: dict[str, dict],
    current_year: int | None = None,
) -> list[tuple[int, float]]:
    """Top 3 clusters by citation velocity.

    Velocity = sum(citation_count where year >= current_year-2) / cluster_size.
    """
    if current_year is None:
        current_year = datetime.datetime.now().year
    threshold_year = current_year - 2

    velocities = []
    for cluster_id, citekeys in clusters.items():
        recent_citations = sum(
            papers_meta.get(ck, {}).get("citation_count", 0) or 0
            for ck in citekeys
            if (papers_meta.get(ck, {}).get("year") or 0) >= threshold_year
        )
        velocity = recent_citations / max(len(citekeys), 1)
        velocities.append((cluster_id, velocity))

    # Top 3 by velocity
    top3 = sorted(velocities, key=lambda x: -x[1])[:3]
    return [(cid, vel) for cid, vel in top3 if vel > 0]


def _detect_structural_holes(
    clusters: dict[int, list[str]],
    edges: dict[str, list[str]],
) -> list[dict]:
    """Cluster pairs with inter-cluster citation density < 0.05."""
    cluster_ids = list(clusters.keys())
    holes = []
    for i in range(len(cluster_ids)):
        for j in range(i + 1, len(cluster_ids)):
            ca, cb = cluster_ids[i], cluster_ids[j]
            set_a, set_b = set(clusters[ca]), set(clusters[cb])
            # Count edges from A -> B and B -> A
            inter = sum(
                1
                for ck in set_a
                for cited in (edges.get(ck) or [])
                if cited in set_b
            ) + sum(
                1
                for ck in set_b
                for cited in (edges.get(ck) or [])
                if cited in set_a
            )
            density = inter / max(len(set_a) * len(set_b), 1)
            if density < 0.05:
                holes.append({"cluster_a": ca, "cluster_b": cb, "density": round(density, 4)})
    return holes


# ── Main analysis ──────────────────────────────────────────────────────────────

def _build_landscape(lit_root: Path) -> dict:
    """Run full landscape analysis. Returns landscape data dict."""
    papers_dir = lit_root / "papers"
    index_dir = lit_root / "index"
    graph_path = index_dir / "graph.yaml"

    yaml = _make_yaml()
    graph_data: dict = {}
    if graph_path.exists():
        with graph_path.open(encoding="utf-8") as fh:
            graph_data = yaml.load(fh) or {}

    papers_meta = _load_papers_metadata(papers_dir)
    embeddings = _load_embeddings(index_dir)
    edges = _load_citation_edges(graph_data)
    collection = set(papers_meta.keys())

    # Cluster using embeddings (only papers with embeddings)
    embedded_vectors = {ck: list(v) for ck, v in embeddings.items() if ck in papers_meta}
    clusters: dict[int, list[str]] = {}
    cluster_labels: dict[int, list[str]] = {}

    if len(embedded_vectors) >= 3:
        k = auto_k(len(embedded_vectors))
        clusters = kmeans(embedded_vectors, k)
        # Build abstracts dict for labeling
        abstracts = {ck: papers_meta.get(ck, {}).get("abstract") or "" for ck in embedded_vectors}
        cluster_labels = label_clusters(clusters, abstracts)
    else:
        # Graceful degradation: put all in cluster 0
        clusters = {0: list(collection)}
        cluster_labels = {0: []}

    fronts = _detect_research_fronts(clusters, papers_meta)
    holes = _detect_structural_holes(clusters, edges)
    gaps = _find_citation_gaps(edges, collection)

    # Build output data structure
    cluster_data: dict[int, dict] = {}
    for cid, citekeys in clusters.items():
        cluster_papers = [ck for ck in citekeys if ck in papers_meta]
        years = [papers_meta[ck].get("year") or 0 for ck in cluster_papers if papers_meta[ck].get("year")]
        cites = [papers_meta[ck].get("citation_count") or 0 for ck in cluster_papers]
        cluster_data[cid] = {
            "label": cluster_labels.get(cid, []),
            "papers": cluster_papers,
            "size": len(cluster_papers),
            "avg_year": round(sum(years) / max(len(years), 1), 1) if years else 0,
            "avg_citations": round(sum(cites) / max(len(cites), 1)),
        }

    return {
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "paper_count": len(papers_meta),
        "cluster_count": len(clusters),
        "clusters": cluster_data,
        "research_fronts": [
            {
                "cluster_id": cid,
                "label": cluster_labels.get(cid, []),
                "velocity": round(vel, 2),
                "key_papers": clusters.get(cid, [])[:3],
            }
            for cid, vel in fronts
        ],
        "structural_holes": holes,
        "citation_gaps": gaps[:20],  # top 20
    }


# ── Output writers ─────────────────────────────────────────────────────────────

def _write_markdown(data: dict, output_path: Path) -> None:
    """Write landscape.md narrative report."""
    lines = [
        "# Research Landscape Report",
        f"\n_Generated: {data['generated_at']}_\n",
        f"**{data['paper_count']} papers** across **{data['cluster_count']} clusters**\n",
        "## Clusters\n",
    ]
    for cid, cluster in sorted(data["clusters"].items()):
        label_str = ", ".join(cluster["label"][:5]) if cluster["label"] else "unlabeled"
        lines.append(f"### Cluster {cid}: {label_str}")
        lines.append(
            f"- **Papers**: {cluster['size']} | Avg year: {cluster['avg_year']} | Avg citations: {cluster['avg_citations']}"
        )
        lines.append(
            f"- **Papers**: {', '.join(cluster['papers'][:5])}"
            + (" ..." if len(cluster["papers"]) > 5 else "")
        )
        lines.append("")

    lines.append("## Research Fronts\n")
    if data["research_fronts"]:
        for front in data["research_fronts"]:
            label_str = ", ".join(front["label"][:3]) if front["label"] else "unlabeled"
            lines.append(f"- **Cluster {front['cluster_id']}** ({label_str}): velocity={front['velocity']}")
    else:
        lines.append("_No active research fronts detected._\n")

    lines.append("\n## Structural Holes\n")
    if data["structural_holes"]:
        for hole in data["structural_holes"][:5]:
            lines.append(f"- Clusters {hole['cluster_a']} ↔ {hole['cluster_b']}: density={hole['density']}")
    else:
        lines.append("_No structural holes detected._\n")

    lines.append("\n## Citation Gaps\n")
    if data["citation_gaps"]:
        for gap in data["citation_gaps"][:10]:
            lines.append(
                f"- `{gap['id']}` — cited by {gap['cited_by_count']} papers: {', '.join(gap['cited_by'][:3])}"
            )
    else:
        lines.append("_No citation gaps found._\n")

    lines.append("\n## Reading Recommendations\n")
    # Research front papers first
    front_papers: list[str] = []
    for front in data["research_fronts"]:
        front_papers.extend(front.get("key_papers", []))
    gap_papers = [g["id"] for g in data["citation_gaps"][:5]]
    all_recs = front_papers[:5] + [p for p in gap_papers if p not in front_papers][:5]
    if all_recs:
        for rec in all_recs[:10]:
            lines.append(f"1. `{rec}`")
    else:
        lines.append("_No recommendations available._")

    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ── CLI ────────────────────────────────────────────────────────────────────────

def run(argv: list[str] | None = None, *, lit_root: Path | None = None) -> int:
    """Run the landscape analysis CLI.

    Args:
        argv: Command-line arguments (default: sys.argv[1:]).
        lit_root: Path to the literature/ directory; overrides ``--root`` flag.

    Returns:
        Exit code.
    """
    parser = argparse.ArgumentParser(description="Research landscape analysis")
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="Path to literature/ directory (default: auto-detect)",
    )
    args = parser.parse_args(argv)

    if lit_root is None:
        lit_root = args.root or _find_literature_root()

    data = _build_landscape(lit_root)

    # Write YAML (inside literature/ dir)
    yaml = _make_yaml()
    yaml_path = lit_root / "landscape.yaml"
    with yaml_path.open("w", encoding="utf-8") as fh:
        yaml.dump(data, fh)
    print(f"Wrote {yaml_path}")

    # Write Markdown (inside literature/ dir)
    md_path = lit_root / "landscape.md"
    _write_markdown(data, md_path)
    print(f"Wrote {md_path}")

    return 0


def main() -> None:
    sys.exit(run())


if __name__ == "__main__":
    main()
