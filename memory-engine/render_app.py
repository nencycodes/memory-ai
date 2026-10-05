import os

from fastapi import FastAPI

app = FastAPI(
    title="MEMORY Render Demo",
    description="A lightweight public demo for MEMORY, the privacy-first personal memory project.",
    version="1.0.0",
)


@app.get("/")
def home():
    return {
        "name": "MEMORY",
        "tagline": "Remember the meaning, not the filename.",
        "description": (
            "MEMORY is a privacy-first personal memory experience that helps people find "
            "saved information from what they remember about it."
        ),
        "image_understanding": {
            "powered_by": "Google Gemini",
            "description": "Gemini provides multimodal image understanding during explicit indexing.",
            "api_key_configured": bool(os.getenv("GEMINI_API_KEY")),
        },
        "privacy": "The full application is local-first; local files stay on the user's device by default.",
        "local_application": "The full MEMORY application runs locally for private file indexing and semantic search.",
        "render_demo": "This lightweight Render deployment provides a live project overview and fictional demo memories.",
        "endpoints": {
            "health": "/health",
            "demo": "/demo",
        },
    }


@app.get("/health")
def health():
    return {"status": "ok", "service": "MEMORY"}


@app.get("/demo")
def demo():
    return {
        "service": "MEMORY",
        "notice": "Fictional sample memories for the Render live demo.",
        "query": "What do you remember about preparing for a backend internship?",
        "memories": [
            {
                "title": "Backend Internship Preparation",
                "source": "Saved webpage",
                "description": "A fictional guide mentioning Java, Spring Boot, projects, and interview preparation.",
                "why_it_matches": "It connects backend internship preparation with Java and Spring Boot.",
            },
            {
                "title": "Cloud Platform Comparison",
                "source": "Screenshot",
                "description": "A fictional comparison of AWS and Azure, including deployment and managed databases.",
                "why_it_matches": "It compares cloud platforms and deployment topics.",
            },
            {
                "title": "Computer Vision Road Study",
                "source": "Local image",
                "description": "A fictional image describing road detection with computer vision.",
                "why_it_matches": "It concerns road detection and visual AI.",
            },
        ],
    }
