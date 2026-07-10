import re
import sqlite3
from datetime import datetime, timezone

DB_PATH = "wiki.db"

CATEGORIES = [
    "Region",
    "City",
    "Character",
    "Organization",
    "Location",
    "Item",
    "Quest",
]

CATEGORY_PLURALS = {
    "Region": "Regions",
    "City": "Cities",
    "Character": "Characters",
    "Organization": "Organizations",
    "Location": "Locations",
    "Item": "Items",
    "Quest": "Quests",
}

LINK_PATTERN = re.compile(r"\[\[([^\[\]|]+)(?:\|([^\[\]]+))?\]\]")

# Columns that hold an explicit, dropdown-selected relationship to another
# entry (as opposed to relationships inferred from [[wiki links]] in prose).
# Each is nullable and only meaningful for entries of a particular category:
#   home_city_id, organization_id, current_city_id -> Character
#   region_id                     -> City
#   headquarters_city_id, leader_id -> Organization (leader_id points at a Character)
RELATIONSHIP_COLUMNS = (
    "home_city_id", "organization_id", "region_id", "headquarters_city_id", "leader_id",
    "current_city_id",
)

# Party roster: a fixed 5-slot lineup of Player Characters, managed separately
# from the general entry form (see the /party routes). pc_slot is 1-5 while a
# Character occupies a roster slot, or NULL otherwise; it's not part of
# RELATIONSHIP_COLUMNS/DETAIL_COLUMNS since it's only ever written by the
# roster assign/unassign actions (or carried through unchanged on normal edits).
PARTY_SLOT_COUNT = 5

# ---------- typical D&D "detail" fields, per category ----------
# These are plain-value fields (not relationships to other entries) that give
# each entry type the flavor of information a D&D party actually tracks.
# Fields with a standard fixed vocabulary render as dropdowns on the form;
# everything else is free text or a number.

SPECIES_OPTIONS = [
    "Human", "Elf", "Dwarf", "Halfling", "Gnome", "Half-Elf", "Half-Orc",
    "Tiefling", "Dragonborn", "Other/Homebrew",
]

CLASS_OPTIONS = [
    "Barbarian", "Bard", "Cleric", "Druid", "Fighter", "Monk", "Paladin",
    "Ranger", "Rogue", "Sorcerer", "Warlock", "Wizard", "Other/Homebrew",
]

ALIGNMENT_OPTIONS = [
    "Lawful Good", "Neutral Good", "Chaotic Good",
    "Lawful Neutral", "True Neutral", "Chaotic Neutral",
    "Lawful Evil", "Neutral Evil", "Chaotic Evil",
]

BACKGROUND_OPTIONS = [
    "Acolyte", "Charlatan", "Criminal", "Entertainer", "Folk Hero",
    "Guild Artisan", "Hermit", "Noble", "Outlander", "Sage", "Sailor",
    "Soldier", "Urchin", "Other/Homebrew",
]

SETTLEMENT_SIZE_OPTIONS = [
    "Thorpe", "Hamlet", "Village", "Small Town", "Large Town",
    "Small City", "Large City", "Metropolis",
]

GOVERNMENT_OPTIONS = [
    "Monarchy", "Republic", "Theocracy", "Council/Oligarchy", "Tribal",
    "Magocracy", "Anarchy/Lawless", "Other",
]

ORG_TYPE_OPTIONS = [
    "Guild", "Religious Order", "Military Order", "Criminal Syndicate",
    "Noble House", "Adventuring Company", "Mercantile Company",
    "Secret Society", "Cult", "Other",
]

TERRAIN_OPTIONS = [
    "Forest", "Mountains", "Desert", "Swamp", "Plains/Grassland",
    "Coastal", "Arctic/Tundra", "Underdark", "Urban", "Mixed", "Other",
]

CLIMATE_OPTIONS = ["Temperate", "Tropical", "Arid", "Arctic", "Subarctic", "Variable", "Other"]

LOCATION_TYPE_OPTIONS = [
    "Dungeon", "Ruins", "Temple/Shrine", "Cave/Cavern", "Forest Grove",
    "Camp/Outpost", "Shop", "Tavern/Inn", "Tower", "Castle/Keep",
    "Battlefield", "Other",
]

