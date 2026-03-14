"""Tests for literature.scripts.cluster — pure Python clustering utilities."""

from __future__ import annotations

import pytest

from literature.scripts.cluster import (
    auto_k,
    cosine_similarity,
    find_nearest,
    kmeans,
    label_clusters,
    pairwise_cosine_matrix,
)


# ── cosine_similarity ──────────────────────────────────────────────────────────

def test_cosine_identical() -> None:
    """Identical vectors have similarity 1.0."""
    assert cosine_similarity([1, 0, 0], [1, 0, 0]) == pytest.approx(1.0)


def test_cosine_orthogonal() -> None:
    """Orthogonal vectors have similarity 0.0."""
    assert cosine_similarity([1, 0, 0], [0, 1, 0]) == pytest.approx(0.0)


def test_cosine_opposite() -> None:
    """Opposite vectors have similarity -1.0."""
    assert cosine_similarity([1, 0, 0], [-1, 0, 0]) == pytest.approx(-1.0)


def test_cosine_zero_vector() -> None:
    """Zero vector returns 0.0."""
    assert cosine_similarity([0, 0, 0], [1, 0, 0]) == pytest.approx(0.0)
    assert cosine_similarity([1, 0, 0], [0, 0, 0]) == pytest.approx(0.0)


def test_cosine_both_zero() -> None:
    """Both zero vectors return 0.0."""
    assert cosine_similarity([0, 0, 0], [0, 0, 0]) == pytest.approx(0.0)


def test_cosine_normalized() -> None:
    """Cosine similarity is scale-invariant."""
    # [1, 0, 0] and [2, 0, 0] should have similarity 1.0
    assert cosine_similarity([1, 0, 0], [2, 0, 0]) == pytest.approx(1.0)


def test_cosine_length_mismatch() -> None:
    """Mismatched vector lengths raise ValueError."""
    with pytest.raises(ValueError):
        cosine_similarity([1, 0], [1, 0, 0])


# ── pairwise_cosine_matrix ─────────────────────────────────────────────────────

def test_pairwise_matrix_symmetric() -> None:
    """Pairwise matrix is symmetric."""
    vectors = {
        "a": [1, 0, 0],
        "b": [0, 1, 0],
        "c": [1, 1, 0],
    }
    matrix = pairwise_cosine_matrix(vectors)
    
    assert matrix["a"]["b"] == pytest.approx(matrix["b"]["a"])
    assert matrix["a"]["c"] == pytest.approx(matrix["c"]["a"])
    assert matrix["b"]["c"] == pytest.approx(matrix["c"]["b"])


def test_pairwise_matrix_diagonal() -> None:
    """Diagonal elements are 1.0 (self-similarity)."""
    vectors = {
        "a": [1, 0, 0],
        "b": [0, 1, 0],
    }
    matrix = pairwise_cosine_matrix(vectors)
    
    assert matrix["a"]["a"] == pytest.approx(1.0)
    assert matrix["b"]["b"] == pytest.approx(1.0)


def test_pairwise_matrix_empty() -> None:
    """Empty vectors dict returns empty matrix."""
    matrix = pairwise_cosine_matrix({})
    assert matrix == {}


# ── kmeans ─────────────────────────────────────────────────────────────────────

def test_kmeans_k2() -> None:
    """K-means with k=2 returns exactly 2 clusters."""
    vectors = {
        "a": [1, 0, 0],
        "b": [1, 0, 0],
        "c": [0, 1, 0],
        "d": [0, 1, 0],
    }
    clusters = kmeans(vectors, k=2)
    
    assert len(clusters) == 2
    # All papers should be assigned
    all_papers = set()
    for citekeys in clusters.values():
        all_papers.update(citekeys)
    assert all_papers == {"a", "b", "c", "d"}


