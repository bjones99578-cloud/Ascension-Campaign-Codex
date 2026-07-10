"""Import a character from D&D Beyond.

D&D Beyond has no official public API or account-linking for third-party
apps. This uses an undocumented internal endpoint that D&D Beyond staff have
explicitly said is "not a public API" and could change or stop working at
any time without notice. It only works for a character whose sheet privacy
is set to Public. Every failure path below is expected to happen eventually —
this module is written to degrade to a clear error message rather than crash
the app when that day comes.
"""
import math
import re

import requests

CHARACTER_API_URL = "https://character-service.dndbeyond.com/character/v5/character/{id}"
REQUEST_TIMEOUT = 10

ABILITY_NAMES = {
    1: "Strength",
    2: "Dexterity",
    3: "Constitution",
    4: "Intelligence",
    5: "Wisdom",
    6: "Charisma",
}

# D&D Beyond stores alignment as a fixed 1-9 id rather than a name. This is
# the order D&D Beyond's own alignment picker uses, and lines up 1-for-1 with
# models.ALIGNMENT_OPTIONS (index 5 there is "True Neutral").
ALIGNMENT_BY_ID = {
    1: "Lawful Good",
    2: "Neutral Good",
    3: "Chaotic Good",
    4: "Lawful Neutral",
    5: "True Neutral",
    6: "Chaotic Neutral",
    7: "Lawful Evil",
    8: "Neutral Evil",
    9: "Chaotic Evil",
}


# The 18 skills, each tied to an ability score id (see ABILITY_NAMES) and the
# lowercase-hyphenated "subType" slug D&D Beyond's own modifier objects use
# to reference them (e.g. a proficiency modifier granting Perception looks
# like {"type": "proficiency", "subType": "perception", ...}). Order matches
# D&D Beyond's own character sheet skill list.
SKILL_DEFS = [
    ("acrobatics", "Acrobatics", 2),
    ("animal-handling", "Animal Handling", 5),
    ("arcana", "Arcana", 4),
    ("athletics", "Athletics", 1),
    ("deception", "Deception", 6),
    ("history", "History", 4),
    ("insight", "Insight", 5),
    ("intimidation", "Intimidation", 6),
    ("investigation", "Investigation", 4),
    ("medicine", "Medicine", 5),
    ("nature", "Nature", 4),
    ("perception", "Perception", 5),
    ("performance", "Performance", 6),
    ("persuasion", "Persuasion", 6),
    ("religion", "Religion", 4),
    ("sleight-of-hand", "Sleight of Hand", 2),
    ("stealth", "Stealth", 2),
    ("survival", "Survival", 5),
]


class DndBeyondError(Exception):
    """Raised with a message that's safe to show directly to the user."""


def extract_character_id(text):
    """Pull a numeric character ID out of a pasted D&D Beyond URL or raw ID.
    Deliberately returns only digits — we build the fetch URL ourselves from
    a hardcoded host, we never fetch a URL supplied directly by the user."""
    if not text:
        return None
    text = text.strip()
    match = re.search(r"/characters/(\d+)", text)
    if match:
        return match.group(1)
    match = re.search(r"\d{3,15}", text)
    return match.group(0) if match else None


def fetch_character(character_id):
    """Fetch a public D&D Beyond character's raw data dict, or raise
    DndBeyondError with a message suitable for display to the user."""
    url = CHARACTER_API_URL.format(id=character_id)
    try:
        resp = requests.get(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; AscensionCampaignCodex/1.0)",
                "Accept": "application/json",
            },
            timeout=REQUEST_TIMEOUT,
        )
    except requests.RequestException as exc:
        raise DndBeyondError(
            "Couldn't reach D&D Beyond to fetch that character. It may be "
            "temporarily unavailable, or D&D Beyond may have changed "
            "something on their end — this relies on an unofficial endpoint "
            "they don't guarantee. Try again later, or enter the character "
            "manually."
        ) from exc

    if resp.status_code == 404:
        raise DndBeyondError(
            "D&D Beyond couldn't find that character, or its sheet isn't set "
            "to Public. Open the character on D&D Beyond, find its privacy "
            "setting, switch it to Public, then try importing again."
        )
    if not resp.ok:
        raise DndBeyondError(
            f"D&D Beyond returned an unexpected error (status {resp.status_code}). "
            "Try again later, or enter the character manually."
        )

    try:
        payload = resp.json()
    except ValueError as exc:
        raise DndBeyondError(
            "D&D Beyond didn't return valid character data — this unofficial "
            "endpoint may have changed. Try entering the character manually."
        ) from exc

    data = payload.get("data") if isinstance(payload, dict) else None
    if not data:
        raise DndBeyondError("D&D Beyond didn't return any character data for that ID.")
    return data


