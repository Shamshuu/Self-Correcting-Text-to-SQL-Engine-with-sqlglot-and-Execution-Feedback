from src.heuristics import evaluate_semantic_sanity

def test_cartesian_volume_is_suspicious():
    result = evaluate_semantic_sanity("SELECT * FROM customers, orders", [{"id": i} for i in range(1001)], "Show all matches")
    assert result["is_suspicious"] is True
    assert "Cartesian" in result["reason"]

def test_empty_entity_request_is_suspicious():
    assert evaluate_semantic_sanity("SELECT * FROM customers WHERE 1=0", [], "Who are the customers?")["is_suspicious"]

def test_legitimate_existence_question_may_be_empty():
    assert not evaluate_semantic_sanity("SELECT * FROM customers WHERE 1=0", [], "Are there any customers?")["is_suspicious"]
