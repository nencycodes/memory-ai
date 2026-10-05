import json
import os
from urllib.error import URLError
from urllib.request import Request, urlopen


OLLAMA_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
GEMMA_MODEL = os.getenv("MEMORY_GEMMA_MODEL", "gemma3:1b")


def _request_json(url, payload=None, timeout=1.0):
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = Request(url, data=body, headers={"Content-Type": "application/json"})
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def gemma_status():
    try:
        tags = _request_json(f"{OLLAMA_URL}/api/tags", timeout=0.5).get("models", [])
    except (OSError, URLError, ValueError):
        return {"available": False, "model": GEMMA_MODEL, "runtime": "ollama", "reasoning": "local embeddings fallback"}

    available = any(model.get("name", "").split(":", 1)[0].lower().startswith("gemma") for model in tags)
    return {
        "available": available,
        "model": next((model.get("name") for model in tags if model.get("name", "").split(":", 1)[0].lower().startswith("gemma")), GEMMA_MODEL),
        "runtime": "ollama",
        "reasoning": "local Gemma query understanding" if available else "local embeddings fallback",
    }


def expand_query(query):
    status = gemma_status()
    if not status["available"]:
        return query, status

    prompt = (
        "Rewrite this search as a compact list of likely concepts and useful synonyms. "
        "Return only the list, no commentary. The query may be vague.\nQuery: " + query[:500]
    )
    try:
        result = _request_json(
            f"{OLLAMA_URL}/api/generate",
            {"model": status["model"], "prompt": prompt, "stream": False, "options": {"temperature": 0, "num_predict": 80}},
            timeout=8.0,
        )
        expansion = str(result.get("response", "")).strip()
        return (f"{query}\n{expansion}" if expansion else query), status
    except (OSError, URLError, ValueError, TimeoutError):
        return query, {**status, "reasoning": "local embeddings fallback (Gemma request failed)"}