def _classes_summary(data):
    classes = data.get("classes") or []
    parts = []
    for c in classes:
        try:
            name = c["definition"]["name"]
        except (KeyError, TypeError):
            continue
        level = c.get("level", "")
        parts.append(f"{name} {level}".strip())
    return " / ".join(parts)


def _primary_class_info(data):
    """Pick the class D&D Beyond marked as the character's starting class
    (falling back to the first one listed) to fill in the single Class /
    Subclass fields our entry form has, and sum every class's level for a
    multiclassed character's total Level. Returns (class_name, subclass_name,
    total_level) — any of which may be "" / None if not present."""
    classes = data.get("classes") or []
    if not classes:
        return "", "", None

    total_level = 0
    primary = None
    for c in classes:
        total_level += c.get("level") or 0
        if c.get("isStartingClass") and primary is None:
            primary = c
    if primary is None:
        primary = classes[0]

    class_name = ((primary.get("definition") or {}).get("name") or "").strip()
    subclass_name = ((primary.get("subclassDefinition") or {}).get("name") or "").strip()
    return class_name, subclass_name, (total_level or None)


def _ability_scores(data):
    """Final 1-6 ability-id -> score dict, folding in bonusStats (racial/
    misc flat bonuses) and overrideStats (a DM/player-set final value that
    wins over everything else) the same way D&D Beyond's own sheet does."""
    base = {s.get("id"): s.get("value") for s in (data.get("stats") or []) if s.get("value") is not None}
    bonus = {s.get("id"): s.get("value") for s in (data.get("bonusStats") or []) if s.get("value") is not None}
    override = {s.get("id"): s.get("value") for s in (data.get("overrideStats") or []) if s.get("value") is not None}

    scores = {}
    for i in range(1, 7):
        if i in override:
            scores[i] = override[i]
        else:
            scores[i] = base.get(i, 10) + bonus.get(i, 0)
    return scores


def _ability_mod(score):
    return (score - 10) // 2


def _has_ability_data(data):
    """True if the payload actually carried ability-score data, as opposed
    to _ability_scores' always-populated (defaults to 10) return value --
    used to skip the Ability/Skill/AC/HP/Speed sections entirely for a
    payload that never had real stats to begin with, rather than rendering
    a table of guessed-at 10s as if it meant something."""
    return bool(data.get("stats") or data.get("overrideStats"))


def _stats_table(data):
    if not _has_ability_data(data):
        return ""
    scores = _ability_scores(data)
    lines = ["| Ability | Score |", "|---|---|"]
    for i in range(1, 7):
        lines.append(f"| {ABILITY_NAMES[i]} | {scores[i]} |")
    return "\n".join(lines)


def _all_modifiers(data):
    """Flatten data["modifiers"] (a dict of lists keyed "race"/"class"/
    "background"/"feat"/"item"/"condition") into one list, since AC/HP/
    Speed/skill bonuses can each come from any of those categories and we
    only care about the individual modifier entries, not which one granted
    them."""
    groups = data.get("modifiers") or {}
    result = []
    for group in groups.values():
        if isinstance(group, list):
            result.extend(group)
    return result


def _total_level(data):
    classes = data.get("classes") or []
    total = sum(c.get("level") or 0 for c in classes)
    return total or 1


def _proficiency_bonus(total_level):
    return 2 + (total_level - 1) // 4


def _skill_proficiency_multiplier(modifiers, subtype):
    """Highest of Proficient (x1), Expertise (x2), or Jack-of-All-Trades-style
    Half-Proficiency (x0.5) granted for one skill/passive-perception subtype,
    matching how D&D Beyond itself resolves stacking proficiency sources
    (expertise always wins over plain proficiency, which always wins over
    half-proficiency)."""
    mult = 0.0
    for m in modifiers:
        if m.get("subType") != subtype:
            continue
        m_type = m.get("type")
        if m_type == "expertise":
            mult = max(mult, 2.0)
        elif m_type == "proficiency":
            mult = max(mult, 1.0)
        elif m_type == "half-proficiency":
            mult = max(mult, 0.5)
    return mult


def _flat_bonus(modifiers, subtype):
    total = 0
    for m in modifiers:
        if m.get("type") == "bonus" and m.get("subType") == subtype and isinstance(m.get("value"), (int, float)):
            total += m["value"]
    return total


