"""Offline retrieval evaluation on synthetic Issue #38 labels.

Usage: python3 evaluate.py relevance.json --baseline
       python3 evaluate.py relevance.json --rankings rankings.json

Rankings format: {"queries": [{"text": "...", "card_ids": ["c1", "c2"]}, ...]}.
No provider or database request is made by this script.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

K = 5


def ndcg_at_k(card_ids: list[str], relevance: dict[str, int], k: int = K) -> float:
    """Graded nDCG using gain 2^grade - 1 and log2 rank discount."""

    def dcg(grades: list[int]) -> float:
        return sum(
            (2**grade - 1) / math.log2(rank + 2) for rank, grade in enumerate(grades)
        )

    ideal = dcg(sorted(relevance.values(), reverse=True)[:k])
    return dcg([relevance.get(card_id, 0) for card_id in card_ids[:k]]) / ideal


def strong_recall_at_k(
    card_ids: list[str], relevance: dict[str, int], k: int = K
) -> float:
    strong = {card_id for card_id, grade in relevance.items() if grade == 2}
    return len(strong.intersection(card_ids[:k])) / len(strong)


def lexical_baseline(cards: list[dict], query: str) -> list[str]:
    """Deterministic word-overlap baseline on term and meaning."""
    terms = set(query.casefold().split())
    matches = []
    for card in cards:
        haystack = f"{card['term']} {card['meaning']}".casefold().split()
        overlap = len(terms.intersection(haystack))
        if overlap:
            matches.append((-overlap, card["id"]))
    return [card_id for _, card_id in sorted(matches)]


def evaluate(labels: dict, rankings: dict[str, list[str]]) -> dict:
    cards = labels["cards"]
    queries = labels["queries"]
    known_ids = {card["id"] for card in cards}
    if len(known_ids) != len(cards):
        raise ValueError("duplicate card ID in labels")
    query_texts = [item["text"] for item in queries]
    if len(set(query_texts)) != len(queries) or set(rankings) != set(query_texts):
        raise ValueError("rankings must contain each labeled query exactly once")

    results = []
    for query in queries:
        text = query["text"]
        relevance = query["relevance"]
        if (
            not relevance
            or not set(relevance) <= known_ids
            or any(grade not in (1, 2) for grade in relevance.values())
            or 2 not in relevance.values()
        ):
            raise ValueError("invalid relevance labels")
        card_ids = rankings[text]
        if len(card_ids) != len(set(card_ids)) or not set(card_ids) <= known_ids:
            raise ValueError("rankings contain duplicate or unknown card IDs")
        results.append(
            {
                "query": text,
                "ndcg_at_5": ndcg_at_k(card_ids, relevance),
                "strong_recall_at_5": strong_recall_at_k(card_ids, relevance),
            }
        )
    return {
        "label_version": labels["version"],
        "query_count": len(results),
        "macro_ndcg_at_5": round(
            sum(item["ndcg_at_5"] for item in results) / len(results), 4
        ),
        "macro_strong_recall_at_5": round(
            sum(item["strong_recall_at_5"] for item in results) / len(results), 4
        ),
        "per_query": [
            {
                key: round(value, 4) if isinstance(value, float) else value
                for key, value in row.items()
            }
            for row in results
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("labels", type=Path)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--baseline", action="store_true")
    source.add_argument("--rankings", type=Path)
    args = parser.parse_args()
    labels = json.loads(args.labels.read_text(encoding="utf-8"))
    if args.baseline:
        rankings = {
            item["text"]: lexical_baseline(labels["cards"], item["text"])
            for item in labels["queries"]
        }
    else:
        payload = json.loads(args.rankings.read_text(encoding="utf-8"))
        rows = payload["queries"]
        rankings = {row["text"]: row["card_ids"] for row in rows}
        if len(rankings) != len(rows):
            raise ValueError("duplicate query in rankings")
    print(json.dumps(evaluate(labels, rankings), indent=2, ensure_ascii=True))


if __name__ == "__main__":
    main()
