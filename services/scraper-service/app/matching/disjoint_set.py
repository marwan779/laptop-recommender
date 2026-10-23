"""Disjoint-Set (Union-Find) Data Structure for Transitive Product Clustering.

Guarantees near-O(1) amortized equivalence resolution across multiple
matching criteria (MPN, silicon fingerprint, retailer sku).
"""

from __future__ import annotations

from collections import defaultdict


class DisjointSet:
    """Disjoint-set forest with union-by-rank and path compression."""

    def __init__(self) -> None:
        self.parent: dict[str, str] = {}
        self.rank: dict[str, int] = {}

    def find(self, item: str) -> str:
        """Find the representative root of the set containing item, applying path compression."""
        if item not in self.parent:
            self.parent[item] = item
            self.rank[item] = 0
            return item

        if self.parent[item] != item:
            self.parent[item] = self.find(self.parent[item])
        return self.parent[item]

    def union(self, item1: str, item2: str) -> str:
        """Union the sets containing item1 and item2 using rank optimization.

        Returns the consolidated root identifier.
        """
        root1 = self.find(item1)
        root2 = self.find(item2)

        if root1 == root2:
            return root1

        # Union by rank
        if self.rank[root1] < self.rank[root2]:
            self.parent[root1] = root2
            return root2
        elif self.rank[root1] > self.rank[root2]:
            self.parent[root2] = root1
            return root1
        else:
            self.parent[root2] = root1
            self.rank[root1] += 1
            return root1

    def get_clusters(self) -> dict[str, list[str]]:
        """Return a mapping of root_id -> list of all item IDs in that cluster."""
        clusters: dict[str, list[str]] = defaultdict(list)
        for item in list(self.parent.keys()):
            root = self.find(item)
            clusters[root].append(item)
        return dict(clusters)