def _compute_armor_class(data, ability_scores, modifiers):
    """Best-effort AC: equipped armor's own base AC plus a Dexterity modifier
    capped per armor category (full for Light, +2 max for Medium, none for
    Heavy), an equipped shield's bonus, any flat "armor-class" bonus
    modifiers (fighting styles, magic items, feats), and -- if nothing is
    equipped -- an Unarmored Defense-style "set" modifier (Barbarian uses
    Constitution, Monk uses Wisdom) layered over the standard 10 + Dex.
    Deliberately conservative: unrecognized armor "type" strings fall back
    to treating Dex as fully applied rather than guessing a cap."""
    dex_mod = _ability_mod(ability_scores.get(2, 10))
    inventory = data.get("inventory") or []

    equipped_armor = None
    shield_bonus = 0
    for item in inventory:
        if not item.get("equipped"):
            continue
        definition = item.get("definition") or {}
        ac_value = definition.get("armorClass")
        if ac_value is None:
            continue
        item_type = (definition.get("type") or definition.get("filterType") or "").lower()
        if "shield" in item_type:
            shield_bonus += ac_value
        elif equipped_armor is None:
            equipped_armor = (ac_value, item_type)

    flat_bonus = _flat_bonus(modifiers, "armor-class")

    if equipped_armor:
        base_ac, item_type = equipped_armor
        if "light" in item_type:
            ac = base_ac + dex_mod
        elif "medium" in item_type:
            ac = base_ac + min(dex_mod, 2)
        elif "heavy" in item_type:
            ac = base_ac
        else:
            ac = base_ac + dex_mod
    else:
        unarmored_stat_id = None
        for m in modifiers:
            if m.get("type") == "set" and m.get("subType") == "unarmored-armor-class" and m.get("statId"):
                unarmored_stat_id = m["statId"]
        ac = 10 + dex_mod
        if unarmored_stat_id:
            ac += _ability_mod(ability_scores.get(unarmored_stat_id, 10))

    return round(ac + shield_bonus + flat_bonus)


def _compute_hit_points(data, total_level, ability_scores):
    """baseHitPoints is D&D Beyond's running total of hit-die rolls/averages
    from leveling up ONLY -- it deliberately excludes the Constitution
    contribution, which has to be added back in separately (conMod per
    total level). overrideHitPoints, when set, is a manual value that wins
    over all of the above."""
    override = data.get("overrideHitPoints")
    if override:
        return round(override)
    base = data.get("baseHitPoints") or 0
    bonus = data.get("bonusHitPoints") or 0
    if not base:
        return None
    con_mod = _ability_mod(ability_scores.get(3, 10))
    return round(base + bonus + con_mod * total_level)


def _compute_speed(data, modifiers):
    race_speeds = ((data.get("race") or {}).get("weightSpeeds") or {}).get("normal") or {}
    walk = race_speeds.get("walk")
    if walk is None:
        return None
    for m in modifiers:
        if m.get("type") == "set" and m.get("subType") == "innate-speed-walking" and m.get("value"):
            walk = m["value"]
    walk += _flat_bonus(modifiers, "speed") + _flat_bonus(modifiers, "speed-walking") + _flat_bonus(modifiers, "unarmored-movement")
    return round(walk)


def _compute_passive_perception(modifiers, ability_scores, prof_bonus):
    wis_mod = _ability_mod(ability_scores.get(5, 10))
    mult = _skill_proficiency_multiplier(modifiers, "perception")
    passive = 10 + wis_mod + math.floor(mult * prof_bonus)
    passive += _flat_bonus(modifiers, "passive-perception")
    return round(passive)


def _skills_table(modifiers, ability_scores, prof_bonus):
    """A markdown table of every skill's modifier, tagging which ones the
    character is Proficient/Expertise/Half-Proficient in -- skills with no
    training show just the plain ability modifier, same as a blank sheet."""
    lines = ["| Skill | Modifier |", "|---|---|"]
    for subtype, label, ability_id in SKILL_DEFS:
        mult = _skill_proficiency_multiplier(modifiers, subtype)
        ability_mod = _ability_mod(ability_scores.get(ability_id, 10))
        total = ability_mod + math.floor(mult * prof_bonus)
        sign = "+" if total >= 0 else ""
        tag = {2.0: " (Expertise)", 1.0: " (Proficient)", 0.5: " (Half Prof.)"}.get(mult, "")
        lines.append(f"| {label} | {sign}{total}{tag} |")
    return "\n".join(lines)