def test_kmeans_k3() -> None:
    """K-means with k=3 returns exactly 3 clusters."""
    vectors = {
        f"paper{i}": [float(i % 3), float(i // 3), 0.0]
        for i in range(9)
    }
    clusters = kmeans(vectors, k=3)
    
    assert len(clusters) == 3
    # All papers should be assigned
    all_papers = set()
    for citekeys in clusters.values():
        all_papers.update(citekeys)
    assert len(all_papers) == 9


def test_kmeans_k_exceeds_n() -> None:
    """K-means with k > n_papers reduces k to n_papers."""
    vectors = {
        "a": [1, 0, 0],
        "b": [0, 1, 0],
    }
    clusters = kmeans(vectors, k=5)
    
    # Should have at most 2 clusters
    assert len(clusters) <= 2


def test_kmeans_empty() -> None:
    """K-means on empty vectors returns empty dict."""
    clusters = kmeans({}, k=2)
    assert clusters == {}


def test_kmeans_single_paper() -> None:
    """K-means with single paper returns 1 cluster."""
    vectors = {"a": [1, 0, 0]}
    clusters = kmeans(vectors, k=2)
    
    assert len(clusters) == 1
    assert clusters[0] == ["a"]


# ── auto_k ────────────────────────────────────────────────────────────────────

def test_auto_k_small() -> None:
    """auto_k returns 2 for small n."""
    assert auto_k(4) == 2
    assert auto_k(8) == 2


def test_auto_k_medium() -> None:
    """auto_k scales with n."""
    assert auto_k(50) == 5


def test_auto_k_large() -> None:
    """auto_k caps at 12."""
    assert auto_k(288) == 12
    assert auto_k(1000) == 12


def test_auto_k_zero() -> None:
    """auto_k returns 2 for n=0."""
    assert auto_k(0) == 2


# ── label_clusters ────────────────────────────────────────────────────────────

def test_label_clusters_basic() -> None:
    """label_clusters returns top_n terms per cluster."""
    clusters = {
        0: ["paper1", "paper2"],
        1: ["paper3"],
    }
    abstracts = {
        "paper1": "machine learning neural networks deep learning",
        "paper2": "machine learning algorithms",
        "paper3": "natural language processing transformers",
    }
    
    labels = label_clusters(clusters, abstracts, top_n=2)
    
    assert 0 in labels
    assert 1 in labels
    assert len(labels[0]) <= 2
    assert len(labels[1]) <= 2


def test_label_clusters_no_stopwords() -> None:
    """label_clusters filters out stopwords."""
    clusters = {
        0: ["paper1"],
    }
    abstracts = {
        "paper1": "the and or but machine learning",
    }
    
    labels = label_clusters(clusters, abstracts, top_n=5)
    
    # Should not contain stopwords
    for term in labels[0]:
        assert term not in {"the", "and", "or", "but"}


def test_label_clusters_min_length() -> None:
    """label_clusters filters words shorter than 3 chars."""
    clusters = {
        0: ["paper1"],
    }
    abstracts = {
        "paper1": "a ab abc abcd machine learning",
    }
    
    labels = label_clusters(clusters, abstracts, top_n=5)
    
    # Should not contain words shorter than 3 chars
    for term in labels[0]:
        assert len(term) >= 3


def test_label_clusters_empty_abstract() -> None:
    """label_clusters handles empty abstracts."""
    clusters = {
        0: ["paper1"],
    }
    abstracts = {
        "paper1": "",
    }
    
    labels = label_clusters(clusters, abstracts, top_n=5)
    
    assert labels[0] == []


def test_label_clusters_missing_abstract() -> None:
    """label_clusters handles missing abstracts gracefully."""
    clusters = {
        0: ["paper1"],
    }
    abstracts = {}
    
    labels = label_clusters(clusters, abstracts, top_n=5)
    
    assert labels[0] == []


def test_label_clusters_top_n() -> None:
    """label_clusters respects top_n parameter."""
    clusters = {
        0: ["paper1"],
    }
    abstracts = {
        "paper1": "machine learning neural networks deep learning algorithms",
    }
    
    labels_2 = label_clusters(clusters, abstracts, top_n=2)
    labels_5 = label_clusters(clusters, abstracts, top_n=5)
    
    assert len(labels_2[0]) <= 2
    assert len(labels_5[0]) <= 5


# ── find_nearest ───────────────────────────────────────────────────────────────

def test_find_nearest_basic() -> None:
    """find_nearest returns top_k results sorted by similarity."""
    query = [1, 0, 0]
    vectors = {
        "a": [1, 0, 0],      # similarity 1.0
        "b": [0.5, 0.5, 0],  # similarity ~0.707
        "c": [0, 1, 0],      # similarity 0.0
    }
    
    results = find_nearest(query, vectors, top_k=3)
    
    assert len(results) == 3
    # Should be sorted descending by similarity
    assert results[0][1] >= results[1][1] >= results[2][1]


def test_find_nearest_top_k() -> None:
    """find_nearest respects top_k parameter."""
    query = [1, 0, 0]
    vectors = {f"paper{i}": [float(i), 0, 0] for i in range(10)}
    
    results_3 = find_nearest(query, vectors, top_k=3)
    results_5 = find_nearest(query, vectors, top_k=5)
    
    assert len(results_3) == 3
    assert len(results_5) == 5


def test_find_nearest_top_k_exceeds_n() -> None:
    """find_nearest returns at most n results."""
    query = [1, 0, 0]
    vectors = {
        "a": [1, 0, 0],
        "b": [0, 1, 0],
    }
    
    results = find_nearest(query, vectors, top_k=10)
    
    assert len(results) == 2


def test_find_nearest_sorted_descending() -> None:
    """find_nearest results are sorted descending by similarity."""
    query = [1, 0, 0]
    vectors = {
        "a": [0, 1, 0],      # similarity 0.0
        "b": [1, 0, 0],      # similarity 1.0
        "c": [0.5, 0.5, 0],  # similarity ~0.707
    }
    
    results = find_nearest(query, vectors, top_k=3)
    
    # Check descending order
    for i in range(len(results) - 1):
        assert results[i][1] >= results[i + 1][1]


def test_find_nearest_empty_vectors() -> None:
    """find_nearest on empty vectors returns empty list."""
    query = [1, 0, 0]
    results = find_nearest(query, {}, top_k=10)
    
    assert results == []


# ── Integration tests ──────────────────────────────────────────────────────────

def test_integration_cluster_and_label() -> None:
    """Integration: kmeans + label_clusters."""
    vectors = {
        "paper1": [1, 0, 0],
        "paper2": [1, 0, 0],
        "paper3": [0, 1, 0],
        "paper4": [0, 1, 0],
    }
    abstracts = {
        "paper1": "machine learning neural networks",
        "paper2": "machine learning algorithms",
        "paper3": "natural language processing",
        "paper4": "language models transformers",
    }
    
    clusters = kmeans(vectors, k=2)
    labels = label_clusters(clusters, abstracts, top_n=2)
    
    # Should have 2 clusters with labels
    assert len(clusters) == 2
    assert len(labels) == 2
    for cluster_id in clusters:
        assert isinstance(labels[cluster_id], list)


def test_integration_pairwise_and_nearest() -> None:
    """Integration: pairwise_cosine_matrix + find_nearest."""
    vectors = {
        "a": [1, 0, 0],
        "b": [0.5, 0.5, 0],
        "c": [0, 1, 0],
    }
    
    matrix = pairwise_cosine_matrix(vectors)
    results = find_nearest([1, 0, 0], vectors, top_k=2)
    
    # Pairwise matrix should match find_nearest results
    assert matrix["a"]["a"] == pytest.approx(results[0][1])
