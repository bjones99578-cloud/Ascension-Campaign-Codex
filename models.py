import os
import re
import sqlite3
from datetime import datetime, timezone

# Anchored to this file's own directory rather than left as a bare relative
# path -- a relative "wiki.db" resolves against the server process's
# *current working directory*, which isn't guaranteed to be this project
# folder under every hosting setup (notably PythonAnywhere's WSGI-based
# Manual Configuration, where the process doesn't necessarily start with its
# cwd here). Overridable via the DB_PATH environment variable so a
# deployment with a persistent disk (e.g. Render's paid Starter plan + a
# mounted Disk) can still point this at a path inside that disk instead --
# otherwise every redeploy/restart/spin-down silently resets the whole
# campaign to a fresh, empty database.
APP_ROOT = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("DB_PATH", os.path.join(APP_ROOT, "wiki.db"))

CATEGORIES = [
    "Region",
    "City",
    "Character",
    "Organization",
    "Location",
    "Item",
    "Quest",
    "SessionLog",
]

CATEGORY_PLURALS = {
    "Region": "Regions",
    "City": "Cities",
    "Character": "Characters",
    "Organization": "Organizations",
    "Location": "Locations",
    "Item": "Items",
    "Quest": "Quests",
    "SessionLog": "Session Logs",
}

# "SessionLog" is stored/URLed as one word (like every other category) so it
# plays nicely with the "cat-{{ category.lower() }}" CSS-class and
# "icons/{{ category.lower() }}.svg" conventions used throughout the
# templates -- but it should still read as "Session Log" (with a space)
# anywhere the *singular* category name is shown to a person, e.g. the New
# Entry category dropdown or an entry's category tag. CATEGORY_PLURALS
# already solves this for the plural case; this is the singular equivalent,
# with the same `.get(cat, cat)` fallback so every other (already-fine)
# category is unaffected.
CATEGORY_LABELS = {
    "SessionLog": "Session Log",
}

LINK_PATTERN = re.compile(r"\[\[([^\[\]|]+)(?:\|([^\[\]]+))?\]\]")