DANGER_LEVEL_OPTIONS = ["Safe", "Low", "Moderate", "High", "Deadly"]

ITEM_TYPE_OPTIONS = [
    "Weapon", "Armor", "Shield", "Wondrous Item", "Potion", "Scroll",
    "Ring", "Rod", "Staff", "Wand", "Ammunition", "Other",
]

RARITY_OPTIONS = ["Mundane", "Common", "Uncommon", "Rare", "Very Rare", "Legendary", "Artifact"]

ATTUNEMENT_OPTIONS = ["Yes", "No"]

QUEST_STATUS_OPTIONS = ["Not Started", "Active", "Completed", "Failed", "Abandoned"]

CHARACTER_STATUS_OPTIONS = ["Alive", "Dead", "Missing", "Retired"]

ORG_STATUS_OPTIONS = ["Active", "Disbanded", "Dissolved", "Dormant"]

PLAYER_CHARACTER_OPTIONS = ["Yes", "No"]

# Fantasy color theme per Class, used only on the Player Character roster
# page (/party) to give each party member's card its own mood — e.g. a
# Ranger's card glows woodland green, a Wizard's glows arcane blue. Reuses
# the same --cat-color/--cat-light/--cat-glow custom properties as the
# per-category themes, via a "class-<slug>" CSS class.
CLASS_THEME_SLUGS = {
    "Barbarian": "barbarian",
    "Bard": "bard",
    "Cleric": "cleric",
    "Druid": "druid",
    "Fighter": "fighter",
    "Monk": "monk",
    "Paladin": "paladin",
    "Ranger": "ranger",
    "Rogue": "rogue",
    "Sorcerer": "sorcerer",
    "Warlock": "warlock",
    "Wizard": "wizard",
}

# category -> ordered list of field descriptors shown on that category's form
# and detail page. type is "select", "number", or "text".
DETAIL_FIELDS = {
    "Character": [
        {"name": "species", "label": "Species", "type": "select", "options": SPECIES_OPTIONS},
        {"name": "char_class", "label": "Class", "type": "select", "options": CLASS_OPTIONS},
        {"name": "level", "label": "Level", "type": "number", "min": 1, "max": 20},
        {"name": "alignment", "label": "Alignment", "type": "select", "options": ALIGNMENT_OPTIONS},
        {"name": "background", "label": "Background", "type": "select", "options": BACKGROUND_OPTIONS},
        {"name": "character_status", "label": "Status", "type": "select", "options": CHARACTER_STATUS_OPTIONS},
        {"name": "is_player_character", "label": "Party Member", "type": "select", "options": PLAYER_CHARACTER_OPTIONS},
        {"name": "player_name", "label": "Player Name", "type": "text"},
        {"name": "subclass", "label": "Subclass", "type": "text"},
        {"name": "key_item", "label": "Key Item", "type": "text"},
    ],
    "City": [
        {"name": "settlement_size", "label": "Settlement Size", "type": "select", "options": SETTLEMENT_SIZE_OPTIONS},
        {"name": "government", "label": "Government", "type": "select", "options": GOVERNMENT_OPTIONS},
        {"name": "population", "label": "Population", "type": "number", "min": 0},
    ],
    "Organization": [
        {"name": "org_type", "label": "Organization Type", "type": "select", "options": ORG_TYPE_OPTIONS},
        {"name": "alignment", "label": "Alignment", "type": "select", "options": ALIGNMENT_OPTIONS},
        {"name": "org_status", "label": "Status", "type": "select", "options": ORG_STATUS_OPTIONS},
    ],
    "Region": [
        {"name": "terrain", "label": "Terrain", "type": "select", "options": TERRAIN_OPTIONS},
        {"name": "climate", "label": "Climate", "type": "select", "options": CLIMATE_OPTIONS},
    ],
    "Location": [
        {"name": "location_type", "label": "Location Type", "type": "select", "options": LOCATION_TYPE_OPTIONS},
        {"name": "danger_level", "label": "Danger Level", "type": "select", "options": DANGER_LEVEL_OPTIONS},
    ],
    "Item": [
        {"name": "item_type", "label": "Item Type", "type": "select", "options": ITEM_TYPE_OPTIONS},
        {"name": "rarity", "label": "Rarity", "type": "select", "options": RARITY_OPTIONS},
        {"name": "requires_attunement", "label": "Requires Attunement", "type": "select", "options": ATTUNEMENT_OPTIONS},
    ],
    "Quest": [
        {"name": "quest_status", "label": "Status", "type": "select", "options": QUEST_STATUS_OPTIONS},
        {"name": "quest_giver", "label": "Quest Giver", "type": "text"},
        {"name": "reward", "label": "Reward", "type": "text"},
    ],
}

