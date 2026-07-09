import os
import uuid
from urllib.parse import urlparse

import requests
from werkzeug.utils import secure_filename

UPLOAD_DIR = os.path.join("static", "uploads")
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}

# Hosts we're willing to download an image from on the server's behalf (used
# for pulling a D&D Beyond character's avatar). Keeping this to an allowlist
# avoids the app being used to fetch arbitrary internal/external URLs.
ALLOWED_REMOTE_HOST_SUFFIXES = (
    "dndbeyond.com",
    "cursecdn.com",
    "cloudfront.net",
)
REMOTE_CONTENT_TYPE_EXTENSIONS = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/gif": "gif",
    "image/webp": "webp",
}
MAX_REMOTE_BYTES = 8 * 1024 * 1024


def ensure_upload_dir():
    os.makedirs(UPLOAD_DIR, exist_ok=True)


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def save_upload(file_storage):
    """Save an uploaded werkzeug FileStorage under a unique name.
    Returns the stored filename (not the full path), or None if there was
    no file / the file type isn't allowed."""
    if not file_storage or not file_storage.filename:
        return None
    original = secure_filename(file_storage.filename)
    if not original or not allowed_file(original):
        return None
    ensure_upload_dir()
    ext = original.rsplit(".", 1)[1].lower()
    stored_name = f"{uuid.uuid4().hex}.{ext}"
    file_storage.save(os.path.join(UPLOAD_DIR, stored_name))
    return stored_name


def save_from_url(url):
    """Download an image from an allowlisted remote host (used for a D&D Beyond
    avatar) and save it under a unique name. Returns the stored filename, or
    None if the URL is missing, not on the allowlist, not actually an image,
    too large, or the download fails for any reason — callers should treat
    None as "no image, that's fine" rather than an error."""
    if not url:
        return None
    try:
        parsed = urlparse(url)
    except ValueError:
        return None
    if parsed.scheme not in ("http", "https"):
        return None
    host = (parsed.hostname or "").lower()
    if not any(host == suf or host.endswith("." + suf) for suf in ALLOWED_REMOTE_HOST_SUFFIXES):
        return None

    try:
        resp = requests.get(url, timeout=10, stream=True)
        resp.raise_for_status()
    except requests.RequestException:
        return None

    content_type = resp.headers.get("Content-Type", "").split(";")[0].strip().lower()
    ext = REMOTE_CONTENT_TYPE_EXTENSIONS.get(content_type)
    if not ext:
        return None

    ensure_upload_dir()
    stored_name = f"{uuid.uuid4().hex}.{ext}"
    path = os.path.join(UPLOAD_DIR, stored_name)
    total = 0
    try:
        with open(path, "wb") as f:
            for chunk in resp.iter_content(8192):
                total += len(chunk)
                if total > MAX_REMOTE_BYTES:
                    raise ValueError("remote image too large")
                f.write(chunk)
    except (OSError, ValueError, requests.RequestException):
        if os.path.exists(path):
            os.remove(path)
        return None
    return stored_name


def delete_upload(filename):
    if not filename:
        return
    path = os.path.join(UPLOAD_DIR, filename)
    if os.path.exists(path):
        try:
            os.remove(path)
        except OSError:
            pass
