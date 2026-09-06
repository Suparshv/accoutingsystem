"""Local-filesystem image uploads (SPEC.md §5 UPLOAD_DIR, §17 P1).

The first and only place this application writes a file. Three things here are
security-relevant rather than incidental, so none of them is optional:

**The client's filename is never used.** Not sanitised, not sniffed — discarded.
A name is generated from `secrets.token_hex`, and only the extension is chosen
(by us, from the detected type). That closes path traversal ("../../.env"),
Windows device names, unicode look-alikes and overwrite-by-collision in one
move, rather than trying to filter a name that only has to slip through once.

**The declared content type is not believed.** `Content-Type` is client-supplied
like everything else (R6), so the first bytes are checked against the real JPEG
and PNG signatures. Without Pillow in the pinned stack (SPEC.md §3) this is a
signature check, not a decode: it proves the file starts like an image, not that
the rest of it is a valid one. That is enough to stop a .php or .html being
served back as an <img> src, which is what matters here.

**The size cap is enforced while reading, not after.** Reading the whole upload
and then measuring it would let a client spend the memory first and be told off
second.
"""

from __future__ import annotations

import secrets
from pathlib import Path

from fastapi import UploadFile

from app.config import BASE_DIR, settings
from app.core.errors import ImageTooLargeError, UnsupportedImageTypeError

MAX_IMAGE_BYTES = 2 * 1024 * 1024  # 2 MB
_CHUNK = 64 * 1024

# Detected type -> the extension we give the file. Declared content types are
# matched against these keys only after the signature agrees.
_JPEG = "image/jpeg"
_PNG = "image/png"

EXTENSIONS = {_JPEG: ".jpg", _PNG: ".png"}
ALLOWED_CONTENT_TYPES = {_JPEG, "image/jpg", _PNG}

_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_JPEG_SIGNATURE = b"\xff\xd8\xff"


def upload_root() -> Path:
    """UPLOAD_DIR as an absolute path, created if it does not exist yet.

    Relative values in .env ("./uploads") resolve against backend/, not against
    the process's working directory, so the location does not move depending on
    where uvicorn was started from.
    """
    configured = Path(settings.upload_dir)
    root = configured if configured.is_absolute() else BASE_DIR / configured
    root.mkdir(parents=True, exist_ok=True)
    return root


def _detect_type(head: bytes) -> str | None:
    """The real image type from the leading bytes, or None if it is neither."""
    if head.startswith(_PNG_SIGNATURE):
        return _PNG
    if head.startswith(_JPEG_SIGNATURE):
        return _JPEG
    return None


def save_image(file: UploadFile) -> str:
    """Validate and store an uploaded image; return its generated filename.

    The caller stores that filename (never a path, never the client's name) and
    is responsible for the database write.
    """
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise UnsupportedImageTypeError(
            f"'{file.content_type or 'unknown'}' is not a supported image type. "
            "Upload a JPEG or a PNG."
        )

    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = file.file.read(_CHUNK)
        if not chunk:
            break
        total += len(chunk)
        if total > MAX_IMAGE_BYTES:
            # Stop reading here: the rest of the body is not worth the memory.
            raise ImageTooLargeError()
        chunks.append(chunk)

    content = b"".join(chunks)
    if not content:
        raise UnsupportedImageTypeError("The uploaded file is empty.")

    detected = _detect_type(content[:8])
    if detected is None:
        raise UnsupportedImageTypeError(
            "That file is not a JPEG or a PNG, whatever it is named."
        )

    filename = f"{secrets.token_hex(16)}{EXTENSIONS[detected]}"
    (upload_root() / filename).write_bytes(content)
    return filename


def delete_image(filename: str | None) -> None:
    """Remove a previously stored image. Silent if it is already gone.

    `filename` is only ever a name this module generated, but it is re-checked
    against the upload root before unlinking: a bare `unlink` on a value read
    back from the database would delete whatever that value pointed at if a row
    were ever written by something other than save_image.
    """
    if not filename:
        return
    root = upload_root()
    target = (root / filename).resolve()
    if target.parent != root.resolve() or not target.is_file():
        return
    target.unlink(missing_ok=True)
