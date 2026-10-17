"""Deterministic checks for technically valid but suspicious query results."""
from typing import Any


def evaluate_semantic_sanity(sql: str, results: list[dict[str, Any]], question: str, row_threshold: int = 1000) -> dict:
    if len(results) > row_threshold:
        return {"is_suspicious": True, "reason": "Result set is unusually large. Check for missing JOIN conditions (Cartesian product)."}
    normalized_question = question.lower()
    entity_words = ("which", "who", "list", "show", "give me", "find")
    legitimate_empty = normalized_question.startswith(("are there any", "is there any", "do any"))
    if not results and any(word in normalized_question for word in entity_words) and not legitimate_empty:
        return {"is_suspicious": True, "reason": "Query returned 0 rows, but the question implies entities exist. Check WHERE clause filters."}
    aggregate_words = ("sum(", "avg(", "min(", "max(", "count(")
    if len(results) == 1 and any(word in sql.lower() for word in aggregate_words):
        values = list(results[0].values())
        if values and all(value is None for value in values):
            return {"is_suspicious": True, "reason": "Aggregation returned a single NULL value. Check filters and aggregation inputs."}
    return {"is_suspicious": False, "reason": None}
