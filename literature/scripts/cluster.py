#!/usr/bin/env python3
"""Pure Python clustering and similarity utilities for paper embeddings.

No external dependencies beyond the standard library.
"""
from __future__ import annotations

import math
import re
from collections import Counter, defaultdict

# ── Constants ──────────────────────────────────────────────────────────────────

STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "as", "is", "was", "are", "were", "be",
    "been", "being", "have", "has", "had", "do", "does", "did", "will",
    "would", "could", "should", "may", "might", "shall", "can", "not",
    "no", "nor", "so", "yet", "both", "either", "each", "that", "this",
    "these", "those", "we", "our", "they", "their", "its", "it", "all",
}


# ── Similarity ─────────────────────────────────────────────────────────────────

def cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """Cosine similarity between two vectors.
    
    Returns float in [-1, 1]. Returns 0.0 if either vector has zero norm.
    
    Args:
        vec_a: First vector
        vec_b: Second vector
        
    Returns:
        Cosine similarity score
    """
    if len(vec_a) != len(vec_b):
        raise ValueError(f"Vector lengths must match: {len(vec_a)} vs {len(vec_b)}")
    
    # Compute dot product
    dot_product = sum(a * b for a, b in zip(vec_a, vec_b))
    
    # Compute norms
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))
    
    # Handle zero vectors
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    
    return dot_product / (norm_a * norm_b)


def pairwise_cosine_matrix(vectors: dict[str, list[float]]) -> dict[str, dict[str, float]]:
    """Compute all-pairs cosine similarity.
    
    Args:
        vectors: Dict mapping citekey to embedding vector
        
    Returns:
        Nested dict where result[i][j] = cosine_similarity(vectors[i], vectors[j])
    """
    result: dict[str, dict[str, float]] = {}
    keys = list(vectors.keys())
    
    for i, key_i in enumerate(keys):
        result[key_i] = {}
        for key_j in keys:
            result[key_i][key_j] = cosine_similarity(vectors[key_i], vectors[key_j])
    
    return result


# ── K-Means ────────────────────────────────────────────────────────────────────

def kmeans(
    vectors: dict[str, list[float]],
    k: int,
    max_iter: int = 10,
) -> dict[int, list[str]]:
    """K-means clustering.
    
    Initializes centroids by picking k evenly-spaced items from sorted keys.
    Stops when assignments don't change or max_iter reached.
    If k > len(vectors), reduces k to len(vectors).
    
    Args:
        vectors: Dict mapping citekey to embedding vector
        k: Number of clusters
        max_iter: Maximum iterations
        
    Returns:
        Dict mapping cluster_id to list of citekeys
    """
    if not vectors:
        return {}
    
    # Reduce k if necessary
    k = min(k, len(vectors))
    
    # Initialize centroids: evenly-spaced items from sorted keys
    sorted_keys = sorted(vectors.keys())
    centroid_indices = [
        int(i * len(sorted_keys) / k) for i in range(k)
    ]
    centroids = [vectors[sorted_keys[idx]] for idx in centroid_indices]
    
    # K-means iterations
    for _ in range(max_iter):
        # Assign points to nearest centroid
        assignments: dict[int, list[str]] = defaultdict(list)
        for citekey, vec in vectors.items():
            distances = [
                math.sqrt(sum((v - c) ** 2 for v, c in zip(vec, centroid)))
                for centroid in centroids
            ]
            nearest_cluster = distances.index(min(distances))
            assignments[nearest_cluster].append(citekey)
        
        # Check for convergence (all clusters have assignments)
        if len(assignments) < k:
            # Some clusters are empty; stop
            break
        
        # Update centroids
        new_centroids = []
        for cluster_id in range(k):
            if cluster_id not in assignments or not assignments[cluster_id]:
                # Keep old centroid if cluster is empty
                new_centroids.append(centroids[cluster_id])
            else:
                cluster_vectors = [
                    vectors[citekey] for citekey in assignments[cluster_id]
                ]
                dim = len(cluster_vectors[0])
                new_centroid = [
                    sum(v[d] for v in cluster_vectors) / len(cluster_vectors)
                    for d in range(dim)
                ]
                new_centroids.append(new_centroid)
        
        # Check for convergence (centroids didn't change much)
        centroid_changed = False
        for old, new in zip(centroids, new_centroids):
            dist = math.sqrt(sum((o - n) ** 2 for o, n in zip(old, new)))
            if dist > 1e-6:
                centroid_changed = True
                break
        
        centroids = new_centroids
        
        if not centroid_changed:
            break
    
    # Final assignment
    final_assignments: dict[int, list[str]] = defaultdict(list)
    for citekey, vec in vectors.items():
        distances = [
            math.sqrt(sum((v - c) ** 2 for v, c in zip(vec, centroid)))
            for centroid in centroids
        ]
        nearest_cluster = distances.index(min(distances))
        final_assignments[nearest_cluster].append(citekey)
    
    return dict(final_assignments)


