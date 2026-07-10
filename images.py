import io
import os
import uuid
from urllib.parse import urlparse

import requests
from PIL import Image, UnidentifiedImageError
from werkzeug.utils import secure_filename

# Overridable via the UPLOAD_DIR environment variable, same reasoning as
# models.DB_PATH -- point this at a persistent disk in production so
# uploaded portraits, city art, and map images survive redeploys/restarts.
# Served through the app's own /uploads/<filename> route (see app.py),
# not Flask's built-in /static route, since a mounted disk generally lives
# outside the app's own static folder.
UPLOAD_DIR = os.environ.get("UPLOAD_DIR", os.path.join("static", "uploads"))
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}

# Longest-edge cap (pixels) applied to every stored image. Nothing in the
# app ever displays an image anywhere near full phone-camera resolution --
# portraits and thumbnails render in small fixed-size boxes, and even the
# zoomable map view is only ever as wide as someone's browser window -- so
# downscaling to this is invisible in the UI while turning a multi-MB
# original into a few hundred KB on disk. That matters most for a
# shared-hosting disk quota (Render's Disk add-on, PythonAnywhere's per-plan
# storage cap, etc.) filling up slower as the party uploads more images over
# a campaign's lifetime.
MAX_DIMENSION = 2048
JPEG_QUALITY = 85

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


def _resized_bytes_and_ext(raw_bytes, original_ext):
    """Given raw image bytes, returns (output_bytes, file_extension) scaled
    down to MAX_DIMENSION and recompressed. Animated GIFs are left completely
    untouched -- Pillow would flatten an animation to its first frame, which
    would silently break the one format that's typically used for that kind
    of motion -- and GIFs are rare for this app's use anyway. Images with
    real transparency are kept as PNG; everything else is re-saved as JPEG,
    since photos and character art don't need an alpha channel and JPEG
    packs down substantially smaller for the same visual quality. Falls back
    to the original bytes/extension untouched if Pillow can't parse the file
    at all (corrupt upload, or some format quirk it doesn't support) --
    better to store the original than to fail the whole upload over it."""
    if original_ext == "gif":
        return raw_bytes, original_ext
    try:
        img = Image.open(io.BytesIO(raw_bytes))
        img.load()
    except (UnidentifiedImageError, OSError):
        return raw_bytes, original_ext

    has_alpha = img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info)

    if max(img.size) > MAX_DIMENSION:
        img.thumbnail((MAX_DIMENSION, MAX_DIMENSION), Image.LANCZOS)

    buf = io.BytesIO()
    if has_alpha:
        img.convert("RGBA").save(buf, format="PNG", optimize=True)
        return buf.getvalue(), "png"
    img.convert("RGB").save(buf, format="JPEG", quality=JPEG_QUALITY, optimize=True)
    return buf.getvalue(), "jpg"


def save_upload(file_storage):
    """Save an uploaded werkzeug FileStorage under a unique name, downscaled
    and recompressed via _resized_bytes_and_ext so a large phone photo
    doesn't eat disk space needlessly. Returns the stored filename (not the
    full path), or None if there was no file / the file type isn't allowed."""
    if not file_storage or not file_storage.filename:
        return None
    original = secure_filename(file_storage.filename)
    if not original or not allowed_file(original):
        return None
    ensure_upload_dir()
    ext = original.rsplit(".", 1)[1].lower()
    out_bytes, out_ext = _resized_bytes_and_ext(file_storage.read(), ext)
    stored_name = f"{uuid.uuid4().hex}.{out_ext}"
    with open(os.path.join(UPLOAD_DIR, stored_name), "wb") as f:
        f.write(out_bytes)
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

    total = 0
    chunks = []
    try:
        for chunk in resp.iter_content(8192):
            total += len(chunk)
            if total > MAX_REMOTE_BYTES:
                raise ValueError("remote image too large")
            chunks.append(chunk)
    except (OSError, ValueError, requests.RequestException):
        return None

    out_bytes, out_ext = _resized_bytes_and_ext(b"".join(chunks), ext)
    ensure_upload_dir()
    stored_name = f"{uuid.uuid4().hex}.{out_ext}"
    path = os.path.join(UPLOAD_DIR, stored_name)
    try:
        with open(path, "wb") as f:
            f.write(out_bytes)
    except OSError:
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
