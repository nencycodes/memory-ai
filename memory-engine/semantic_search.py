import json
import os
import re
import uuid
from datetime import datetime, timezone

import numpy as np
from sentence_transformers import SentenceTransformer
from gemma_reasoning import expand_query

INDEX_FILE = os.path.join(os.path.dirname(__file__), "memory_index.json")
STOP_WORDS = {
    "a", "about", "an", "and", "as", "at", "by", "do", "find", "for",
    "from", "i", "in", "is", "it", "of", "on", "or", "saw", "that",
    "the", "this", "thing", "to", "was", "were", "what", "where", "with",
    "you", "saved", "showing", "screenshot", "image", "picture", "photo",
    "containing", "mentioned", "using", "involving"
}

print("Loading local AI model...")
model = SentenceTransformer("all-MiniLM-L6-v2")
print("Local AI model ready!")


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def normalize_text(text):
    return " ".join(re.sub(r"\s+", " ", str(text or "")).split()).strip()


def tokenize(text):
    return {
        token for token in re.findall(r"[a-z0-9]+", normalize_text(text).lower())
        if token not in STOP_WORDS
    }


def infer_source_type(file_path=None, extension=None, source_type=None):
    if source_type:
        return source_type
    if extension:
        mapping = {
            ".pdf": "pdf",
            ".docx": "docx",
            ".txt": "txt",
            ".md": "md",
            ".csv": "csv",
            ".png": "image",
            ".jpg": "image",
            ".jpeg": "image",
            ".webp": "image"
        }
        return mapping.get(extension.lower(), "file")
    if file_path:
        lower_path = str(file_path).lower()
        if lower_path.endswith(".pdf"):
            return "pdf"
        if lower_path.endswith(".docx"):
            return "docx"
        if lower_path.endswith(".txt"):
            return "txt"
        if lower_path.endswith(".md"):
            return "md"
        if lower_path.endswith(".csv"):
            return "csv"
    return "file"


def make_summary(title, text, source_type="file"):
    cleaned = normalize_text(text)
    if not cleaned:
        return f"{source_type.replace('_',' ').title()} memory saved."

    sentences = re.split(r"(?<=[.!?])\s+|\n+", cleaned)
    candidate = ""
    for sentence in sentences:
        if len(sentence) > 20:
            candidate = sentence
            break

    if not candidate:
        candidate = cleaned[:220]

    if title and title.lower() not in candidate.lower():
        candidate = f"{title}: {candidate}"

    return candidate[:220]


def embed_text(text):
    if not text or not text.strip():
        return np.zeros(384, dtype=np.float32).tolist()
    vector = model.encode(text[:12000], convert_to_numpy=True)
    return np.asarray(vector, dtype=np.float32).tolist()


def load_index(index_path=INDEX_FILE):
    if not os.path.exists(index_path):
        return []

    try:
        with open(index_path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def save_index(index, index_path=INDEX_FILE):
    with open(index_path, "w", encoding="utf-8") as handle:
        json.dump(index, handle, ensure_ascii=False, indent=2)


def get_memory_id(item):
    existing_id = item.get("id")
    if existing_id:
        return str(existing_id)

    identity = item.get("file_path") or item.get("path") or item.get("url") or item.get("name") or item.get("title") or "legacy-memory"
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"memory:{identity}"))