def build_entry_fields(data):
    """Turn a D&D Beyond character payload into fields for the entry form:
    name, summary, content (markdown), and avatar_url (may be empty)."""
    name = (data.get("name") or "").strip() or "Unnamed Character"

    race = data.get("race") or {}
    race_name = race.get("fullName") or race.get("baseName") or ""
    classes_text = _classes_summary(data)

    summary_bits = [b for b in [classes_text, race_name] if b]
    summary = " — ".join(summary_bits)[:200] if summary_bits else "Imported from D&D Beyond."

    background_name = ((data.get("background") or {}).get("definition") or {}).get("name", "")
    traits = data.get("traits") or {}
    backstory = (data.get("notes") or {}).get("backstory") or ""

    content_parts = []
    header_bits = [b for b in [classes_text, race_name] if b]
    if header_bits:
        content_parts.append("**" + " — ".join(header_bits) + "**")
    if background_name:
        content_parts.append(f"Background: {background_name}")

    stats_md = _stats_table(data)
    if stats_md:
        content_parts.append(stats_md)

    ability_scores = _ability_scores(data)
    modifiers = _all_modifiers(data)
    total_level_for_pb = _total_level(data)
    prof_bonus = _proficiency_bonus(total_level_for_pb)
    armor_class = None
    hit_points = None
    speed = None
    passive_perception = None
    if _has_ability_data(data):
        # Best-effort combat-stat math from the raw payload (equipped armor,
        # proficiency/expertise modifiers, race base speed, etc.) -- see the
        # _compute_*/​_skills_table helpers above for exactly what is and
        # isn't accounted for. This covers the common cases (standard
        # Light/Medium/Heavy armor + shield, Barbarian/Monk Unarmored
        # Defense, ordinary skill proficiencies) but, like any unofficial
        # parse of D&D Beyond's data, can't promise to catch every exotic
        # magic item or homebrew modifier -- worth a quick glance against
        # the real sheet after import rather than treated as gospel.
        try:
            armor_class = _compute_armor_class(data, ability_scores, modifiers)
        except Exception:
            armor_class = None
        try:
            hit_points = _compute_hit_points(data, total_level_for_pb, ability_scores)
        except Exception:
            hit_points = None
        try:
            speed = _compute_speed(data, modifiers)
        except Exception:
            speed = None
        try:
            passive_perception = _compute_passive_perception(modifiers, ability_scores, prof_bonus)
        except Exception:
            passive_perception = None

        try:
            skills_md = _skills_table(modifiers, ability_scores, prof_bonus)
            content_parts.append(skills_md)
        except Exception:
            pass

    for label, key in [
        ("Personality", "personalityTraits"),
        ("Ideals", "ideals"),
        ("Bonds", "bonds"),
        ("Flaws", "flaws"),
    ]:
        value = traits.get(key)
        if value:
            content_parts.append(f"**{label}:** {value}")

    if backstory:
        content_parts.append("## Backstory\n\n" + backstory)

    if not content_parts:
        content_parts.append("_Imported from D&D Beyond — no further details were available._")

    avatar_url = (data.get("decorations") or {}).get("avatarUrl") or race.get("portraitAvatarUrl") or ""

    char_class, subclass, level = _primary_class_info(data)
    alignment = ALIGNMENT_BY_ID.get(data.get("alignmentId"), "")
    player_name = (data.get("username") or "").strip()
    personality_traits = (traits.get("personalityTraits") or "").strip()
    # D&D Beyond's unofficial payload sometimes carries a "faith" field for a
    # character's deity/patron -- straightforward to read when present, but
    # not guaranteed across every character, hence the defensive .get.
    deity_patron = (data.get("faith") or "").strip()

    # These map straight onto the Character category's DETAIL_FIELDS columns
    # (see models.py) so the New Entry form comes up with Species/Class/
    # Subclass/Level/Alignment/Background/Player Name already filled in
    # instead of just a name and a paragraph of prose. Any value here that
    # isn't one of the form's standard dropdown options (a less common race,
    # an unusual background, a class like Artificer that isn't in the core
    # twelve) still comes through as free text — the entry form's "+ Add new
    # option..." mechanism registers it as a real dropdown option the moment
    # the entry is saved, so it's not lost or forced into "Other".
    details = {
        "species": race_name or None,
        "char_class": char_class or None,
        "subclass": subclass or None,
        "level": level,
        "alignment": alignment or None,
        "background": background_name or None,
        # D&D Beyond doesn't expose a clean "is this character dead" flag we
        # can trust, and a sheet being importable at all means it's an active
        # PC, so "Alive" / party-member are safe, easily-overridden defaults
        # rather than guesses about data that isn't really there.
        "character_status": "Alive",
        "is_player_character": "Yes",
        "player_name": player_name or None,
        "personality_traits": personality_traits or None,
        "deity_patron": deity_patron or None,
        "armor_class": armor_class,
        "hit_points": hit_points,
        "speed": speed,
        "passive_perception": passive_perception,
    }

    return {
        "name": name,
        "summary": summary,
        "content": "\n\n".join(content_parts),
        "avatar_url": avatar_url,
        "details": details,
    }
