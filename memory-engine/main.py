import os
import webbrowser
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from scanner import scan_folder
from extractor import analyze_image_with_gemini, extract_text
from semantic_search import (
    build_index,
    forget_memory,
    get_memory_id,
    load_index,
    remember_web_memory,
    search_memory,
)
from gemma_reasoning import gemma_status

app = FastAPI(title="MEMORY Engine")
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"(chrome-extension://.*|http://(127\.0\.0\.1|localhost)(:\d+)?)",
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
)


class FolderRequest(BaseModel):
    path: str = Field(..., min_length=1)


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1)


class RememberPageRequest(BaseModel):
    title: Optional[str] = None
    url: Optional[str] = None
    text: Optional[str] = None
    saved_at: Optional[str] = None


class ForgetRequest(BaseModel):
    id: str = Field(..., min_length=1)


def extract_index_content(file):
    filename = file["name"]
    content = extract_text(file["path"])

    if file.get("extension") in {".png", ".jpg", ".jpeg", ".webp"}:
        description = analyze_image_with_gemini(file["path"])
        parts = [f"Filename: {filename}"]
        if description:
            parts.append(f"Visual description: {description}")
        if content and content.strip():
            parts.append(f"Visible text (local OCR): {content}")
        content = "\n".join(parts)
        if not content.strip():
            content = f"Filename: {filename}"

    return content


@app.get("/")
def home():
    return {"status": "Memory engine is running 🧠"}


@app.get("/health")
def health():
    return {"status": "ok", "retrieval": "local sentence-transformers", "reasoning": gemma_status()}


@app.get("/ai-status")
def ai_status():
    return {"embeddings": "local all-MiniLM-L6-v2", "gemma": gemma_status()}


@app.post("/scan")
def scan(request: FolderRequest):
    files = scan_folder(request.path)
    return {"count": len(files), "files": files}


@app.post("/index")
def index(request: FolderRequest):
    files = scan_folder(request.path)
    indexed = []

    for file in files:
        content = extract_index_content(file)
        indexed.append({
            "name": file["name"],
            "path": file["path"],
            "extension": file["extension"],
            "content": content[:20000]
        })

    return {"count": len(indexed), "files": indexed}


@app.post("/build-memory")
def build_memory(request: FolderRequest):
    files = scan_folder(request.path)
    extracted = []

    for file in files:
        content = extract_index_content(file)
        if content and content.strip():
            extracted.append({
                "name": file["name"],
                "path": file["path"],
                "extension": file["extension"],
                "content": content,
                "size": file.get("size")
            })

    _, indexed_count = build_index(extracted)

    return {
        "status": "Memory created 🧠",
        "files": indexed_count
    }


@app.post("/remember-page")
def remember_page(request: RememberPageRequest):
    if not request.url and not request.title:
        raise HTTPException(status_code=400, detail="Page URL or title is required.")

    memory = remember_web_memory({
        "title": request.title,
        "url": request.url,
        "text": request.text,
        "saved_at": request.saved_at
    })

    if not memory:
        raise HTTPException(status_code=500, detail="Could not save the page.")

    return {
        "status": "Memory saved",
        "memory": {
            "id": memory["id"],
            "title": memory["title"],
            "summary": memory["summary"],
            "source_type": memory["source_type"],
            "url": memory["url"],
            "saved_at": memory["saved_at"]
        }
    }


@app.post("/forget")
def forget(request: ForgetRequest):
    index = forget_memory(request.id)
    return {"status": "Memory forgotten", "remaining": len(index)}


@app.post("/open")
def open_memory(request: ForgetRequest):
    memory = next(
        (item for item in load_index() if get_memory_id(item) == request.id),
        None
    )
    file_path = (memory or {}).get("file_path") or (memory or {}).get("path")
    if not memory or not file_path:
        raise HTTPException(status_code=404, detail="Original local file not found.")

    if not os.path.isfile(file_path):
        raise HTTPException(status_code=404, detail="Original local file no longer exists.")

    try:
        if hasattr(os, "startfile"):
            os.startfile(file_path)
        else:
            webbrowser.open(file_path)
    except Exception as error:
        raise HTTPException(status_code=500, detail="Could not open the original file.") from error

    return {"status": "Opened original file"}


@app.post("/search")
def search(request: SearchRequest):
    results = search_memory(request.query)
    return {"query": request.query, "results": results, "reasoning": gemma_status()}