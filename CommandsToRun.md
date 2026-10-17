# Git Bash Run Commands: Self-Correcting Text-to-SQL Engine

An end-to-end guide to running and testing every functionality of the project from scratch using **Git Bash** and `curl`.

---

## Step 0: Initial Setup & Starting the Services

Run these commands in Git Bash to initialize the environment, build containers, and spin up PostgreSQL and the FastAPI application.

```bash
# 1. Copy the environment configuration template
cp .env.example .env

# 2. Build and launch PostgreSQL and the API container in the background
docker compose up --build -d

# 3. Wait a few seconds for PostgreSQL to seed data and API to be ready
sleep 5
```

---

## Step 1: Health Check & API Spec Discovery

Verify that the API server is healthy and discover the OpenAPI specification.

### 1.1 Health Check (`GET /health`)
Verifies that the FastAPI server is running.
```bash
curl -s -X GET http://localhost:8000/health
```
**Expected Output:**
```json
{"status":"ok"}
```

### 1.2 View OpenAPI Spec (`GET /openapi.json`)
Verifies the API contract is exposed and functional.
```bash
curl -s -X GET http://localhost:8000/openapi.json
```
*(Interactive Swagger documentation is also available at http://localhost:8000/docs).*

---

## Step 2: Basic Filtered Query (Single Table + WHERE Filter)

Test natural language translation to SQL with column filtering.

```bash
curl -s -X POST http://localhost:8000/api/query \
  -H "Content-Type: application/json" \
  -d '{"question":"Show me all customers in New York"}'
```

**What this tests:**
- Converts the question to `SELECT customer_id, name, region FROM customers WHERE region = 'New York' ORDER BY customer_id`.
- sqlglot guardrail ensures only read-only `SELECT` queries pass.
- Returns matching rows with `iterations: 1`, `status: "success"`, and an empty `repair_history: []`.

---

## Step 3: Aggregation & Financial Metric Query

Test generating an aggregation (`SUM`) with status filters.

```bash
curl -s -X POST http://localhost:8000/api/query \
  -H "Content-Type: application/json" \
  -d '{"question":"What is total revenue?"}'
```

**What this tests:**
- Generates `SELECT SUM(total_amount) AS total_revenue FROM orders WHERE status = 'completed'`.
- Runs semantic sanity check: ensures aggregation did not return a null value.
- Returns aggregated metrics from the 600 seeded orders.

---

## Step 4: Multi-Table Relational Join Across Messy Schema

The seeded schema intentionally uses `customers.customer_id` vs `orders.cust_id` to simulate real-world naming mismatches.

```bash
curl -s -X POST http://localhost:8000/api/query \
  -H "Content-Type: application/json" \
  -d '{"question":"Show customer names and orders"}'
```

**What this tests:**
- Joins `customers c` with `orders o` using `o.cust_id = c.customer_id`.
- Validates the AST table relationships and column mappings against PostgreSQL catalog metadata.

---

## Step 5: Entity List & Limit Checks

Fetch line items to test multi-record pagination and limits.

```bash
curl -s -X POST http://localhost:8000/api/query \
  -H "Content-Type: application/json" \
  -d '{"question":"List line items"}'
```

**What this tests:**
- Executes `SELECT li.id, li.product_name, li.qty, li.unit_price FROM line_items li ORDER BY li.id LIMIT 100`.
- Runs semantic threshold verification (`SEMANTIC_ROW_THRESHOLD=1000`) to confirm no unconstrained Cartesian product.

---

## Step 6: Input Validation & Boundary Guardrails

Test request validation and error handling behavior.

### 6.1 Empty Request Body (FastAPI / Pydantic validation)
```bash
curl -s -i -X POST http://localhost:8000/api/query \
  -H "Content-Type: application/json" \
  -d '{"question":""}'
```
**Expected Output:**
`HTTP/1.1 422 Unprocessable Entity` (enforces `min_length=1` constraint).

### 6.2 Malformed JSON
```bash
curl -s -i -X POST http://localhost:8000/api/query \
  -H "Content-Type: application/json" \
  -d 'invalid-json'
```
**Expected Output:**
`HTTP/1.1 422 Unprocessable Entity`.

---

## Step 7: Self-Correction & Repair History (OpenAI Provider Mode)

The engine features a 3-attempt bounded feedback loop:
1. **Syntax / Safety Repair**: sqlglot catches syntax errors or forbidden statements (e.g. `DROP`, `UPDATE`, multi-statements), recording `failure_type: "syntax"`.
2. **Schema Repair**: PostgreSQL catalog errors (e.g., column `orders.customer_id` instead of `orders.cust_id`), recording `failure_type: "schema"`.
3. **Semantic Repair**: Heuristic checks (e.g., Cartesian product `> 1000` rows, aggregation returning `NULL`, or empty results for entity queries), recording `failure_type: "semantic"`.

To enable live LLM repair with OpenAI:
```bash
# In your .env file:
# LLM_PROVIDER=openai
# OPENAI_API_KEY=sk-...

# Then restart the API service:
docker compose restart api
```

When an attempt fails and repairs, the response structure returned to `curl` will look like:
```json
{
  "status": "success",
  "final_sql": "SELECT ...",
  "results": [...],
  "iterations": 2,
  "repair_history": [
    {
      "attempt": 1,
      "failure_type": "syntax",
      "error_message": "Security Guardrail Violation: Only SELECT statements are permitted."
    }
  ]
}
```

---

## Step 8: Run the 30-Case Benchmark Evaluation

Execute the automated benchmark across all 3 modes:
1. **Zero-shot** (no repair)
2. **Syntax + Schema Repair only**
3. **Full Pipeline** (Syntax + Schema + Semantic Sanity Checks)

```bash
docker compose exec api python scripts/evaluate.py
```

**What this outputs:**
- Generates `results/evaluation_metrics.json`.
- Displays `execution_accuracy`, `average_iterations`, and `failure_class_breakdown` for each pipeline mode.

---

## Step 9: Run the Unit & Guardrail Test Suite

Run pytest inside the container to test AST safety rules, heuristics, and state machine transitions:

```bash
docker compose exec api pytest -v
```

**What this validates:**
- `test_guardrails.py`: SQL normalization, injection blocking, and prohibition of destructive DDL/DML.
- `test_heuristics.py`: Detection of Cartesian products, empty results, and valid existential questions.
- `test_agent.py`: Typed repair history recording and the hard 3-iteration cap.

---

## Step 10: Teardown & Clean Up

When finished testing, shut down the containers and clean up volumes:

```bash
docker compose down -v
```