# Flat, de-duplicated list of every detail column across all categories
# (e.g. "alignment" is shared by Character and Organization), used for
# schema creation/migration and generic read/write of these fields.
DETAIL_COLUMNS = sorted({f["name"] for fields in DETAIL_FIELDS.values() for f in fields})

# Columns that store a number rather than text.
DETAIL_INT_COLUMNS = {"level", "population"}


def empty_details():
    """A details dict with every column set to None, for a brand-new entry."""
    return {col: None for col in DETAIL_COLUMNS}


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_db()
    detail_column_defs = ",\n            ".join(
        f"{col} {'INTEGER' if col in DETAIL_INT_COLUMNS else 'TEXT'}" for col in DETAIL_COLUMNS
    )
    conn.executescript(
        f"""
        CREATE TABLE IF NOT EXISTS entry (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            category TEXT NOT NULL,
            summary TEXT DEFAULT '',
            content TEXT DEFAULT '',
            author TEXT DEFAULT '',
            image_filename TEXT,
            home_city_id INTEGER REFERENCES entry (id) ON DELETE SET NULL,
            organization_id INTEGER REFERENCES entry (id) ON DELETE SET NULL,
            region_id INTEGER REFERENCES entry (id) ON DELETE SET NULL,
            headquarters_city_id INTEGER REFERENCES entry (id) ON DELETE SET NULL,
            leader_id INTEGER REFERENCES entry (id) ON DELETE SET NULL,
            current_city_id INTEGER REFERENCES entry (id) ON DELETE SET NULL,
            pc_slot INTEGER,
            {detail_column_defs},
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
    # Lightweight migrations for databases created before these columns existed.
    # SQLite can't add a FK constraint via ALTER TABLE, so migrated columns are
    # plain nullable INTEGERs — that's fine, the app is the only thing writing
    # to them and only ever with either a valid entry id or NULL.
    existing_cols = {row["name"] for row in conn.execute("PRAGMA table_info(entry)")}
    for col in ("image_filename", "pc_slot") + RELATIONSHIP_COLUMNS + tuple(DETAIL_COLUMNS):
        if col in existing_cols:
            continue
        if col == "image_filename":
            conn.execute("ALTER TABLE entry ADD COLUMN image_filename TEXT")
        elif col == "pc_slot":
            conn.execute("ALTER TABLE entry ADD COLUMN pc_slot INTEGER")
        elif col in RELATIONSHIP_COLUMNS:
            conn.execute(f"ALTER TABLE entry ADD COLUMN {col} INTEGER")
        elif col in DETAIL_INT_COLUMNS:
            conn.execute(f"ALTER TABLE entry ADD COLUMN {col} INTEGER")
        else:
            conn.execute(f"ALTER TABLE entry ADD COLUMN {col} TEXT")
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


def merge_by_id(*lists):
    """Merge several lists of entry rows, de-duplicating by id and sorting by
    name — used to combine explicit dropdown relationships with wiki-link
    backlinks into one table without showing the same entry twice."""
    seen = {}
    for lst in lists:
        for row in lst:
            seen[row["id"]] = row
    return sorted(seen.values(), key=lambda r: (r["name"] or "").lower())


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


def get_characters_in_city(conn, city_id):
    return conn.execute(
        "SELECT id, name, category, summary FROM entry "
        "WHERE category = 'Character' AND home_city_id = ? ORDER BY name COLLATE NOCASE ASC",
        (city_id,),
    ).fetchall()


def get_characters_in_organization(conn, organization_id):
    return conn.execute(
        "SELECT id, name, category, summary FROM entry "
        "WHERE category = 'Character' AND organization_id = ? ORDER BY name COLLATE NOCASE ASC",
        (organization_id,),
    ).fetchall()


def get_organizations_in_city(conn, city_id):
    return conn.execute(
        "SELECT id, name, category, summary FROM entry "
        "WHERE category = 'Organization' AND headquarters_city_id = ? ORDER BY name COLLATE NOCASE ASC",
        (city_id,),
    ).fetchall()


def get_cities_in_region(conn, region_id):
    return conn.execute(
        "SELECT id, name, category, summary FROM entry "
        "WHERE category = 'City' AND region_id = ? ORDER BY name COLLATE NOCASE ASC",
        (region_id,),
    ).fetchall()


def get_player_characters(conn):
    """All Characters flagged as party members, alphabetical — used for the
    roster page's occupied-slot lookup and its "assign an existing character"
    dropdown for empty slots."""
    return conn.execute(
        "SELECT * FROM entry WHERE category = 'Character' AND is_player_character = 'Yes' "
        "ORDER BY name COLLATE NOCASE ASC"
    ).fetchall()


def create_entry(conn, name, category, summary, content, author, image_filename=None,
                  home_city_id=None, organization_id=None, region_id=None, headquarters_city_id=None,
                  leader_id=None, current_city_id=None, pc_slot=None, details=None):
    """details: dict mapping a DETAIL_COLUMNS column name to its value (or None) —
    the typical D&D fields (Species, Class, Alignment, etc.) relevant to whichever
    category this entry is. Columns not relevant to this category are simply
    left NULL. pc_slot (1-5, or None) is only meaningful for a Player Character
    and is normally managed via the /party roster routes, not the entry form."""
    details = details or {}
    ts = now_iso()
    base_cols = [
        "name", "category", "summary", "content", "author", "image_filename",
        "home_city_id", "organization_id", "region_id", "headquarters_city_id", "leader_id",
        "current_city_id", "pc_slot",
        "created_at", "updated_at",
    ]
    base_vals = [
        name.strip(), category, summary.strip(), content, author.strip(), image_filename,
        home_city_id, organization_id, region_id, headquarters_city_id, leader_id,
        current_city_id, pc_slot, ts, ts,
    ]
    all_cols = base_cols + DETAIL_COLUMNS
    all_vals = base_vals + [details.get(col) for col in DETAIL_COLUMNS]
    placeholders = ", ".join(["?"] * len(all_cols))
    cur = conn.execute(
        f"INSERT INTO entry ({', '.join(all_cols)}) VALUES ({placeholders})", all_vals
    )
    conn.commit()
    entry_id = cur.lastrowid
    resolve_dangling_links(conn, entry_id, name)
    sync_links(conn, entry_id, content)
    return entry_id


def update_entry(conn, entry_id, name, category, summary, content, author, image_filename=None,
                  home_city_id=None, organization_id=None, region_id=None, headquarters_city_id=None,
                  leader_id=None, current_city_id=None, pc_slot=None, details=None):
    """image_filename: pass a new filename to replace the image, or omit/None to
    leave whatever image is already set untouched (use clear_entry_image to remove it).
    The relationship ids (home_city_id, etc.) and the details dict (Species, Class,
    Alignment, etc.) are always set to whatever is passed in, including None to
    clear them — unlike image_filename there's no separate "leave unchanged" state,
    since a <select>/<input> always resubmits its current value. pc_slot is likewise
    always overwritten — callers that want to preserve an existing slot must pass it
    back in explicitly (the entry form carries it through as a hidden field)."""
    details = details or {}
    ts = now_iso()
    set_cols = [
        "name", "category", "summary", "content", "author",
        "home_city_id", "organization_id", "region_id", "headquarters_city_id", "leader_id",
        "current_city_id", "pc_slot",
    ]
    set_vals = [
        name.strip(), category, summary.strip(), content, author.strip(),
        home_city_id, organization_id, region_id, headquarters_city_id, leader_id,
        current_city_id, pc_slot,
    ]
    if image_filename is not None:
        set_cols.append("image_filename")
        set_vals.append(image_filename)
    set_cols.extend(DETAIL_COLUMNS)
    set_vals.extend(details.get(col) for col in DETAIL_COLUMNS)
    set_cols.append("updated_at")
    set_vals.append(ts)
    set_clause = ", ".join(f"{c} = ?" for c in set_cols)
    set_vals.append(entry_id)
    conn.execute(f"UPDATE entry SET {set_clause} WHERE id = ?", set_vals)
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
