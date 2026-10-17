"""Run reproducible execution-accuracy evaluation against the three required modes."""
from __future__ import annotations
import json, sys
from collections import Counter
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.agent import TextToSQLAgent
from src.db import Database

ROOT = Path(__file__).resolve().parents[1]

def canonical(rows):
    return sorted([tuple(sorted(row.items())) for row in rows])

def run_mode(name, repair_enabled, semantic_checks, cases, db):
    successes, iterations, failure_classes = 0, [], Counter()
    for case in cases:
        response = TextToSQLAgent(db=db).query(case["question"], repair_enabled=repair_enabled, semantic_checks=semantic_checks)
        gold = db.execute(case["gold_sql"])
        correct = response.status == "success" and canonical(response.results) == canonical(gold)
        successes += int(correct)
        iterations.append(response.iterations)
        failure_classes.update(item["failure_type"] for item in response.repair_history)
    return {"execution_accuracy": round(successes / len(cases), 4), "average_iterations": round(sum(iterations) / len(iterations), 3), "failure_class_breakdown": dict(failure_classes), "cases": len(cases)}

def main():
    cases = json.loads((ROOT / "data/eval_set.json").read_text())
    db = Database()
    report = {"dataset_cases": len(cases), "modes": {
        "zero_shot": run_mode("zero_shot", False, False, cases, db),
        "syntax_schema_repair_only": run_mode("repair", True, False, cases, db),
        "full_pipeline": run_mode("full", True, True, cases, db)}}
    out = ROOT / "results/evaluation_metrics.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))

if __name__ == "__main__": main()