def build_index(files, index_path=INDEX_FILE):
    index = load_index(index_path)
    existing_by_path = {
        os.path.normcase(os.path.normpath(str(item.get("file_path") or item.get("path") or ""))): position
        for position, item in enumerate(index)
        if item.get("file_path") or item.get("path")
    }
    indexed_count = 0

    for file in files:
        raw_content = str(file.get("content", ""))
        content = normalize_text(raw_content)
        if not content:
            continue

        extension = file.get("extension") or os.path.splitext(str(file.get("path") or ""))[1]
        file_path = file.get("path")
        source_type = infer_source_type(file_path, extension, file.get("source_type"))
        filename_title = os.path.splitext(os.path.basename(str(file_path or "")))[0].replace("_", " ").replace("-", " ").title()
        generic_image_name = bool(re.fullmatch(r"(?:img|image|screenshot)(?:\s|\d|[-_])?.*", filename_title, re.IGNORECASE))
        image_heading = next((
            line.strip() for line in raw_content.splitlines()
            if len(line.strip()) > 4 and not line.strip().lower().startswith(("filename:", "visual description:", "visible text (local ocr):"))
        ), "")
        title = file.get("title") or (image_heading[:80] if source_type == "image" and generic_image_name and image_heading else filename_title)

        if file_path and not file.get("modified_at"):
            try:
                modified = os.path.getmtime(file_path)
                file["modified_at"] = datetime.fromtimestamp(modified, tz=timezone.utc).isoformat()
            except Exception:
                file["modified_at"] = utc_now()

        normalized_path = os.path.normcase(os.path.normpath(str(file_path or "")))
        prior = index[existing_by_path[normalized_path]] if normalized_path in existing_by_path else {}
        unchanged = bool(
            prior
            and prior.get("modified_at") == file.get("modified_at")
            and prior.get("content") == content
        )
        embedding_text = f"Filename: {os.path.basename(str(file_path or ''))}\n{content}" if source_type == "image" else f"{title}\n{content}"
        if source_type == "image" and not unchanged:
            print(f"[INDEX] Embedding image memory: {os.path.basename(str(file_path or ''))}")

        memory = {
            "id": prior.get("id") or file.get("id") or str(uuid.uuid4()),
            "source_type": source_type,
            "title": title,
            "content": content,
            "url": file.get("url"),
            "file_path": file_path,
            "created_at": prior.get("created_at") or file.get("created_at") or utc_now(),
            "modified_at": file.get("modified_at") or utc_now(),
            "saved_at": prior.get("saved_at") or file.get("saved_at") or utc_now(),
            "summary": file.get("summary") or make_summary(title, content, source_type),
            "embedding": prior.get("embedding") if unchanged else (file.get("embedding") or embed_text(embedding_text)),
            "metadata": {
                "extension": extension,
                "source": "local_file",
                "original_filename": os.path.basename(str(file_path or "")),
                "size": file.get("size"),
                "indexed_at": utc_now()
            }
        }

        if normalized_path in existing_by_path:
            index[existing_by_path[normalized_path]] = memory
        else:
            existing_by_path[normalized_path] = len(index)
            index.append(memory)
        indexed_count += 1

    save_index(index, index_path)
    return index, indexed_count


def remember_web_memory(page, index_path=INDEX_FILE):
    if not page:
        return None

    index = load_index(index_path)
    url = (page.get("url") or "").strip()
    title = (page.get("title") or "Saved webpage").strip() or "Saved webpage"
    text = normalize_text(page.get("text") or page.get("content") or "")
    saved_at = page.get("saved_at") or utc_now()

    memory = {
        "id": str(uuid.uuid4()),
        "source_type": "web",
        "title": title,
        "content": text,
        "url": url,
        "file_path": None,
        "created_at": saved_at,
        "modified_at": saved_at,
        "saved_at": saved_at,
        "summary": make_summary(title, text, "web"),
        "embedding": embed_text(f"{title}\n{text}"),
        "metadata": {
            "extension": "web",
            "source": "browser",
            "domain": url.split("/")[2] if url.startswith("http") else "",
            "saved_by_user": True,
            "captured_at": saved_at
        }
    }

    for existing in index:
        if existing.get("url") == url and existing.get("source_type") == "web":
            existing.update(memory)
            save_index(index, index_path)
            return existing

    index.append(memory)
    save_index(index, index_path)
    return memory


def forget_memory(memory_id, index_path=INDEX_FILE):
    index = load_index(index_path)
    filtered = [item for item in index if get_memory_id(item) != str(memory_id)]
    save_index(filtered, index_path)
    return filtered


