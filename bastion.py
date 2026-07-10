"""Reference data and helpers for the party's Bastion (their floating cloud
ship, tracked as one shared stronghold rather than a separate one per
character -- see the 2024 Dungeon Master's Guide's "combine your Bastions
into a single structure" variant, simplified here into one shared sheet).

There is no live D&D Beyond source for this: Bastions have no field on a
character sheet and no API (official or unofficial) exposes them -- D&D
Beyond's own Bastion support is still just a blank fillable PDF as of this
writing. So the facility list below is hand-entered from the official 2024
DMG rules text (not imported), the same way the Reference page's Species/
Class blurbs are hand-entered rather than pulled from anywhere live.

Every facility has a stable "key" (never shown to the user, never renamed)
so a party's custom name/description overrides -- stored in the
bastion_facility_type_override table -- stay attached to the right facility
even if they rename it to something unrecognizable for their homebrew
airship theme.
"""

# Basic Facilities: free, no game-mechanical effect (no Orders, no
# hirelings) -- purely flavor/roleplay rooms. A Bastion gets 2 for free at
# level 5; the party can add more any time after that (this app doesn't
# track the gold/time cost of doing so, to keep this a roster rather than a
# full build-cost simulator).
BASIC_FACILITIES = [
    {"key": "bedroom", "name": "Bedroom", "description": "Sleeping quarters, furnished appropriately for the room's size."},
    {"key": "courtyard", "name": "Courtyard", "description": "An outdoor gathering space within the Bastion's walls."},
    {"key": "dining_room", "name": "Dining Room", "description": "A formal space for eating and entertaining guests."},
    {"key": "kitchen", "name": "Kitchen", "description": "Food preparation space for the Bastion's residents."},
    {"key": "parlor", "name": "Parlor", "description": "A social reception and sitting room."},
    {"key": "storage", "name": "Storage", "description": "General containment room for goods and supplies."},
]

# Special Facilities: unlock as the Bastion's level crosses 5/9/13/17 (2
# slots at 5, 2 more at 9, 1 more at 13, 1 more at 17 -- 6 total by level
# 17). Each has a Space size (Cramped/Roomy/Vast, some offer a choice) and
# usually supports one or more weekly Orders (Craft/Trade/Empower/Harvest/
# Recruit/Research) -- noted in its description, though this app doesn't
# hard-enforce which Order a given facility can run, to keep the "Current
# Order" field simple and not a rules-lawyering minefield.
SPECIAL_FACILITIES = [
    # Level 5
    {"key": "arcane_study", "name": "Arcane Study", "level": 5, "space": "Roomy",
     "description": "Requires an Arcane spellcasting focus. Crafts magic items (Common/Uncommon Implements from level 9) and grants free uses of Identify."},
    {"key": "armory", "name": "Armory", "level": 5, "space": "Roomy",
     "description": "Hirelings buy, sell, and maintain weapons and armor, and equip your Bastion Defenders."},
    {"key": "barrack", "name": "Barrack", "level": 5, "space": "Roomy or Vast",
     "description": "Houses and recruits up to 12 Bastion Defenders for protection."},
    {"key": "garden", "name": "Garden", "level": 5, "space": "Roomy or Vast",
     "description": "Harvest order: hirelings grow and gather herbs, food, or produce Potions of Healing/poison."},
    {"key": "library", "name": "Library", "level": 5, "space": "Roomy",
     "description": "Research order: hireling scholars investigate a topic, yielding a piece of lore after 7 days."},
    {"key": "sanctuary", "name": "Sanctuary", "level": 5, "space": "Roomy",
     "description": "Requires a Holy Symbol or Druidic Focus. Grants a charm to cast Healing Word and crafts sacred spellcasting foci."},
    {"key": "smithy", "name": "Smithy", "level": 5, "space": "Roomy",
     "description": "Forge, anvil, and tools. Hirelings craft mundane weapons/armor, and Uncommon magic weapons from level 9."},
    {"key": "storehouse", "name": "Storehouse", "level": 5, "space": "Roomy",
     "description": "Trade order: buys and resells goods for income."},
    {"key": "workshop", "name": "Workshop", "level": 5, "space": "Roomy or Vast",
     "description": "Crafts mundane adventuring gear and (from level 9) Common/Uncommon magic implements. A short rest here grants Heroic Inspiration."},
    # Level 9
    {"key": "gaming_hall", "name": "Gaming Hall", "level": 9, "space": "Vast",
     "description": "Trade order: a gambling hall generating variable income."},
    {"key": "greenhouse", "name": "Greenhouse", "level": 9, "space": "Roomy",
     "description": "Harvest order: controlled-climate growing of rare plants/fungi for greater healing potions and poisons."},
    {"key": "laboratory", "name": "Laboratory", "level": 9, "space": "Roomy",
     "description": "Craft order: alchemical potions of any rarity, and poisons."},
    {"key": "sacristy", "name": "Sacristy", "level": 9, "space": "Roomy",
     "description": "Requires a spellcasting focus. Crafts holy water and items from the Relic table."},
    {"key": "scriptorium", "name": "Scriptorium", "level": 9, "space": "Roomy",
     "description": "Craft order: produces spell scrolls."},
    {"key": "stable", "name": "Stable", "level": 9, "space": "Roomy or Vast",
     "description": "Trade order: buys, sells, and trains mounts."},
    {"key": "teleportation_circle", "name": "Teleportation Circle", "level": 9, "space": "Roomy",
     "description": "Recruit order: a permanent teleportation circle can summon a visiting NPC spellcaster to cast a spell for you."},
    {"key": "theater", "name": "Theater", "level": 9, "space": "Vast",
     "description": "Empower order: stage productions grant contributors a scaling Theater die (d6, d8 at level 13, d10 at level 17) usable on a d20 test."},
    {"key": "training_area", "name": "Training Area", "level": 9, "space": "Vast",
     "description": "Empower order: 7 days of training grants participants a temporary combat or skill benefit."},
    {"key": "trophy_room", "name": "Trophy Room", "level": 9, "space": "Roomy",
     "description": "Research order: investigate lore, or search for a trinket trophy (a chance at a Common magic item)."},
    # Level 13
    {"key": "archive", "name": "Archive", "level": 13, "space": "Roomy or Vast",
     "description": "An upgraded Research facility -- a deeper knowledge repository than the Library."},
    {"key": "meditation_chamber", "name": "Meditation Chamber", "level": 13, "space": "Cramped",
     "description": "Empower order: reroll (and choose) the result of your next Bastion event."},
    {"key": "menagerie", "name": "Menagerie", "level": 13, "space": "Vast",
     "description": "Recruit order: houses up to four Large creatures as Bastion Defenders or companions."},
    {"key": "observatory", "name": "Observatory", "level": 13, "space": "Roomy",
     "description": "Requires a spellcasting focus. Cast ritual spells without expending slots, plus related divination benefits."},
    {"key": "pub", "name": "Pub", "level": 13, "space": "Roomy or Vast",
     "description": "Research order: the bartender runs a spy network (intel within 10 miles, or locate a familiar creature within 50 miles); also serves a rotating magical drink with a 24-hour buff."},
    {"key": "reliquary", "name": "Reliquary", "level": 13, "space": "Cramped",
     "description": "Requires a spellcasting focus. A vault of sacred relics that enhances restoration-type spells and reduces material component costs."},
    # Level 17
    {"key": "demiplane", "name": "Demiplane", "level": 17, "space": "Vast",
     "description": "Requires an Arcane Focus. An extradimensional room accessible only to you and your hirelings; grants large temporary HP after a long rest there."},
    {"key": "guildhall", "name": "Guildhall", "level": 17, "space": "Vast",
     "description": "Requires expertise in a skill. Recruits and manages a roughly 50-member guild of specialists."},
    {"key": "sanctum", "name": "Sanctum", "level": 17, "space": "Roomy",
     "description": "Requires a spellcasting focus. Casts Heal, grants temporary HP, and keeps Word of Recall prepared."},
    {"key": "war_room", "name": "War Room", "level": 17, "space": "Vast",
     "description": "Requires a Fighting Style or Unarmored Defense. Recruit up to 10 Veteran lieutenants, each able to muster ~100 Guards (or 20 mounted) as an army, and each reducing Bastion Defender losses by 1 die when the Bastion is attacked."},
]

