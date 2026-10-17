# Self-Correcting Text-to-SQL Engine: Project Architecture & Summary

An in-depth guide detailing what this project does, its core purpose, how each functionality is implemented, and how each technology in the stack contributes to the system.

---

## 1. What This Project Does & Its Purpose

### The Problem
When using Large Language Models (LLMs) to generate SQL from natural language (Text-to-SQL):
- **Schema Hallucinations**: LLMs frequently invent columns or tables that do not exist or assume standard naming conventions (e.g. `orders.customer_id` when the actual schema uses `orders.cust_id`).
- **Security Vulnerabilities**: Naive execution of LLM-generated code exposes databases to destructive statements (`DROP TABLE`, `UPDATE`, `DELETE`, `TRUNCATE`) or stacked query injection (`SELECT 1; DROP ...`).
- **Logical & Semantic Errors**: Queries might parse and execute cleanly without errors in PostgreSQL, but return completely wrong data—such as accidental Cartesian products causing thousands of duplicate rows, or over-filtered queries returning zero rows when entities were expected.
- **Fragile Retry Loops**: Many systems either fail immediately on the first error or enter unbounded, expensive retry loops without providing targeted feedback to the LLM.

### The Purpose
This project implements an **inspectable, self-correcting PostgreSQL analytics agent**. It enforces a **bounded 3-iteration state machine** that validates generated SQL across three independent layers before trusting the query and returning data:

```
Natural Language Question 
       │
       ▼
 [LLM Generation]
       │
       ▼
 [Layer 1: AST Guardrail (sqlglot)]  ──(Fail: syntax/unsafe)──► [Syntax Repair Prompt] ──┐
       │ (Pass)                                                                          │
       ▼                                                                                 │
 [Layer 2: PostgreSQL Execution]     ──(Fail: catalog error)──► [Schema Repair Prompt]  ──┤ (Max 3
       │ (Pass)                                                  + Live Catalog Context  │  attempts)
       ▼                                                                                 │
 [Layer 3: Semantic Sanity Check]    ──(Fail: suspicious)  ───► [Semantic Repair Prompt] ─┘
       │ (Pass)                                                  + Sample Rows
       ▼
 Final SQL & Verified Result Rows
```

---

## 2. How Each Functionality Is Implemented

