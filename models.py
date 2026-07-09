import re
import sqlite3
from datetime import datetime, timezone

DB_PATH = "wiki.db"

CATEGORIES = [
    "City",
    "Character",
    "Organization",
    "Location",
    "Item",
    "Quest",
]

CATEGORY_PLURALS = {
    "City": "Cities",
    "Character": "Characters",
    "Organization": "Organizations",
    "Location": "Locations",
    "Item": "Items",
    "Quest": "Quests",
}

LINK_PATTERN = re.compile(r"\[\[([^\[\]|]+)(?:\|([^\[\]]+))?\]\]")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_db()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS entry (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            category TEXT NOT NULL,
            summary TEXT DEFAULT '',
            content TEXT DEFAULT '',
            author TEXT DEFAULT '',
            image_filename TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS link (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id INTEGER NOT NULL,
            target_name TEXT NOT NULL,
            target_id INTEGER,
            FOREIGN KEY (source_id) REFERENCES entry (id) ON DELETE CASCADE,
            FOREIGN KEY (target_id) REFERENCES entry (id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS setting (
            key TEXT PRIMARY KEY,
            value TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_link_source ON link (source_id);
        CREATE INDEX IF NOT EXISTS idx_link_target ON link (target_id);
        CREATE INDEX IF NOT EXISTS idx_entry_category ON entry (category);
        """
    )
    # Lightweight migration for databases created before image_filename existed.
    existing_cols = {row["name"] for row in conn.execute("PRAGMA table_info(entry)")}
    if "image_filename" not in existing_cols:
        conn.execute("ALTER TABLE entry ADD COLUMN image_filename TEXT")
    conn.commit()
    conn.close()


def get_setting(conn, key, default=None):
    row = conn.execute("SELECT value FROM setting WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def set_setting(conn, key, value):
    conn.execute(
        "INSERT INTO setting (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
    conn.commit()


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def find_entry_by_name(conn, name):
    return conn.execute(
        "SELECT * FROM entry WHERE lower(name) = lower(?)", (name.strip(),)
    ).fetchone()


def get_entry(conn, entry_id):
    return conn.execute("SELECT * FROM entry WHERE id = ?", (entry_id,)).fetchone()


def list_entries(conn, category=None, query=None):
    sql = "SELECT * FROM entry WHERE 1=1"
    params = []
    if category:
        sql += " AND category = ?"
        params.append(category)
    if query:
        sql += " AND (name LIKE ? OR summary LIKE ? OR content LIKE ?)"
        like = f"%{query}%"
        params.extend([like, like, like])
    sql += " ORDER BY name COLLATE NOCASE ASC"
    return conn.execute(sql, params).fetchall()


def category_counts(conn):
    rows = conn.execute(
        "SELECT category, COUNT(*) as n FROM entry GROUP BY category"
    ).fetchall()
    counts = {c: 0 for c in CATEGORIES}
    for row in rows:
        counts[row["category"]] = row["n"]
    return counts


def extract_link_names(content):
    """Return a list of raw target names referenced via [[Name]] or [[Name|Display]]."""
    names = []
    for match in LINK_PATTERN.finditer(content or ""):
        target = match.group(1).strip()
        if target:
            names.append(target)
    return names


def sync_links(conn, source_id, content):
    """Recompute the link table rows for a given source entry based on its content."""
    conn.execute("DELETE FROM link WHERE source_id = ?", (source_id,))
    names = extract_link_names(content)
    seen = set()
    for name in names:
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        target = find_entry_by_name(conn, name)
        target_id = target["id"] if target else None
        conn.execute(
            "INSERT INTO link (source_id, target_name, target_id) VALUES (?, ?, ?)",
            (source_id, name, target_id),
        )
    conn.commit()


def resolve_dangling_links(conn, entry_id, entry_name):
    """When a new entry is created, point any existing dangling links with a matching
    name at it, so backlinks created before the target existed still connect."""
    conn.execute(
        "UPDATE link SET target_id = ? WHERE target_id IS NULL AND lower(target_name) = lower(?)",
        (entry_id, entry_name),
    )
    conn.commit()


def clear_links_to(conn, entry_id):
    """When an entry is renamed or deleted, detach links that pointed at it."""
    conn.execute(
        "UPDATE link SET target_id = NULL WHERE target_id = ?", (entry_id,)
    )
    conn.commit()


def get_backlinks(conn, entry_id):
    return conn.execute(
        """
        SELECT DISTINCT e.id, e.name, e.category, e.summary
        FROM link l
        JOIN entry e ON e.id = l.source_id
        WHERE l.target_id = ?
        ORDER BY e.name COLLATE NOCASE ASC
        """,
        (entry_id,),
    ).fetchall()


def create_entry(conn, name, category, summary, content, author, image_filename=None):
    ts = now_iso()
    cur = conn.execute(
        "INSERT INTO entry (name, category, summary, content, author, image_filename, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (name.strip(), category, summary.strip(), content, author.strip(), image_filename, ts, ts),
    )
    conn.commit()
    entry_id = cur.lastrowid
    resolve_dangling_links(conn, entry_id, name)
    sync_links(conn, entry_id, content)
    return entry_id


def update_entry(conn, entry_id, name, category, summary, content, author, image_filename=None):
    """image_filename: pass a new filename to replace the image, or omit/None to
    leave whatever image is already set untouched (use clear_entry_image to remove it)."""
    ts = now_iso()
    if image_filename is not None:
        conn.execute(
            "UPDATE entry SET name = ?, category = ?, summary = ?, content = ?, author = ?, "
            "image_filename = ?, updated_at = ? WHERE id = ?",
            (name.strip(), category, summary.strip(), content, author.strip(), image_filename, ts, entry_id),
        )
    else:
        conn.execute(
            "UPDATE entry SET name = ?, category = ?, summary = ?, content = ?, author = ?, updated_at = ? "
            "WHERE id = ?",
            (name.strip(), category, summary.strip(), content, author.strip(), ts, entry_id),
        )
    conn.commit()
    resolve_dangling_links(conn, entry_id, name)
    sync_links(conn, entry_id, content)


def clear_entry_image(conn, entry_id):
    conn.execute("UPDATE entry SET image_filename = NULL WHERE id = ?", (entry_id,))
    conn.commit()


def delete_entry(conn, entry_id):
    clear_links_to(conn, entry_id)
    conn.execute("DELETE FROM link WHERE source_id = ?", (entry_id,))
    conn.execute("DELETE FROM entry WHERE id = ?", (entry_id,))
    conn.commit()
