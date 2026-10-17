from src.guardrails import validate_and_guard_sql

def test_select_is_normalized_and_accepted():
    outcome = validate_and_guard_sql("```sql\nselect * from customers;\n```")
    assert outcome["is_valid"] is True
    assert outcome["sql"].upper().startswith("SELECT")

def test_destructive_statement_is_rejected():
    outcome = validate_and_guard_sql("DROP TABLE customers")
    assert outcome["is_valid"] is False
    assert "Guardrail" in outcome["error"]

def test_multiple_statements_are_rejected():
    assert validate_and_guard_sql("SELECT 1; DELETE FROM customers")["is_valid"] is False
