from pathlib import Path
from functools import lru_cache
import mimetypes
import os
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

try:
    from pypdf import PdfReader
except Exception:  # pragma: no cover
    PdfReader = None

try:
    from docx import Document
except Exception:  # pragma: no cover
    Document = None


def _read_text_file(path):
    return path.read_text(encoding="utf-8", errors="ignore")


@lru_cache(maxsize=1)
def _get_ocr_engine():
    from rapidocr_onnxruntime import RapidOCR

    return RapidOCR()


def _extract_image_text(path):
    result, _ = _get_ocr_engine()(str(path))
    if not result:
        return ""
    return "\n".join(item[1] for item in result if len(item) > 1 and item[1].strip())


def analyze_image_with_gemini(image_path):
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print(f"[WARN] Gemini unavailable for {Path(image_path).name}: GEMINI_API_KEY is not set; using local OCR.")
        return ""

    print(f"[IMAGE] {Path(image_path).name}")
    print("[AI] Analyzing image with Gemini...")
    prompt = (
        "You are the visual memory engine for a privacy-focused personal memory system.\n\n"
        "Analyze this image carefully. Return a concise but information-rich searchable description.\n"
        "Include all readable text; names, technologies, organizations, dates and numbers visible; "
        "important objects or visual concepts; what this screenshot, photo, or document appears to be about; "
        "and useful search keywords. Do not invent information that is not visible."
    )

    try:
        from google import genai
        from google.genai import types

        mime_type = mimetypes.guess_type(str(image_path))[0] or "application/octet-stream"
        with open(image_path, "rb") as image_file:
            image_bytes = image_file.read()

        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model="gemini-3.8-flash",
            contents=[
                prompt,
                types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
            ],
        )
        description = (response.text or "").strip()
        if description:
            print("[AI] Image understanding complete")
            return description

        print(f"[WARN] Gemini returned no description for {Path(image_path).name}; using local OCR.")
    except Exception as error:
        status_code = getattr(error, "code", None) or getattr(error, "status_code", None)
        reason = "rate limit (429)" if str(status_code) == "429" or "429" in str(error) else type(error).__name__
        print(f"[WARN] Gemini image analysis failed for {Path(image_path).name} ({reason}); using local OCR.")

    return ""


def extract_text(file_path):
    path = Path(file_path)
    extension = path.suffix.lower()

    try:
        if extension in [".txt", ".md", ".csv"]:
            return _read_text_file(path)

        if extension == ".pdf":
            if PdfReader is None:
                return "Scanned/image PDF — OCR required"

            reader = PdfReader(str(path))
            text = ""
            for page in reader.pages:
                extracted = page.extract_text() or ""
                if extracted.strip():
                    text += extracted + "\n"

            if text.strip():
                return text
            return "Scanned/image PDF — OCR required"

        if extension == ".docx":
            if Document is None:
                return ""

            document = Document(str(path))
            return "\n".join(paragraph.text for paragraph in document.paragraphs)

        if extension in [".png", ".jpg", ".jpeg", ".webp"]:
            try:
                text = _extract_image_text(path)
                if text and text.strip():
                    return text
            except Exception:
                pass

            return ""

        return ""

    except Exception as e:
        print(f"Could not read {file_path}: {e}")
        return ""