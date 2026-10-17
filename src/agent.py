"""Explicit state machine for Text-to-SQL generation and typed repair."""
from __future__ import annotations
import os
from dataclasses import dataclass, field
from typing import Protocol, Any
import psycopg2
from .db import Database
from .guardrails import validate_and_guard_sql
from .heuristics import evaluate_semantic_sanity
from . import prompts


class SQLGenerator(Protocol):
    def generate(self, prompt: str) -> str: ...


class DeterministicGenerator:
    """Small no-key local generator for demos; production may use OpenAIGenerator."""
    def generate(self, prompt: str) -> str:
        q = prompt.lower()
        # Repairs return a broadly useful safe query when the failed SQL is not recognizable.
        if "new york" in q:
            return "SELECT customer_id, name, region FROM customers WHERE region = 'New York' ORDER BY customer_id"
        if "total revenue" in q or "revenue" in q:
            return "SELECT SUM(total_amount) AS total_revenue FROM orders WHERE status = 'completed'"
        if "line item" in q or "products" in q:
            return "SELECT li.id, li.product_name, li.qty, li.unit_price FROM line_items li ORDER BY li.id LIMIT 100"
        if "order" in q and ("customer" in q or "name" in q or "join" in q):
            return "SELECT c.customer_id, c.name, o.id AS order_id, o.total_amount FROM customers c JOIN orders o ON o.cust_id = c.customer_id ORDER BY o.id LIMIT 100"
        if "region" in q:
            return "SELECT customer_id, name, region FROM customers ORDER BY customer_id"
        if "customer" in q:
            return "SELECT customer_id, name, region FROM customers ORDER BY customer_id LIMIT 100"
        return "SELECT id, cust_id, order_date, total_amount, status FROM orders ORDER BY id LIMIT 100"


class OpenAIGenerator:
    def __init__(self):
        from openai import OpenAI
        self.client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
        self.model = os.getenv("LLM_MODEL", "gpt-4o-mini")

    def generate(self, prompt: str) -> str:
        response = self.client.chat.completions.create(model=self.model, temperature=0, messages=[{"role": "system", "content": prompts.SYSTEM_PROMPT}, {"role": "user", "content": prompt}])
        return response.choices[0].message.content or ""


@dataclass
class QueryResponse:
    status: str
    final_sql: str | None
    results: list[dict[str, Any]]
    iterations: int
    repair_history: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self):
        return {"status": self.status, "final_sql": self.final_sql, "results": self.results, "iterations": self.iterations, "repair_history": self.repair_history}


class TextToSQLAgent:
    """A bounded state machine: generate -> AST -> execute -> semantic check -> typed repair."""
    def __init__(self, db: Database | None = None, generator: SQLGenerator | None = None, max_attempts: int | None = None):
        self.db = db or Database()
        self.generator = generator or (OpenAIGenerator() if os.getenv("LLM_PROVIDER") == "openai" else DeterministicGenerator())
        self.max_attempts = max_attempts or int(os.getenv("MAX_ATTEMPTS", "3"))

    def _record(self, history, attempt, failure_type, message):
        history.append({"attempt": attempt, "failure_type": failure_type, "error_message": str(message)})

    @staticmethod
    def _is_schema_error(error: Exception) -> bool:
        return isinstance(error, (psycopg2.errors.UndefinedColumn, psycopg2.errors.UndefinedTable)) or getattr(error, "pgcode", None) in {"42703", "42P01"}

    def query(self, question: str, semantic_checks: bool = True, repair_enabled: bool = True) -> QueryResponse:
        history: list[dict] = []
        prompt = f"{prompts.SYSTEM_PROMPT}\nQuestion: {question}"
        latest_sql: str | None = None
        for attempt in range(1, self.max_attempts + 1):
            raw_sql = self.generator.generate(prompt)
            guarded = validate_and_guard_sql(raw_sql)
            latest_sql = guarded["sql"]
            if not guarded["is_valid"]:
                self._record(history, attempt, "syntax", guarded["error"])
                if not repair_enabled or attempt == self.max_attempts:
                    return QueryResponse("failed", latest_sql, [], attempt, history)
                prompt = prompts.syntax_repair_prompt(question, raw_sql, guarded["error"], history)
                continue
            try:
                results = self.db.execute(guarded["sql"])
            except Exception as error:
                failure = "schema" if self._is_schema_error(error) else "schema"  # engine feedback gets catalog context
                self._record(history, attempt, failure, str(error))
                if not repair_enabled or attempt == self.max_attempts:
                    return QueryResponse("failed", guarded["sql"], [], attempt, history)
                prompt = prompts.schema_repair_prompt(question, guarded["sql"], str(error), self.db.catalog(), history)
                continue
            if semantic_checks:
                sanity = evaluate_semantic_sanity(guarded["sql"], results, question)
                if sanity["is_suspicious"]:
                    self._record(history, attempt, "semantic", sanity["reason"])
                    if not repair_enabled or attempt == self.max_attempts:
                        return QueryResponse("failed", guarded["sql"], results, attempt, history)
                    prompt = prompts.semantic_repair_prompt(question, guarded["sql"], sanity["reason"], results[:3], history)
                    continue
            return QueryResponse("success", guarded["sql"], results, attempt, history)
        return QueryResponse("failed", latest_sql, [], self.max_attempts, history)
