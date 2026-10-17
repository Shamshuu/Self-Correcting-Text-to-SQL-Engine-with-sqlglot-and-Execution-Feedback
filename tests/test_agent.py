from src.agent import TextToSQLAgent

class SequenceGenerator:
    def __init__(self, statements): self.statements = iter(statements)
    def generate(self, prompt): return next(self.statements)

class FakeDB:
    def execute(self, sql): return [{"customer_id": 1, "name": "Customer 1"}]
    def catalog(self): return "customers(customer_id integer, name text)"

def test_unsafe_sql_records_typed_syntax_then_repairs():
    agent = TextToSQLAgent(FakeDB(), SequenceGenerator(["DROP TABLE customers", "SELECT customer_id, name FROM customers"]), max_attempts=3)
    response = agent.query("Show customers")
    assert response.status == "success"
    assert response.iterations == 2
    assert response.repair_history[0]["failure_type"] == "syntax"

def test_bound_is_exactly_three_attempts():
    agent = TextToSQLAgent(FakeDB(), SequenceGenerator(["DELETE FROM customers"] * 3), max_attempts=3)
    response = agent.query("impossible request")
    assert response.status == "failed"
    assert response.iterations == 3
