import html as html_lib
import re
from urllib.parse import quote

import markdown

from models import LINK_PATTERN, find_entry_by_name

# Lightweight HTML sanitizer (no external dependency required). This app is meant
# for a small trusted group of friends, not the public internet, so this is a
# reasonable safety net rather than an airtight sanitizer: it strips script/style/
# iframe/object/embed tags, inline event-handler attributes (onclick=...), and
# javascript: URLs, while leaving normal Markdown-generated HTML untouched.
_DANGEROUS_TAGS = re.compile(
    r"<\s*/?\s*(script|style|iframe|object|embed|form|meta|link)\b[^>]*>",
    re.IGNORECASE | re.DOTALL,
)
_EVENT_ATTR = re.compile(r'\s+on[a-z]+\s*=\s*(".*?"|\'.*?\'|[^\s>]+)', re.IGNORECASE)
_JS_HREF = re.compile(r'(href|src)\s*=\s*(["\'])\s*javascript:[^"\']*\2', re.IGNORECASE)


def sanitize_html(raw_html):
    cleaned = _DANGEROUS_TAGS.sub("", raw_html)
    cleaned = _EVENT_ATTR.sub("", cleaned)
    cleaned = _JS_HREF.sub(lambda m: f'{m.group(1)}="#"', cleaned)
    return cleaned


def render_wiki_content(content, conn):
    """Convert raw markdown + [[wiki links]] into safe HTML."""
    raw_html = markdown.markdown(
        content or "",
        extensions=["fenced_code", "tables", "nl2br", "sane_lists"],
    )
    clean_html = sanitize_html(raw_html)

    def replace(match):
        target = match.group(1).strip()
        display = (match.group(2) or target).strip()
        display_esc = html_lib.escape(display)
        entry = find_entry_by_name(conn, target)
        if entry:
            return f'<a href="/entry/{entry["id"]}" class="wiki-link">{display_esc}</a>'
        create_url = f"/new?name={quote(target)}"
        return (
            f'<a href="{create_url}" class="wiki-link wiki-link-missing" '
            f'title="No entry yet for &quot;{html_lib.escape(target)}&quot; — click to create it">'
            f'{display_esc}</a>'
        )

    return LINK_PATTERN.sub(replace, clean_html)
