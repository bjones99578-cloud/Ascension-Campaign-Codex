"""Import a character from D&D Beyond.

D&D Beyond has no official public API or account-linking for third-party
apps. This uses an undocumented internal endpoint that D&D Beyond staff have
explicitly said is "not a public API" and could change or stop working at
any time without notice. It only works for a character whose sheet privacy
is set to Public. Every failure path below is expected to happen eventually —
this module is written to degrade to a clear error message rather than crash
the app when that day comes.
"""
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


def _stats_table(data):
    base = {s.get("id"): s.get("value") for s in (data.get("stats") or []) if s.get("value") is not None}
    bonus = {s.get("id"): s.get("value") for s in (data.get("bonusStats") or []) if s.get("value") is not None}
    override = {s.get("id"): s.get("value") for s in (data.get("overrideStats") or []) if s.get("value") is not None}

    if not base and not override:
        return ""

    lines = ["| Ability | Score |", "|---|---|"]
    for i in range(1, 7):
        if i in override:
            value = override[i]
        else:
            value = base.get(i, 10) + bonus.get(i, 0)
        lines.append(f"| {ABILITY_NAMES[i]} | {value} |")
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
    }

    return {
        "name": name,
        "summary": summary,
        "content": "\n\n".join(content_parts),
        "avatar_url": avatar_url,
        "details": details,
    }
