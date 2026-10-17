"""AST-level, read-only SQL guardrails."""
import re
import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError


def _unwrap_markdown(sql: str) -> str:
    match = re.search(r"```(?:sql)?\s*(.*?)```", sql, flags=re.I | re.S)
    return (match.group(1) if match else sql).strip().rstrip(";").strip()


def validate_and_guard_sql(sql_string: str) -> dict:
    """Parse exactly one PostgreSQL SELECT/SELECT CTE; never execute unsafe SQL."""
    raw = _unwrap_markdown(sql_string or "")
    if not raw:
        return {"is_valid": False, "sql": raw, "error": "Syntax Error: empty SQL."}
    try:
        statements = sqlglot.parse(raw, read="postgres")
        if len(statements) != 1:
            return {"is_valid": False, "sql": raw, "error": "Security Guardrail Violation: exactly one SELECT statement is permitted."}
        ast = statements[0]
        # A WITH expression is represented by Select with a `with_` argument.
        # sqlglot versions name TRUNCATE differently, so resolve optional AST classes
        # dynamically while keeping the allowlist itself intentionally narrow.
        prohibited = tuple(kind for kind in (
            exp.Insert, exp.Update, exp.Delete, exp.Drop, exp.Alter, exp.Create,
            # PostgreSQL SELECT INTO writes a table despite having a Select root.
            getattr(exp, "Into", None), getattr(exp, "Truncate", None), getattr(exp, "TruncateTable", None),
        ) if kind is not None)
        if not isinstance(ast, exp.Select) or any(ast.find(kind) for kind in prohibited):
            return {"is_valid": False, "sql": raw, "error": "Security Guardrail Violation: Only SELECT statements are permitted."}
        return {"is_valid": True, "sql": ast.sql(dialect="postgres"), "error": None}
    except (ParseError, ValueError) as exc:
        return {"is_valid": False, "sql": raw, "error": f"Syntax Error: {exc}"}
