"""Optional DashScope/OpenAI-compatible embeddings for hybrid retrieval.

Secrets are read only from environment variables and never persisted:
DASHSCOPE_API_KEY, DASHSCOPE_BASE_URL, DASHSCOPE_EMBEDDING_MODEL,
DASHSCOPE_EMBEDDING_DIMENSION.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CACHE_FILE = ROOT / "embedding_cache.json"
DEFAULT_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
DEFAULT_MODEL = "text-embedding-v4"
DEFAULT_DIMENSION = 1024


def _config() -> dict[str, object]:
    return {
        "api_key": os.getenv("DASHSCOPE_API_KEY", "").strip(),
        "base_url": os.getenv("DASHSCOPE_BASE_URL", DEFAULT_BASE_URL).rstrip("/"),
        "model": os.getenv("DASHSCOPE_EMBEDDING_MODEL", DEFAULT_MODEL),
        "dimension": int(os.getenv("DASHSCOPE_EMBEDDING_DIMENSION", str(DEFAULT_DIMENSION))),
    }


def configured() -> bool:
    cfg = _config()
    return bool(cfg["api_key"] and cfg["base_url"] and cfg["model"])


def _key(model: str, text: str, dimension: int) -> str:
    return hashlib.sha256(f"{model}\0{dimension}\0{text}".encode("utf-8")).hexdigest()


def _load_cache() -> dict[str, list[float]]:
    if not CACHE_FILE.exists():
        return {}
    try:
        data = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _save_cache(cache: dict[str, list[float]]) -> None:
    CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")


def _request(texts: list[str]) -> list[list[float]]:
    """Embed texts in batches because DashScope caps inputs per call."""
    cfg = _config()
    batch_size = int(os.getenv("DASHSCOPE_EMBEDDING_BATCH", "10"))
    vectors: list[list[float]] = []
    for offset in range(0, len(texts), batch_size):
        chunk = texts[offset:offset + batch_size]
        payload: dict[str, object] = {"model": cfg["model"], "input": chunk}
        if cfg["dimension"]:
            payload["dimensions"] = cfg["dimension"]
        request = urllib.request.Request(
            f"{cfg['base_url']}/embeddings",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Authorization": f"Bearer {cfg['api_key']}", "Content-Type": "application/json"},
            method="POST",
        )
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                with urllib.request.urlopen(request, timeout=30) as response:
                    data = json.loads(response.read().decode("utf-8"))
                break
            except urllib.error.HTTPError as exc:
                last_error = exc
                detail = exc.read().decode("utf-8", "ignore")[:200]
                if exc.code in (400, 401, 403):
                    raise RuntimeError(f"Embedding HTTP {exc.code}: {detail}") from exc
                time.sleep(1.5 * (attempt + 1))
            except Exception as exc:
                last_error = exc
                time.sleep(1.5 * (attempt + 1))
        else:
            raise RuntimeError(f"Embedding request failed: {type(last_error).__name__}")
        rows = sorted(data.get("data", []), key=lambda row: row.get("index", 0))
        batch_vectors = [row.get("embedding", []) for row in rows]
        if len(batch_vectors) != len(chunk) or not all(batch_vectors):
            raise RuntimeError("Embedding接口返回数量或向量为空")
        vectors.extend([[float(x) for x in vector] for vector in batch_vectors])
    return vectors


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def hybrid_scores(query: str, documents: list[dict[str, object]], bm25_weight: float = 0.6, embedding_weight: float = 0.4) -> tuple[dict[int, float] | None, str]:
    """Return normalized semantic scores by document index, or None when unavailable.

    Failing closed to BM25 keeps local demos and tests usable without credentials.
    """
    if not configured():
        return None, "bm25_only:not_configured"
    try:
        cfg = _config()
        texts = [query] + [str(doc.get("content", "")) for doc in documents]
        cache = _load_cache()
        keys = [_key(str(cfg["model"]), text, int(cfg["dimension"])) for text in texts]
        missing = [text for text, key in zip(texts, keys) if key not in cache]
        if missing:
            vectors = _request(missing)
            for key, vector in zip((key for key in keys if key not in cache), vectors):
                cache[key] = vector
            _save_cache(cache)
        query_vector = cache[keys[0]]
        semantic = {_idx: (max(-1.0, min(1.0, _cosine(query_vector, cache[key]))) + 1.0) / 2.0 for _idx, key in enumerate(keys[1:])}
        return semantic, f"hybrid:bm25={bm25_weight:.2f},embedding={embedding_weight:.2f},model={cfg['model']}"
    except Exception as exc:
        return None, f"bm25_only:embedding_error:{type(exc).__name__}"