def cosine_similarity(a, b):
    a = np.asarray(a, dtype=np.float32)
    b = np.asarray(b, dtype=np.float32)
    if a.size == 0 or b.size == 0:
        return 0.0
    denom = np.linalg.norm(a) * np.linalg.norm(b)
    if denom == 0:
        return 0.0
    return float(np.dot(a, b) / denom)


def build_reason(memory, query):
    query_terms = tokenize(query)
    fields = " ".join([
        str(memory.get("title") or ""),
        str(memory.get("summary") or ""),
        str(memory.get("content") or ""),
        str(memory.get("url") or "")
    ])
    memory_terms = tokenize(fields)
    overlap = sorted(query_terms & memory_terms)[:4]

    if overlap:
        return "Saved content covers " + ", ".join(overlap) + "."

    if memory.get("source_type") == "web":
        return "Matches the page topic and context from a saved web memory."

    return "Matches the semantic meaning of the saved local memory."


def search_memory(query, top_k=5, index_path=INDEX_FILE):
    if not query or not query.strip():
        return []

    index = load_index(index_path)
    if not index:
        return []

    retrieval_query, _ = expand_query(query)
    query_embedding = np.asarray(embed_text(retrieval_query), dtype=np.float32)
    query_terms = tokenize(query)
    query_lower = query.lower()
    results = []

    for item in index:
        item_embedding = np.asarray(item.get("embedding") or [], dtype=np.float32)
        if item_embedding.size == 0:
            continue

        similarity = cosine_similarity(query_embedding, item_embedding)
        memory_text = " ".join([
            str(item.get("title") or item.get("name") or ""),
            str(item.get("summary") or ""),
            str(item.get("content") or ""),
            str(item.get("url") or "")
        ])
        overlap = len(query_terms & tokenize(memory_text))
        title_bonus = 0.12 if query_lower in str(item.get("title", "")).lower() else 0.0
        summary_bonus = 0.08 if query_lower in str(item.get("summary", "")).lower() else 0.0
        try:
            saved = datetime.fromisoformat(str(item.get("saved_at") or item.get("created_at")).replace("Z", "+00:00"))
            if saved.tzinfo is None:
                saved = saved.replace(tzinfo=timezone.utc)
            age_days = max(0, (datetime.now(timezone.utc) - saved).days)
            recency_bonus = 0.05 / (1 + age_days / 30)
        except (TypeError, ValueError):
            recency_bonus = 0.0

        source_bonus = 0.04 if query_terms & {"pdf", "document", "file"} and item.get("source_type") != "web" else 0.0
        source_bonus += 0.04 if query_terms & {"webpage", "article", "website"} and item.get("source_type") == "web" else 0.0
        if re.search(r"\b(screenshot|image|picture|photo)\b", query, re.IGNORECASE) and item.get("source_type") == "image":
            source_bonus += 0.18

        final_score = similarity + title_bonus + summary_bonus + (overlap * 0.04) + recency_bonus + source_bonus
        final_score = max(0.0, min(final_score, 1.0))

        results.append({
            "id": get_memory_id(item),
            "name": item.get("title") or os.path.basename(str(item.get("file_path") or item.get("path") or "memory")),
            "title": item.get("title") or os.path.basename(str(item.get("file_path") or item.get("path") or "memory")),
            "source_type": item.get("source_type") or infer_source_type(item.get("file_path") or item.get("path")),
            "source": (item.get("source_type") or infer_source_type(item.get("file_path") or item.get("path"))).upper(),
            "summary": item.get("summary") or make_summary(item.get("title"), item.get("content", ""), item.get("source_type", "file")),
            "reason": build_reason(item, query),
            "url": item.get("url"),
            "file_path": item.get("file_path") or item.get("path"),
            "path": item.get("url") or item.get("file_path") or item.get("path"),
            "saved_at": item.get("saved_at") or item.get("created_at"),
            "score": round(float(final_score), 4),
            "preview": (item.get("content") or "")[:300]
        })

    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:top_k]