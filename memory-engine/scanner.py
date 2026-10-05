from pathlib import Path

SUPPORTED_EXTENSIONS = {
    ".pdf",
    ".txt",
    ".md",
    ".csv",
    ".docx",
    ".png",
    ".jpg",
    ".jpeg",
    ".webp"
}


def scan_folder(folder_path):
    folder = Path(folder_path)
    files = []

    if not folder.exists() or not folder.is_dir():
        return files

    for file in sorted(folder.rglob("*")):
        if not file.is_file():
            continue

        extension = file.suffix.lower()
        if extension not in SUPPORTED_EXTENSIONS:
            continue

        try:
            files.append({
                "name": file.name,
                "path": str(file),
                "extension": extension,
                "size": file.stat().st_size
            })
        except Exception:
            continue

    return files