# Columns that hold an explicit, dropdown-selected relationship to another
# entry (as opposed to relationships inferred from [[wiki links]] in prose).
# Each is nullable and only meaningful for entries of a particular category:
#   home_city_id, organization_id, current_city_id -> Character
#   region_id, leading_organization_id             -> City
#   headquarters_city_id, leader_id -> Organization (leader_id points at a Character)
#   leader_id is also reused by City, for the same reason "alignment" is
#   shared by Character and Organization -- it's the same concept ("the
#   Character who leads this") regardless of which category it's attached to.
#   current_holder_id -> Item (which Character is currently carrying it)
#   controlling_org_id -> Location (which Organization controls/owns it)
RELATIONSHIP_COLUMNS = (
    "home_city_id", "organization_id", "region_id", "headquarters_city_id", "leader_id",
    "current_city_id", "leading_organization_id", "current_holder_id", "controlling_org_id",
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

# Species/Background lists match the 2024 Player's Handbook (the "revised"
# 5e ruleset) rather than the original 2014 core lists -- notably Half-Elf
# and Half-Orc aren't part of the 2024 core species list (their old niches
# are folded into Human/Orc variant flavor instead), and the background list
# was substantially reworked. A party still using the 2014 rules, or with a
# character whose sheet predates this change, isn't blocked by any of this:
# any value already saved on an existing entry keeps displaying correctly
# even if it's no longer one of these built-in options (see the "current not
# in f.options" handling on the entry form), and "Other/Homebrew" is always
# available to type in anything not listed here.
SPECIES_OPTIONS = [
    "Aasimar", "Dragonborn", "Dwarf", "Elf", "Gnome", "Goliath", "Halfling",
    "Human", "Orc", "Tiefling", "Other/Homebrew",
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
    "Acolyte", "Artisan", "Charlatan", "Criminal", "Entertainer", "Farmer",
    "Guard", "Guide", "Hermit", "Merchant", "Noble", "Sage", "Sailor",
    "Scribe", "Soldier", "Wayfarer", "Other/Homebrew",
]

# Per-class subclass names, matching the 2024 Player's Handbook (4 per
# class, 48 total). Powers the class-dependent Subclass dropdown on the
# entry form (see entry_form.html) -- picking a Class there repopulates this
# list via JS, keyed off this exact dict, embedded as JSON. The underlying
# `subclass` column stays a plain text field (see DETAIL_FIELDS below), so a
# subclass from an older campaign, a homebrew subclass, or anything typed in
# via "+ Add new option..." still saves and displays fine even though it
# isn't one of these 48 names.
SUBCLASS_OPTIONS_BY_CLASS = {
    "Barbarian": ["Path of the Berserker", "Path of the Wild Heart", "Path of the World Tree", "Path of the Zealot"],
    "Bard": ["College of Dance", "College of Glamour", "College of Lore", "College of Valor"],
    "Cleric": ["Life Domain", "Light Domain", "Trickery Domain", "War Domain"],
    "Druid": ["Circle of the Land", "Circle of the Moon", "Circle of the Sea", "Circle of the Stars"],
    "Fighter": ["Battle Master", "Champion", "Eldritch Knight", "Psi Warrior"],
    "Monk": ["Warrior of Mercy", "Warrior of Shadow", "Warrior of the Elements", "Warrior of the Open Hand"],
    "Paladin": ["Oath of Devotion", "Oath of Glory", "Oath of the Ancients", "Oath of Vengeance"],
    "Ranger": ["Beast Master", "Fey Wanderer", "Gloom Stalker", "Hunter"],
    "Rogue": ["Arcane Trickster", "Assassin", "Soulknife", "Thief"],
    "Sorcerer": ["Aberrant Sorcery", "Clockwork Sorcery", "Draconic Sorcery", "Wild Magic Sorcery"],
    "Warlock": ["Archfey Patron", "Celestial Patron", "Fiend Patron", "Great Old One Patron"],
    "Wizard": ["Abjurer", "Diviner", "Evoker", "Illusionist"],
}

# Short, original flavor blurbs (not reproduced from any published book) for
# the in-site Reference page (see /reference in app.py) -- just enough to
# jog memory about what a species or class is about without leaving the
# site to go look it up.
SPECIES_BLURBS = {
    "Aasimar": "Touched by a celestial heritage, often marked by faintly luminous eyes or an inner warmth -- many feel called toward healing or protecting others.",
    "Dragonborn": "Proud, dragon-blooded folk with scaled skin and a breath weapon echoing their draconic ancestry; honor and clan mean a great deal to them.",
    "Dwarf": "Hardy, stubborn folk of stone and forge, known for resilience, deep loyalty to kin and clan, and a natural toughness that shrugs off poison and hardship.",
    "Elf": "Graceful, long-lived people with keen senses and an innate connection to magic; many pursue mastery of a craft over centuries rather than rushing toward it.",
    "Gnome": "Small, endlessly curious tinkerers and spellcasters with a quick wit and an irrepressible love of invention, riddles, and mischief.",
    "Goliath": "Towering mountain-folk built for endurance, shaped by harsh climates into a culture that prizes physical feats and stoic self-reliance.",
    "Halfling": "Small, nimble, and famously lucky folk who value comfort, community, and a good meal as much as any daring adventure.",
    "Human": "Adaptable and ambitious, humans are found in every corner of the world, prized for their drive, versatility, and knack for shaping their own destiny.",
    "Orc": "Powerful and tireless folk whose relentless endurance and force of will make them formidable in nearly any calling they choose to pursue.",
    "Tiefling": "Marked by an infernal bloodline visible in horns, a tail, or otherworldly eyes, tieflings often forge their own identity apart from the legacy they carry.",
}

CLASS_BLURBS = {
    "Barbarian": "A fury-driven warrior who channels raw rage into devastating strength, shrugging off blows that would fell lesser combatants.",
    "Bard": "A charismatic performer whose music and words weave real magic, inspiring allies and unraveling foes with equal skill.",
    "Cleric": "A conduit for divine power, drawing on a god or divine force to heal wounds, smite enemies, and carry out a sacred purpose.",
    "Druid": "A guardian of the natural world who commands primal magic and can take on the shapes of beasts to protect the wild.",
    "Fighter": "A master of martial combat, trained to excel with nearly any weapon or armor through discipline and relentless practice.",
    "Monk": "A disciplined martial artist who channels inner energy into supernatural speed, precision strikes, and resilience.",
    "Paladin": "A sworn champion bound by a sacred oath, blending martial prowess with divine magic in service of a cause greater than themselves.",
    "Ranger": "A skilled hunter and wilderness expert who blends martial skill with nature magic to track, survive, and protect the frontier.",
    "Rogue": "A cunning specialist in stealth and precision, striking from the shadows and slipping past danger where brute force would fail.",
    "Sorcerer": "A spellcaster whose magic wells up from an innate, often inherited source of power, shaped by force of will rather than study.",
    "Warlock": "A spellcaster who has struck a bargain with a powerful otherworldly patron in exchange for magic beyond mortal reach.",
    "Wizard": "A scholarly spellcaster whose power comes from rigorous study, arcane theory, and a carefully maintained spellbook.",
}

SETTLEMENT_SIZE_OPTIONS = [
    "Thorpe", "Hamlet", "Village", "Small Town", "Large Town",
    "Small City", "Large City", "Metropolis",
]

GOVERNMENT_OPTIONS = [
    "Monarchy", "Republic", "Theocracy", "Council/Oligarchy", "Tribal",
    "Magocracy", "Anarchy/Lawless", "Other",
]

# A City's stance toward the party -- drives the World Map pin color (blue
# for Friendly, red for Hostile, the default gold for Neutral/unset) and
# shows up as a normal detail field everywhere else a City appears.
DISPOSITION_OPTIONS = ["Friendly", "Neutral", "Hostile"]

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

# Tracks what happened to a piece of loot over time -- "In Possession" is the
# only status that counts toward the Loot Tracker's current gold total (see
# get_loot_summary); everything else is history (sold off, handed away, used
# up, destroyed, or lost) that still stays on the record for reference.
ITEM_STATUS_OPTIONS = ["In Possession", "Sold", "Given Away", "Used/Consumed", "Destroyed", "Lost"]

QUEST_STATUS_OPTIONS = ["Not Started", "Active", "Completed", "Failed", "Abandoned"]

QUEST_DIFFICULTY_OPTIONS = ["Easy", "Medium", "Hard", "Deadly"]

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
        {"name": "subclass", "label": "Subclass", "type": "subclass"},
        {"name": "key_item", "label": "Key Item", "type": "text"},
        {"name": "armor_class", "label": "Armor Class (AC)", "type": "number", "min": 0, "max": 40},
        {"name": "hit_points", "label": "Hit Points (HP)", "type": "number", "min": 0},
        {"name": "speed", "label": "Speed (ft.)", "type": "number", "min": 0},
        {"name": "passive_perception", "label": "Passive Perception", "type": "number", "min": 0},
        {"name": "deity_patron", "label": "Deity / Patron", "type": "text"},
        {"name": "personality_traits", "label": "Personality Traits", "type": "text"},
    ],
    "City": [
        {"name": "settlement_size", "label": "Settlement Size", "type": "select", "options": SETTLEMENT_SIZE_OPTIONS},
        {"name": "government", "label": "Government", "type": "select", "options": GOVERNMENT_OPTIONS},
        {"name": "population", "label": "Population", "type": "number", "min": 0},
        {"name": "disposition", "label": "Disposition", "type": "select", "options": DISPOSITION_OPTIONS},
    ],
    "Organization": [
        {"name": "org_type", "label": "Organization Type", "type": "select", "options": ORG_TYPE_OPTIONS},
        {"name": "alignment", "label": "Alignment", "type": "select", "options": ALIGNMENT_OPTIONS},
        {"name": "org_status", "label": "Status", "type": "select", "options": ORG_STATUS_OPTIONS},
        # Shares the "disposition" column with City -- same field, same three
        # options, same map-pin-coloring precedent as "alignment"/"leader"
        # being shared across categories elsewhere in this file.
        {"name": "disposition", "label": "Disposition", "type": "select", "options": DISPOSITION_OPTIONS},
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
        {"name": "estimated_value", "label": "Estimated Value (gp)", "type": "number", "min": 0},
        {"name": "item_status", "label": "Status", "type": "select", "options": ITEM_STATUS_OPTIONS},
    ],
    "Quest": [
        {"name": "quest_status", "label": "Status", "type": "select", "options": QUEST_STATUS_OPTIONS},
        {"name": "quest_giver", "label": "Quest Giver", "type": "text"},
        {"name": "reward", "label": "Reward", "type": "text"},
        {"name": "difficulty", "label": "Difficulty", "type": "select", "options": QUEST_DIFFICULTY_OPTIONS},
        {"name": "level_range", "label": "Level Range", "type": "text"},
        {"name": "xp_reward", "label": "XP Reward", "type": "number", "min": 0},
        {"name": "gold_reward", "label": "Gold Reward (gp)", "type": "number", "min": 0},
    ],
    "SessionLog": [
        {"name": "session_number", "label": "Session #", "type": "number", "min": 1},
        # A real HTML date input (stored as an ISO "YYYY-MM-DD" string, which
        # also happens to sort correctly as plain text) -- the real-world
        # date the session was played, for ordering the log chronologically.
        {"name": "session_date", "label": "Session Date", "type": "date"},
        # Free text rather than another date picker: most campaigns run on a
        # custom fantasy calendar ("the 15th of Highsun, 1492"), not the real
        # Gregorian calendar, so this stays flexible instead of forcing a
        # format that wouldn't fit most settings.
        {"name": "in_game_date", "label": "In-Game Date", "type": "text"},
    ],
}