FACILITY_LEVEL_TIERS = (5, 9, 13, 17)

# How many Special Facility slots are unlocked at a given Bastion level --
# 0 below level 5, then 2/4/5/6 at the 5/9/13/17 tiers per the DMG's "two at
# level 5, a third and fourth at level 9, a fifth at level 13, a sixth at
# level 17."
def special_slot_count(level):
    if level is None or level < 5:
        return 0
    if level < 9:
        return 2
    if level < 13:
        return 4
    if level < 17:
        return 5
    return 6


def available_special_types(level):
    """Special Facility types unlocked at or below this Bastion level --
    what should populate a slot's dropdown once the party is high enough
    level to have opened that slot."""
    if level is None:
        level = 0
    return [f for f in SPECIAL_FACILITIES if f["level"] <= level]


ORDER_OPTIONS = ["Craft", "Trade", "Empower", "Harvest", "Recruit", "Research"]

BASIC_BY_KEY = {f["key"]: f for f in BASIC_FACILITIES}
SPECIAL_BY_KEY = {f["key"]: f for f in SPECIAL_FACILITIES}
ALL_BY_KEY = {**BASIC_BY_KEY, **SPECIAL_BY_KEY}


def merged_facility_types(conn):
    """BASIC_FACILITIES and SPECIAL_FACILITIES, but with any custom name/
    description a party has saved (see bastion_facility_type_override)
    layered on top -- built fresh per request, same pattern as
    models.merged_detail_fields, so a rename shows up everywhere
    immediately without needing to touch the reference data itself."""
    overrides = {
        row["facility_key"]: row
        for row in conn.execute("SELECT * FROM bastion_facility_type_override").fetchall()
    }

    def apply(facility):
        override = overrides.get(facility["key"])
        if not override:
            return facility
        merged = dict(facility)
        if override["custom_name"]:
            merged["name"] = override["custom_name"]
            merged["official_name"] = facility["name"]
        if override["custom_description"]:
            merged["description"] = override["custom_description"]
            merged["official_description"] = facility["description"]
        return merged

    return {
        "basic": [apply(f) for f in BASIC_FACILITIES],
        "special": [apply(f) for f in SPECIAL_FACILITIES],
    }