def auto_k(n_papers: int) -> int:
    """Heuristic for automatic k selection.
    
    Formula: max(2, min(int(sqrt(n/2)), 12))
    
    Args:
        n_papers: Number of papers
        
    Returns:
        Recommended number of clusters
    """
    return max(2, min(int(math.sqrt(n_papers / 2)), 12))


# ── Labeling ───────────────────────────────────────────────────────────────────

def label_clusters(
    clusters: dict[int, list[str]],
    abstracts: dict[str, str],
    top_n: int = 5,
) -> dict[int, list[str]]:
    """Label clusters using TF-IDF over abstracts.
    
    Tokenization: lowercase, split on non-alpha (re.split(r'[^a-z]+', text.lower())),
    filter stopwords, min length 3.
    
    TF = term freq in cluster / total words in cluster
    IDF = log(total_clusters / clusters_containing_term + 1) + 1
    TF-IDF score = TF * IDF
    
    Args:
        clusters: Dict mapping cluster_id to list of citekeys
        abstracts: Dict mapping citekey to abstract text
        top_n: Number of top terms to return per cluster
        
    Returns:
        Dict mapping cluster_id to list of top_n terms
    """
    result: dict[int, list[str]] = {}
    
    # Tokenize all abstracts
    cluster_tokens: dict[int, list[str]] = {}
    for cluster_id, citekeys in clusters.items():
        tokens = []
        for citekey in citekeys:
            abstract = abstracts.get(citekey, "")
            # Tokenize: lowercase, split on non-alpha, filter stopwords and short words
            words = re.split(r"[^a-z]+", abstract.lower())
            for word in words:
                if word and len(word) >= 3 and word not in STOPWORDS:
                    tokens.append(word)
        cluster_tokens[cluster_id] = tokens
    
    # Compute TF-IDF for each cluster
    for cluster_id, tokens in cluster_tokens.items():
        if not tokens:
            result[cluster_id] = []
            continue
        
        # TF: term frequency in this cluster
        term_counts = Counter(tokens)
        total_words = len(tokens)
        tf = {term: count / total_words for term, count in term_counts.items()}
        
        # IDF: inverse document frequency (clusters containing term)
        clusters_with_term = defaultdict(int)
        for cid, ctokens in cluster_tokens.items():
            unique_terms = set(ctokens)
            for term in unique_terms:
                clusters_with_term[term] += 1
        
        total_clusters = len(clusters)
        idf = {
            term: math.log(total_clusters / (clusters_with_term[term] + 1)) + 1
            for term in tf.keys()
        }
        
        # TF-IDF
        tfidf = {term: tf[term] * idf[term] for term in tf.keys()}
        
        # Top N terms
        top_terms = sorted(tfidf.items(), key=lambda x: x[1], reverse=True)[:top_n]
        result[cluster_id] = [term for term, _ in top_terms]
    
    return result


# ── Nearest Neighbor ───────────────────────────────────────────────────────────

def find_nearest(
    query_vector: list[float],
    vectors: dict[str, list[float]],
    top_k: int = 10,
) -> list[tuple[str, float]]:
    """Find top_k most similar vectors by cosine similarity.
    
    Returns top_k most similar (citekey, score) pairs, sorted descending by score.
    Excludes the query vector itself if it appears in vectors.
    
    Args:
        query_vector: Query embedding vector
        vectors: Dict mapping citekey to embedding vector
        top_k: Number of results to return
        
    Returns:
        List of (citekey, cosine_similarity) tuples, sorted descending by similarity
    """
    similarities: list[tuple[str, float]] = []
    
    for citekey, vec in vectors.items():
        sim = cosine_similarity(query_vector, vec)
        similarities.append((citekey, sim))
    
    # Sort descending by similarity
    similarities.sort(key=lambda x: x[1], reverse=True)
    
    # Return top_k
    return similarities[:top_k]