# Flat, de-duplicated list of every detail column across all categories
# (e.g. "alignment" is shared by Character and Organization), used for
# schema creation/migration and generic read/write of these fields.
DETAIL_COLUMNS = sorted({f["name"] for fields in DETAIL_FIELDS.values() for f in fields})

# Columns that store a number rather than text.
DETAIL_INT_COLUMNS = {
    "level", "population", "armor_class", "hit_points", "speed", "passive_perception",
    "estimated_value", "xp_reward", "gold_reward", "session_number",
}

# field name -> its built-in option list, used to tell a genuinely new custom
# value apart from one that just matches a built-in option under different
# capitalization (see add_custom_option).
OPTIONS_BY_FIELD = {
    f["name"]: f["options"]
    for fields in DETAIL_FIELDS.values() for f in fields if f["type"] == "select"
}


def empty_details():
    """A details dict with every column set to None, for a brand-new entry."""
    return {col: None for col in DETAIL_COLUMNS}


def merged_detail_fields(conn):
    """DETAIL_FIELDS, but with every select field's options extended by any
    custom values the party has typed in via the "+ Add new option..." control
    on the entry form (see add_custom_option). Built fresh per request instead
    of mutating the module-level DETAIL_FIELDS, so it always reflects the
    current contents of the custom_option table."""
    custom_by_field = {}
    for row in conn.execute(
        "SELECT field_name, value FROM custom_option ORDER BY value COLLATE NOCASE ASC"
    ):
        custom_by_field.setdefault(row["field_name"], []).append(row["value"])

    merged = {}
    for category, fields in DETAIL_FIELDS.items():
        new_fields = []
        for f in fields:
            if f["type"] == "select":
                customs = custom_by_field.get(f["name"], [])
                if customs:
                    base = list(f["options"])
                    # Slot new custom options in just before a trailing "Other"
                    # catch-all (if there is one) so "Other/Homebrew" still
                    # reads as the last resort, rather than after it.
                    if base and base[-1].strip().lower().startswith("other"):
                        options = base[:-1] + customs + [base[-1]]
                    else:
                        options = base + customs
                    f = {**f, "options": options}
            new_fields.append(f)
        merged[category] = new_fields
    return merged