### 1. Dual-Mode SQL Generation
- **Source Code**: [src/agent.py](file:///home/shamshu/GPPV/Self-Correcting-Text-to-SQL-Engine-with-sqlglot-and-Execution-Feedback/src/agent.py) & [src/prompts.py](file:///home/shamshu/GPPV/Self-Correcting-Text-to-SQL-Engine-with-sqlglot-and-Execution-Feedback/src/prompts.py)
- **Implementation**:
  - Implements a flexible `SQLGenerator` Protocol with two backends:
    - `DeterministicGenerator`: Runs locally with zero API keys or external costs. Used for local development, fast evaluations, and CI/CD pipelines.
    - `OpenAIGenerator`: Invokes OpenAI's API (default: `gpt-4o-mini`, temperature 0) with strict system prompt instructions forbidding markdown, prose, or destructive statements.

---

### 2. AST-Level Safety Guardrails
- **Source Code**: [src/guardrails.py](file:///home/shamshu/GPPV/Self-Correcting-Text-to-SQL-Engine-with-sqlglot-and-Execution-Feedback/src/guardrails.py)
- **Implementation**:
  - `validate_and_guard_sql(sql_string)` unwraps any markdown wrappers (```sql ... ```) and parses the raw text into an Abstract Syntax Tree using `sqlglot.parse(raw, read="postgres")`.
  - **Single Statement Enforcement**: Ensures `len(statements) == 1`, preventing stacked queries (e.g., `SELECT 1; DROP TABLE customers`).
  - **SELECT-Only Root**: Verifies the top-level AST node is an instance of `sqlglot.exp.Select` (which also covers SELECT-backed Common Table Expressions / CTEs with `WITH`).
  - **Forbidden Node Detection**: Traverses the AST to detect and reject disallowed operations:
    - `exp.Insert`, `exp.Update`, `exp.Delete`, `exp.Drop`, `exp.Alter`, `exp.Create`
    - `exp.Into` (handles PostgreSQL's `SELECT ... INTO`, which writes tables despite starting with `SELECT`)
    - `exp.Truncate` / `exp.TruncateTable`
  - Returns a dictionary `{"is_valid": bool, "sql": str, "error": str | None}`.

---

### 3. Database Execution & Dynamic Catalog Reflection
- **Source Code**: [src/db.py](file:///home/shamshu/GPPV/Self-Correcting-Text-to-SQL-Engine-with-sqlglot-and-Execution-Feedback/src/db.py)
- **Implementation**:
  - Wraps database connections via `psycopg2` using `RealDictCursor` for dictionary output.
  - **Dynamic Catalog Reflection**: The `catalog()` method queries PostgreSQL's `information_schema.columns` to construct a real-time schema summary of all public tables, column names, data types, and nullability:
    ```sql
    SELECT table_name, column_name, data_type, is_nullable 
    FROM information_schema.columns 
    WHERE table_schema = 'public' 
    ORDER BY table_name, ordinal_position
    ```
  - **Schema Error Classification**: Detects PostgreSQL exceptions (`UndefinedColumn`, `UndefinedTable`, or `pgcode` in `{"42703", "42P01"}`) to classify the failure specifically as a `schema` error.

---

### 4. Semantic Sanity Checks (Heuristics)
- **Source Code**: [src/heuristics.py](file:///home/shamshu/GPPV/Self-Correcting-Text-to-SQL-Engine-with-sqlglot-and-Execution-Feedback/src/heuristics.py)
- **Implementation**:
  - `evaluate_semantic_sanity(sql, results, question, row_threshold=1000)` checks for technically valid SQL queries that produce logically suspicious results:
    1. **Cartesian Product Detection**: If the row count exceeds `SEMANTIC_ROW_THRESHOLD` (1,000 rows), flags the query for possible missing `JOIN` conditions.
    2. **Silent Zero-Row Check**: If the question contains entity words (*"which"*, *"who"*, *"list"*, *"show"*, *"give me"*, *"find"*) but returns 0 rows, it is flagged as suspicious (unless the question specifically began as an existence check like *"are there any..."*).
    3. **NULL Aggregations**: If an aggregation query (`SUM`, `AVG`, `MIN`, `MAX`, `COUNT`) returns a single row where all values are `None`/`NULL`, it is flagged for check.

---

### 5. Typed Self-Correction Loop & Auditable State Machine
- **Source Code**: [src/agent.py](file:///home/shamshu/GPPV/Self-Correcting-Text-to-SQL-Engine-with-sqlglot-and-Execution-Feedback/src/agent.py)
- **Implementation**:
  - The `TextToSQLAgent.query` method runs a bounded loop up to `max_attempts` (default: 3).
  - Every rejected iteration records `{ "attempt": int, "failure_type": "syntax" | "schema" | "semantic", "error_message": str }` in `repair_history`.
  - Rather than sending a generic error back to the LLM, it builds a targeted prompt:
    - **Syntax Repair Prompt**: Contains question, previous SQL, and the exact parser/guardrail diagnostic.
    - **Schema Repair Prompt**: Contains question, failed SQL, PostgreSQL error, and the full dynamic schema catalog from `db.catalog()`.
    - **Semantic Repair Prompt**: Contains question, SQL, suspicion reason, and sample rows returned.
  - Returns a structured `QueryResponse` containing `status`, `final_sql`, `results`, `iterations`, and `repair_history`.

---

### 6. REST API & Operational Boundary
- **Source Code**: [api/main.py](file:///home/shamshu/GPPV/Self-Correcting-Text-to-SQL-Engine-with-sqlglot-and-Execution-Feedback/api/main.py)
- **Implementation**:
  - Exposes `GET /health` for automated container and load balancer health checks.
  - Exposes `POST /api/query` accepting `{ "question": str }` with length limits (1 to 4,000 characters).
  - **Status Code Strategy**:
    - Returns **HTTP 200** for all completed query runs (even if all 3 attempts failed), because a rejected query is an audited, finished pipeline outcome.
    - Raises **HTTP 503** only when database or provider infrastructure is down.
    - Returns **HTTP 422** for invalid payloads or empty strings.

---

### 7. Automated 30-Case Benchmark Suite
- **Source Code**: [scripts/evaluate.py](file:///home/shamshu/GPPV/Self-Correcting-Text-to-SQL-Engine-with-sqlglot-and-Execution-Feedback/scripts/evaluate.py) & [data/eval_set.json](file:///home/shamshu/GPPV/Self-Correcting-Text-to-SQL-Engine-with-sqlglot-and-Execution-Feedback/data/eval_set.json)
- **Implementation**:
  - Evaluates 30 diverse natural language queries against gold-standard SQL.
  - Compares query output order-independently using canonical sorted tuples.
  - Tests three distinct configurations:
    1. `zero_shot`: Repair disabled, semantic checks disabled.
    2. `syntax_schema_repair_only`: Repair enabled, semantic checks disabled.
    3. `full_pipeline`: Both repair and semantic checks enabled.
  - Calculates and writes `execution_accuracy`, `average_iterations`, and `failure_class_breakdown` to `results/evaluation_metrics.json`.

---

### 8. Deliberately Messy E-Commerce Seed Schema
- **Source Code**: [scripts/seed_db.sql](file:///home/shamshu/GPPV/Self-Correcting-Text-to-SQL-Engine-with-sqlglot-and-Execution-Feedback/scripts/seed_db.sql)
- **Implementation**:
  - Seeds 120 customers, 600 orders, and 1,800 line items via PostgreSQL `generate_series`.
  - Introduces intentional real-world schema traps:
    - Column mismatch: `customers.customer_id` vs `orders.cust_id`.
    - Nullable data: `customers.region` permits `NULL`.
    - Duplicate financial indicators: `orders.total_amount` vs line-item pricing (`qty * unit_price`).

---

## 3. Technology Stack & Role of Each Tool

```
 ┌─────────────────────────────────────────────────────────────┐
 │                         FastAPI                             │
 │       (REST API layer, Pydantic validation, OpenAPI docs)    │
 └──────────────────────────────┬──────────────────────────────┘
                                │
 ┌──────────────────────────────▼──────────────────────────────┐
 │                    sqlglot AST Engine                       │
 │  (Lexer/Parser, single SELECT guardrail, DDL/DML blocking)  │
 └──────────────────────────────┬──────────────────────────────┘
                                │
 ┌──────────────────────────────▼──────────────────────────────┐
 │                     psycopg2-binary                         │
 │     (PostgreSQL connection, real-time catalog reflection)   │
 └──────────────────────────────┬──────────────────────────────┘
                                │
 ┌──────────────────────────────▼──────────────────────────────┐
 │                      PostgreSQL 16                          │
 │         (Relational store, index lookups, transactions)     │
 └─────────────────────────────────────────────────────────────┘
 [Orchestration: Docker Compose | Testing: Pytest | AI: OpenAI API]
```

### 1. sqlglot
- **Why it is used**: Regex or string pattern matching (e.g. checking if the word `"DROP"` is in the query) is brittle and easily bypassed via SQL comments, table aliases, or string literals.
- **How it helps**: `sqlglot` parses PostgreSQL queries into a full Abstract Syntax Tree (AST). It enables precise semantic inspection to verify that exactly one statement exists and that it is strictly a read-only `SELECT` statement before any execution occurs.

### 2. FastAPI & Pydantic
- **Why it is used**: High-performance, modern Python web framework with asynchronous support and data validation.
- **How it helps**: Automatically validates incoming JSON request schemas, handles request bounds (`min_length`, `max_length`), maps exceptions to HTTP standards, and automatically generates interactive Swagger UI documentation at `/docs`.

### 3. PostgreSQL 16
- **Why it is used**: Robust, production-grade relational database engine.
- **How it helps**: Provides ACID transaction guarantees, rich date/numeric functions, indexing, and the standard `information_schema` tables necessary for dynamic schema reflection.

### 4. psycopg2-binary
- **Why it is used**: The battle-tested PostgreSQL adapter for Python.
- **How it helps**: Connects the API agent to the database, formats rows as dictionaries using `RealDictCursor`, and provides granular error codes (e.g. `pgcode` `42703` for undefined column, `42P01` for undefined table) to enable typed repair classification.

### 5. Docker & Docker Compose
- **Why it is used**: Containerization and multi-container orchestration.
- **How it helps**: Eliminates "works on my machine" issues by packaging PostgreSQL and the Python API together. Automatically runs the database seeding script upon container initialization via `/docker-entrypoint-initdb.d/` and configures inter-service health checks.

### 6. Pytest
- **Why it is used**: Python unit and integration testing framework.
- **How it helps**: Provides fast, deterministic tests for guardrails, heuristic rules, and agent retry limits without requiring live database connections or OpenAI API keys.
