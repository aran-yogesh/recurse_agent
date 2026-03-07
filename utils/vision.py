import base64
from pathlib import Path

SUPPORTED_FORMATS = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
}


def encode_image(image_path: str) -> tuple[str, str]:
    """Encode an image file to base64. Returns (data, media_type)."""
    path = Path(image_path)

    if path.suffix.lower() not in SUPPORTED_FORMATS:
        supported = ", ".join(SUPPORTED_FORMATS)
        raise ValueError(f"Unsupported format '{path.suffix}'. Supported: {supported}")

    media_type = SUPPORTED_FORMATS[path.suffix.lower()]
    data = base64.standard_b64encode(path.read_bytes()).decode("utf-8")

    return data, media_type