def add_custom_option(conn, field_name, value):
    """Persist a free-typed dropdown value (from the "+ Add new option..."
    control on a select-type detail field) so it becomes a real option in
    everyone's dropdown from now on. No-ops for blank values, for fields that
    aren't a known select-type detail field, and for values that already
    match a built-in option (case-insensitively) -- the custom_option table's
    UNIQUE constraint also guards against re-adding a value that was already
    added as a custom option before."""
    if field_name not in OPTIONS_BY_FIELD:
        return  # not a select-type detail field (e.g. a number column like level/population)
    value = (value or "").strip()
    if not value:
        return
    if any(value.lower() == opt.lower() for opt in OPTIONS_BY_FIELD[field_name]):
        return
    conn.execute(
        "INSERT OR IGNORE INTO custom_option (field_name, value, created_at) VALUES (?, ?, ?)",
        (field_name, value, now_iso()),
    )
    conn.commit()


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    # WAL mode lets readers and writers work concurrently instead of
    # blocking each other outright -- without it, a hosting plan that serves
    # requests across multiple worker processes (as PythonAnywhere's paid
    # tiers and Render both do) can throw a raw "database is locked" error
    # to the browser the moment two people save something at nearly the same
    # instant. busy_timeout gives any write that does collide a few seconds
    # to wait its turn and retry automatically rather than failing right
    # away. This is a one-time property of the database file itself (SQLite
    # remembers it), so re-issuing it on every connection is just a cheap
    # no-op after the first time.
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA busy_timeout = 5000")
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
            leading_organization_id INTEGER REFERENCES entry (id) ON DELETE SET NULL,
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

        CREATE TABLE IF NOT EXISTS custom_option (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            field_name TEXT NOT NULL,
            value TEXT NOT NULL COLLATE NOCASE,
            created_at TEXT NOT NULL,
            UNIQUE (field_name, value)
        );

        CREATE TABLE IF NOT EXISTS game_map (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            filename TEXT,
            sort_order INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS map_pin (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            map_id INTEGER REFERENCES game_map (id) ON DELETE CASCADE,
            entry_id INTEGER NOT NULL REFERENCES entry (id) ON DELETE CASCADE,
            x REAL NOT NULL,
            y REAL NOT NULL,
            symbol TEXT,
            color TEXT,
            discovered INTEGER NOT NULL DEFAULT 1,
            target_map_id INTEGER REFERENCES game_map (id) ON DELETE SET NULL,
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_link_source ON link (source_id);
        CREATE INDEX IF NOT EXISTS idx_link_target ON link (target_id);
        CREATE INDEX IF NOT EXISTS idx_entry_category ON entry (category);
        CREATE INDEX IF NOT EXISTS idx_custom_option_field ON custom_option (field_name);
        CREATE INDEX IF NOT EXISTS idx_map_pin_entry ON map_pin (entry_id);
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
    # Same lightweight-migration approach for map_pin: databases created before
    # Character pins existed won't have these columns yet (City pins never
    # used them, so they're NULL there — that's expected, not a migration gap).
    existing_pin_cols = {row["name"] for row in conn.execute("PRAGMA table_info(map_pin)")}
    for col in ("symbol", "color"):
        if col not in existing_pin_cols:
            conn.execute(f"ALTER TABLE map_pin ADD COLUMN {col} TEXT")
    if "discovered" not in existing_pin_cols:
        # Pins placed before "Discovered" existed were, by definition, always
        # visible on the map -- so they migrate in as discovered (1), not
        # hidden, to avoid retroactively fogging out a party's existing map.
        conn.execute("ALTER TABLE map_pin ADD COLUMN discovered INTEGER NOT NULL DEFAULT 1")
    if "map_id" not in existing_pin_cols:
        conn.execute("ALTER TABLE map_pin ADD COLUMN map_id INTEGER REFERENCES game_map (id) ON DELETE CASCADE")
    if "target_map_id" not in existing_pin_cols:
        # Optional drilldown: a pin can point at a more detailed map (e.g. a
        # City pin on the World Map linking to that city's own street-level
        # map) so clicking it can offer to jump straight there. Not every pin
        # uses this -- NULL just means "no sub-map for this one".
        conn.execute("ALTER TABLE map_pin ADD COLUMN target_map_id INTEGER REFERENCES game_map (id) ON DELETE SET NULL")
    # Only safe to index map_id once the column above is guaranteed to exist --
    # on a pre-multi-map database this ALTER TABLE (not the initial
    # CREATE TABLE IF NOT EXISTS, which no-ops against an existing table) is
    # what actually adds it, so this index creation must come after it.
    conn.execute("CREATE INDEX IF NOT EXISTS idx_map_pin_map ON map_pin (map_id)")
    conn.commit()

    # One-time backfill for databases from before multi-map support: they have
    # a single map image stored under the "map_filename" setting and pins with
    # no map_id yet. Migrate that legacy single map into a real game_map row
    # (named "World Map" so it reads naturally as the first entry in the new
    # map picker) and point every orphaned pin at it, so nobody's existing map
    # or pins silently vanish when this update lands.
    if conn.execute("SELECT COUNT(*) AS n FROM game_map").fetchone()["n"] == 0:
        legacy_filename = get_setting(conn, "map_filename")
        orphaned_pins = conn.execute(
            "SELECT COUNT(*) AS n FROM map_pin WHERE map_id IS NULL"
        ).fetchone()["n"]
        if legacy_filename or orphaned_pins:
            cur = conn.execute(
                "INSERT INTO game_map (name, filename, sort_order, created_at) VALUES (?, ?, ?, ?)",
                ("World Map", legacy_filename, 0, now_iso()),
            )
            legacy_map_id = cur.lastrowid
            conn.execute("UPDATE map_pin SET map_id = ? WHERE map_id IS NULL", (legacy_map_id,))
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


def list_entries(conn, category=None, query=None, filters=None):
    """filters: an optional {column_name: value} dict of exact-match detail-field
    filters (e.g. {"disposition": "Hostile", "character_status": "Alive"}) --
    used by the Search page's per-category filter dropdowns, layered on top of
    the free-text query and/or category. Column names always come from
    DETAIL_COLUMNS (never raw user input), so building the SQL with an
    f-string here is safe -- only the values themselves are parameterized."""
    sql = "SELECT * FROM entry WHERE 1=1"
    params = []
    if category:
        sql += " AND category = ?"
        params.append(category)
    if query:
        sql += " AND (name LIKE ? OR summary LIKE ? OR content LIKE ?)"
        like = f"%{query}%"
        params.extend([like, like, like])
    for col, value in (filters or {}).items():
        if col not in DETAIL_COLUMNS or not value:
            continue
        sql += f" AND {col} = ?"
        params.append(value)
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


def get_entries_by_ids(conn, ids):
    """Bulk-fetch entries by id as an {id: row} dict, in one query -- used to
    resolve a batch of relationship ids (Home City, Region, Leader, etc.) when
    building a listing table, instead of one query per row."""
    ids = [i for i in set(ids) if i]
    if not ids:
        return {}
    placeholders = ", ".join("?" * len(ids))
    rows = conn.execute(f"SELECT * FROM entry WHERE id IN ({placeholders})", ids).fetchall()
    return {row["id"]: row for row in rows}


def split_party_members(rows):
    """Partition a list of Character rows into (party_members, others), used
    everywhere a page lists Characters -- keeps party members visually and
    structurally separate from NPCs/other characters for clarity."""
    party = [r for r in rows if r["is_player_character"] == "Yes"]
    others = [r for r in rows if r["is_player_character"] != "Yes"]
    return party, others


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


def get_items_held_by(conn, character_id):
    """Every Item whose Current Holder dropdown points at this Character --
    shown as a "Carried Items" table on the Character's own page, the same
    dropdown-relationship-plus-backlink pattern used everywhere else (Home
    City, Headquarters City, Region, etc.)."""
    return conn.execute(
        "SELECT id, name, category, summary FROM entry "
        "WHERE category = 'Item' AND current_holder_id = ? ORDER BY name COLLATE NOCASE ASC",
        (character_id,),
    ).fetchall()


def get_locations_controlled_by(conn, organization_id):
    """Every Location whose Controlling Organization dropdown points at this
    Organization -- shown as a "Controlled Locations" table on the
    Organization's own page."""
    return conn.execute(
        "SELECT id, name, category, summary FROM entry "
        "WHERE category = 'Location' AND controlling_org_id = ? ORDER BY name COLLATE NOCASE ASC",
        (organization_id,),
    ).fetchall()


DEFAULT_CHARACTER_PIN_SYMBOL = "★"
DEFAULT_CHARACTER_PIN_COLOR = "#a78bfa"  # matches the Character category's own violet theme


def list_maps(conn):
    """Every map the party has, in display order -- powers the "Viewing: [...]"
    picker on the Map page. sort_order defaults to insertion order (each new
    map is appended at the end); nothing currently lets the party manually
    reorder maps, so this is effectively "oldest/most-important first"."""
    return conn.execute(
        "SELECT * FROM game_map ORDER BY sort_order ASC, name COLLATE NOCASE ASC"
    ).fetchall()


def get_map(conn, map_id):
    return conn.execute("SELECT * FROM game_map WHERE id = ?", (map_id,)).fetchone()


def create_map(conn, name, filename=None):
    cur = conn.execute(
        "INSERT INTO game_map (name, filename, sort_order, created_at) "
        "VALUES (?, ?, (SELECT COALESCE(MAX(sort_order), -1) + 1 FROM game_map), ?)",
        (name.strip(), filename, now_iso()),
    )
    conn.commit()
    return cur.lastrowid


def rename_map(conn, map_id, name):
    conn.execute("UPDATE game_map SET name = ? WHERE id = ?", (name.strip(), map_id))
    conn.commit()


def set_map_image(conn, map_id, filename):
    conn.execute("UPDATE game_map SET filename = ? WHERE id = ?", (filename, map_id))
    conn.commit()


def delete_map(conn, map_id):
    """Deletes a map row. ON DELETE CASCADE takes every pin placed on it down
    with it, and ON DELETE SET NULL clears target_map_id on any pin elsewhere
    that drilled down into this map, so removing a sub-map never leaves a
    dangling "view sub-map" link on some other map's pin. Returns the map's
    own image filename (or None) so the caller can delete the uploaded file
    too -- that's the caller's job, matching how clear_entry_image/
    delete_entry already split "remove the DB row" from "remove the uploaded
    file" elsewhere in this module."""
    row = get_map(conn, map_id)
    conn.execute("DELETE FROM game_map WHERE id = ?", (map_id,))
    conn.commit()
    return row["filename"] if row else None


def get_map_pins(conn, map_id):
    """Every pin on one specific map. Pins can mark a City, a Character, or an
    Organization -- all three live in the same `entry` table, so one query
    pulls whatever columns apply to each pin's own category:
      - City pins: the city's Leader (or, lacking one, its Leading
        Organization) and its Settlement Size, plus its Disposition, which
        drives the pin's color (Friendly = blue, Hostile = red,
        Neutral/unset = the default gold).
      - Character pins: the character's own free-picked symbol and color
        (from the pin-placement form), plus their Status for the tooltip.
      - Organization pins: the same Disposition-driven coloring as City
        pins (so a hostile guild's hideout reads red just like a hostile
        city), plus its Leader and Organization Type for the tooltip.
    Any pin can also optionally carry a target_map_id (an explicit "drill
    down to this more detailed map" link, e.g. a City pin on the World Map
    pointing at that city's own street-level map) -- resolved here too so
    the template can offer a "View sub-map" link without a second query.
    All resolved in one query rather than one round-trip per pin."""
    return conn.execute(
        """
        SELECT map_pin.id AS pin_id, map_pin.x AS x, map_pin.y AS y, map_pin.entry_id AS entry_id,
               map_pin.symbol AS symbol, map_pin.color AS color,
               map_pin.discovered AS discovered,
               map_pin.target_map_id AS target_map_id,
               target_map.name AS target_map_name,
               e.name AS entry_name, e.category AS entry_category,
               e.settlement_size AS settlement_size,
               e.disposition AS disposition,
               e.character_status AS character_status,
               e.org_type AS org_type,
               leader.name AS leader_name,
               leading_org.name AS leading_org_name
        FROM map_pin
        JOIN entry e ON e.id = map_pin.entry_id
        LEFT JOIN entry leader ON leader.id = e.leader_id
        LEFT JOIN entry leading_org ON leading_org.id = e.leading_organization_id
        LEFT JOIN game_map target_map ON target_map.id = map_pin.target_map_id
        WHERE map_pin.map_id = ?
        ORDER BY map_pin.id ASC
        """,
        (map_id,),
    ).fetchall()


def add_map_pin(conn, map_id, entry_id, x, y, symbol=None, color=None, discovered=1, target_map_id=None):
    cur = conn.execute(
        "INSERT INTO map_pin (map_id, entry_id, x, y, symbol, color, discovered, target_map_id, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (map_id, entry_id, x, y, symbol, color, discovered, target_map_id, now_iso()),
    )
    conn.commit()
    return cur.lastrowid


def delete_map_pin(conn, pin_id):
    conn.execute("DELETE FROM map_pin WHERE id = ?", (pin_id,))
    conn.commit()


def set_pin_discovered(conn, pin_id, discovered):
    """DM-only toggle: flip whether a pin has been discovered by the party
    yet. Undiscovered pins (discovered=0) are fully hidden from the default
    player-facing map view and only appear -- with a "hidden from players"
    visual treatment -- when DM Mode is switched on."""
    conn.execute(
        "UPDATE map_pin SET discovered = ? WHERE id = ?",
        (1 if discovered else 0, pin_id),
    )
    conn.commit()


def get_outgoing_links(conn, entry_id):
    """Every resolved [[wiki link]] target FROM a given entry's own content --
    the mirror image of get_backlinks (which shows what links TO an entry).
    Used by the Timeline view to show which Characters, Cities, Quests, etc.
    a given Session Log entry's write-up actually mentions, reusing the link
    table that's already populated by sync_links -- no separate relationship
    field needed."""
    return conn.execute(
        """
        SELECT DISTINCT e.id, e.name, e.category
        FROM link l
        JOIN entry e ON e.id = l.target_id
        WHERE l.source_id = ? AND l.target_id IS NOT NULL
        ORDER BY e.name COLLATE NOCASE ASC
        """,
        (entry_id,),
    ).fetchall()


def get_all_items_with_holders(conn):
    """Every Item, joined with its Current Holder's name and Party Member
    flag in one query -- the Loot Tracker page groups this single result set
    into Party-held / Other-held / Unclaimed sections rather than issuing a
    separate query per holder."""
    return conn.execute(
        """
        SELECT entry.*, holder.name AS holder_name, holder.is_player_character AS holder_is_pc
        FROM entry
        LEFT JOIN entry holder ON holder.id = entry.current_holder_id
        WHERE entry.category = 'Item'
        ORDER BY entry.name COLLATE NOCASE ASC
        """
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
                  leader_id=None, current_city_id=None, leading_organization_id=None,
                  current_holder_id=None, controlling_org_id=None,
                  pc_slot=None, details=None):
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
        "current_city_id", "leading_organization_id", "current_holder_id", "controlling_org_id",
        "pc_slot", "created_at", "updated_at",
    ]
    base_vals = [
        name.strip(), category, summary.strip(), content, author.strip(), image_filename,
        home_city_id, organization_id, region_id, headquarters_city_id, leader_id,
        current_city_id, leading_organization_id, current_holder_id, controlling_org_id,
        pc_slot, ts, ts,
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
                  leader_id=None, current_city_id=None, leading_organization_id=None,
                  current_holder_id=None, controlling_org_id=None,
                  pc_slot=None, details=None):
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
        "current_city_id", "leading_organization_id", "current_holder_id", "controlling_org_id",
        "pc_slot",
    ]
    set_vals = [
        name.strip(), category, summary.strip(), content, author.strip(),
        home_city_id, organization_id, region_id, headquarters_city_id, leader_id,
        current_city_id, leading_organization_id, current_holder_id, controlling_org_id,
        pc_slot,
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
