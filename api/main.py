from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from src.agent import TextToSQLAgent

app = FastAPI(title="Self-Correcting Text-to-SQL Engine", version="1.0.0")

class QueryRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/api/query")
def query(request: QueryRequest):
    try:
        return TextToSQLAgent().query(request.question).as_dict()
    except Exception as exc:
        # Infrastructure failures use a 503, distinct from a completed three-attempt failure.
        raise HTTPException(status_code=503, detail=f"Database or provider unavailable: {exc}") from exc
