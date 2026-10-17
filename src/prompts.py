SYSTEM_PROMPT = "Respond ONLY with one valid PostgreSQL SELECT query. No markdown, prose, or destructive statements."

def syntax_repair_prompt(question, sql, error, history):
    return f"{SYSTEM_PROMPT}\nRepair a PostgreSQL syntax or safety failure. Question: {question}\nSQL: {sql}\nParser diagnostic: {error}\nPrior attempts: {history}"

def schema_repair_prompt(question, sql, error, catalog, history):
    return f"{SYSTEM_PROMPT}\nRepair a schema failure. Question: {question}\nSQL: {sql}\nDatabase error: {error}\nActual catalog:\n{catalog}\nPrior attempts: {history}"

def semantic_repair_prompt(question, sql, reason, sample_rows, history):
    return f"{SYSTEM_PROMPT}\nRepair a semantically suspicious query. Question: {question}\nSQL: {sql}\nSuspicion: {reason}\nSample rows: {sample_rows}\nPrior attempts: {history}"
