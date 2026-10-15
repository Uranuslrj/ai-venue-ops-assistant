from __future__ import annotations
import json
from pathlib import Path
from retrieval import evaluate_cases

ROOT = Path(__file__).resolve().parent
result = evaluate_cases(ROOT / "evaluation_cases.json")
print(json.dumps(result, ensure_ascii=False, indent=2))
raise SystemExit(0 if result["failed"] == 0 else 1)