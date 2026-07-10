import os
import re
import sys

from flask import Flask, g, redirect, render_template, request, send_from_directory, session, url_for
from werkzeug.exceptions import RequestEntityTooLarge

import bastion
import dndbeyond
import images
import models
from rendering import render_wiki_content

app = Flask(__name__)
if not os.environ.get("SECRET_KEY"):
    # Not fatal -- a small trusted-party app shouldn't refuse to start over
    # this -- but silent-and-insecure is worse than silent-and-loud. Session
    # cookies (currently just the DM Mode toggle and the "your name"
    # field) are signed with this key, so a known default value in the
    # public GitHub repo means anyone could forge one. This prints to
    # whatever the host's own startup/error log is (PythonAnywhere's Error
    # log, Render's log stream, etc.), so it's visible without needing to
    # go looking for it.
    print(
        "WARNING: SECRET_KEY environment variable is not set -- using the "
        "insecure default from source code. Set a real SECRET_KEY (see "
        "README.md) before real party data depends on this deployment.",
        file=sys.stderr,
    )
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-me")
# 20 MB covers even a large modern phone photo. This is just a sanity cap on
# the raw upload, not the stored file size -- images.py compresses and
# downscales every image after it's received, so a bigger raw upload here
# doesn't cost extra disk space long-term, it just avoids rejecting a
# legitimate high-res photo for no real benefit.
app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024


@app.errorhandler(RequestEntityTooLarge)
def handle_upload_too_large(e):
    """Without this, a too-large upload crashes with Flask's generic,
    unstyled 413 error page -- Werkzeug rejects the request before any view
    function (or its usual error-message handling) ever runs, so there's no
    way to redisplay the entry form with the name/summary/content the
    person already typed still filled in. The friendliest honest option is
    a clear explanation and a nudge to go back (most browsers restore
    what was typed via the back button) rather than a technical crash."""
    max_mb = app.config["MAX_CONTENT_LENGTH"] // (1024 * 1024)
    return render_template(
        "simple_message.html",
        title="That image is too large",
        message=(
            f"Uploads are limited to {max_mb} MB. Use your browser's Back "
            "button, pick a smaller image (or let your phone's camera app "
            "compress it first), and try again."
        ),
    ), 413


@app.route("/uploads/<path:filename>")
def uploaded_file(filename):
    """Serves every uploaded portrait/city-art/map image from images.UPLOAD_DIR.
    Deliberately separate from Flask's built-in /static route, which only ever
    serves files sitting inside this app's own code folder -- when UPLOAD_DIR
    is pointed at a mounted persistent disk (see images.py), that directory
    lives outside the code folder entirely, so /static can't reach it."""
    return send_from_directory(images.UPLOAD_DIR, filename)


def get_conn():
    if "db" not in g:
        g.db = models.get_db()
    return g.db


def relationship_options(conn):
    """Option lists for the Home City / Organization / Region / Headquarters
    City / Leader dropdowns on the entry form."""
    return {
        "city_options": models.list_entries(conn, category="City"),
        "organization_options": models.list_entries(conn, category="Organization"),
        "region_options": models.list_entries(conn, category="Region"),
        "character_options": models.list_entries(conn, category="Character"),
    }


def _parse_relationship_id(value):
    """Convert a <select> value (empty string or a numeric id) to int or None."""
    return int(value) if value else None


def _parse_pc_slot(conn, form, ignore_entry_id=None):
    """Read the hidden pc_slot field carried through the entry form. Returns
    None if unset/blank, or if the requested slot is already occupied by a
    different Character (defensive against stale links/back-button races) —
    the entry still saves normally, it just doesn't land in the roster."""
    raw = (form.get("pc_slot") or "").strip()
    if not raw:
        return None
    try:
        slot = int(raw)
    except ValueError:
        return None
    if not (1 <= slot <= models.PARTY_SLOT_COUNT):
        return None
    holder = conn.execute(
        "SELECT id FROM entry WHERE pc_slot = ?", (slot,)
    ).fetchone()
    if holder and holder["id"] != ignore_entry_id:
        return None
    return slot


def parse_detail_fields(form):
    """Read the typical D&D detail fields (Species, Class, Alignment, Population,
    etc.) out of a submitted form, keyed by their DB column name. Numeric columns
    are converted to int (or None if blank/invalid); everything else is stripped
    text (or None if blank). "__add_new__" is the entry form's sentinel value for
    a select whose "+ Add new option..." control was picked -- normally client-side
    JS swaps it out for the typed-in text before submit, but if that never ran
    (JS disabled) treat it the same as blank rather than saving the literal sentinel.
    """
    details = {}
    for col in models.DETAIL_COLUMNS:
        raw = (form.get(col) or "").strip()
        if raw == "__add_new__":
            raw = ""
        if col in models.DETAIL_INT_COLUMNS:
            try:
                details[col] = int(raw) if raw else None
            except ValueError:
                details[col] = None
        else:
            details[col] = raw or None
    return details


def _persist_custom_options(conn, details):
    """Any select-field value in a saved entry that isn't one of the built-in
    options gets saved as a new custom option (see models.add_custom_option),
    so typing "Beastmaster" into the Class field once means every future
    Character entry can just pick "Beastmaster" from the dropdown."""
    for field_name, value in details.items():
        models.add_custom_option(conn, field_name, value)


@app.teardown_appcontext
def close_conn(exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


@app.context_processor
def inject_globals():
    conn = get_conn()
    return {
        "categories": models.CATEGORIES,
        "category_plurals": models.CATEGORY_PLURALS,
        "category_labels": models.CATEGORY_LABELS,
        "category_counts": models.category_counts(conn),
        "current_author": session.get("display_name", ""),
        "detail_fields": models.merged_detail_fields(conn),
        "subclass_options_by_class": models.SUBCLASS_OPTIONS_BY_CLASS,
    }


@app.route("/")
def index():
    conn = get_conn()
    recent = conn.execute(
        "SELECT * FROM entry ORDER BY updated_at DESC LIMIT 8"
    ).fetchall()
    # The homepage preview always shows whichever map is first in sort_order
    # -- the same one /map falls back to when no ?map_id= is given -- so
    # clicking through lands on the map you'd expect from the thumbnail.
    maps = models.list_maps(conn)
    preview_map = maps[0] if maps else None
    return render_template("index.html", recent=recent, preview_map=preview_map)


@app.route("/category/<category>")
def category_view(category):
    """The per-category listing page. Renders as a proper table of that
    category's typical fields rather than a bare name+summary list, since a
    table reads far better once there's more than a couple of entries.
    Characters additionally get split into Party Members vs. everyone else so
    the party's core cast doesn't get lost among NPCs; a few categories also
    need relationship ids (Home City, Region, Headquarters City, Leader)
    resolved to real names for their table's columns."""
    conn = get_conn()
    if category not in models.CATEGORIES:
        return redirect(url_for("index"))
    entries = models.list_entries(conn, category=category)
    if category == "SessionLog":
        # A session log reads best in chronological order, most recent
        # first -- not the alphabetical-by-name order every other category
        # uses, since entry names here are freeform ("Session 12", "The
        # Night the Tower Fell") rather than something that sorts usefully.
        entries = sorted(
            entries,
            key=lambda e: (e["session_date"] or "", e["session_number"] or 0, e["id"]),
            reverse=True,
        )

    party_members = []
    npcs = []
    related_names = {}

    if category == "Character":
        cities = models.get_entries_by_ids(conn, [e["home_city_id"] for e in entries])
        rows = [{"entry": e, "home_city": cities.get(e["home_city_id"])} for e in entries]
        party_members = [r for r in rows if r["entry"]["is_player_character"] == "Yes"]
        npcs = [r for r in rows if r["entry"]["is_player_character"] != "Yes"]
    elif category == "City":
        regions = models.get_entries_by_ids(conn, [e["region_id"] for e in entries])
        related_names = {e["id"]: {"region": regions.get(e["region_id"])} for e in entries}
    elif category == "Organization":
        cities = models.get_entries_by_ids(conn, [e["headquarters_city_id"] for e in entries])
        leaders = models.get_entries_by_ids(conn, [e["leader_id"] for e in entries])
        related_names = {
            e["id"]: {
                "headquarters_city": cities.get(e["headquarters_city_id"]),
                "leader": leaders.get(e["leader_id"]),
            }
            for e in entries
        }
    elif category == "Item":
        holders = models.get_entries_by_ids(conn, [e["current_holder_id"] for e in entries])
        related_names = {e["id"]: {"current_holder": holders.get(e["current_holder_id"])} for e in entries}

    return render_template(
        "category.html",
        category=category,
        entries=entries,
        party_members=party_members,
        npcs=npcs,
        related_names=related_names,
    )


@app.route("/search")
def search():
    """Free-text search across name/summary/content, optionally narrowed by
    Category and (once a Category is picked) that category's own select-type
    fields -- Disposition, Status, Difficulty, Rarity, and so on. Filters are
    only ever applied for whichever category is selected (there's no single
    universal "Status" column -- each category's Status lives in its own
    differently-named column, per DETAIL_FIELDS), and any filter left on
    "Any" is simply omitted rather than sent as an empty-string constraint."""
    conn = get_conn()
    q = request.args.get("q", "").strip()
    category = request.args.get("category", "").strip()
    if category not in models.CATEGORIES:
        category = ""
    merged_fields = models.merged_detail_fields(conn)
    category_filter_fields = [
        f for f in merged_fields.get(category, []) if f["type"] == "select"
    ] if category else []
    active_filters = {
        f["name"]: request.args.get(f["name"], "").strip()
        for f in category_filter_fields
    }
    active_filters = {k: v for k, v in active_filters.items() if v}
    searched = bool(q or category or active_filters)
    results = (
        models.list_entries(conn, category=category or None, query=q or None, filters=active_filters)
        if searched
        else []
    )
    return render_template(
        "search.html",
        query=q,
        category=category,
        category_filter_fields=category_filter_fields,
        active_filters=active_filters,
        searched=searched,
        results=results,
    )


@app.route("/entry/<int:entry_id>")
def entry_detail(entry_id):
    conn = get_conn()
    entry = models.get_entry(conn, entry_id)
    if entry is None:
        return render_template("not_found.html"), 404
    rendered = render_wiki_content(entry["content"], conn, exclude_name=entry["name"])
    all_backlinks = models.get_backlinks(conn, entry_id)

    related = None
    backlinks = all_backlinks
    if entry["category"] == "City":
        # Cities get their linked Characters, Organizations, and Quests broken
        # out into their own tables — populated both from the explicit Home
        # City / Headquarters City dropdowns and from [[City Name]] wiki-link
        # backlinks, merged and de-duplicated. Anything else that links here
        # (an Item, another City) still shows up below as a
        # general backlink so nothing gets lost. Characters are additionally
        # split into Party Members vs. everyone else for clarity, matching
        # the same split used on the Characters category page and City View.
        character_stubs = models.merge_by_id(
            models.get_characters_in_city(conn, entry_id),
            [b for b in all_backlinks if b["category"] == "Character"],
        )
        characters = [models.get_entry(conn, row["id"]) for row in character_stubs]
        party_characters, npc_characters = models.split_party_members(characters)

        faction_stubs = models.merge_by_id(
            models.get_organizations_in_city(conn, entry_id),
            [b for b in all_backlinks if b["category"] == "Organization"],
        )
        factions_display = []
        for stub in faction_stubs:
            org = models.get_entry(conn, stub["id"])
            leader = models.get_entry(conn, org["leader_id"]) if org["leader_id"] else None
            factions_display.append({"entry": org, "leader": leader})

        quests_display = [
            models.get_entry(conn, b["id"]) for b in all_backlinks if b["category"] == "Quest"
        ]

        related = {
            "party_characters": party_characters,
            "npc_characters": npc_characters,
            "factions_display": factions_display,
            "quests_display": quests_display,
        }
        backlinks = [
            b for b in all_backlinks
            if b["category"] not in ("Character", "Organization", "Quest")
        ]
    elif entry["category"] == "Organization":
        member_stubs = models.merge_by_id(
            models.get_characters_in_organization(conn, entry_id),
            [b for b in all_backlinks if b["category"] == "Character"],
        )
        members = [models.get_entry(conn, row["id"]) for row in member_stubs]
        party_members, npc_members = models.split_party_members(members)

        related = {
            "party_members": party_members,
            "npc_members": npc_members,
        }
        backlinks = [b for b in all_backlinks if b["category"] != "Character"]
    elif entry["category"] == "Region":
        city_stubs = models.merge_by_id(
            models.get_cities_in_region(conn, entry_id),
            [b for b in all_backlinks if b["category"] == "City"],
        )
        cities_display = [models.get_entry(conn, row["id"]) for row in city_stubs]
        related = {"cities_display": cities_display}
        backlinks = [b for b in all_backlinks if b["category"] != "City"]
    elif entry["category"] == "Character":
        # A Character's own page gets a "Carried Items" table, the mirror of
        # each Item's own Current Holder dropdown -- so a party member's page
        # shows everything they're holding at a glance, the same
        # dropdown-plus-backlink merge pattern used everywhere else.
        item_stubs = models.merge_by_id(
            models.get_items_held_by(conn, entry_id),
            [b for b in all_backlinks if b["category"] == "Item"],
        )
        carried_items = [models.get_entry(conn, row["id"]) for row in item_stubs]
        related = {"carried_items": carried_items}
        backlinks = [b for b in all_backlinks if b["category"] != "Item"]

    related_entities = {}
    if entry["category"] == "Character":
        if entry["home_city_id"]:
            related_entities["home_city"] = models.get_entry(conn, entry["home_city_id"])
        if entry["organization_id"]:
            related_entities["organization"] = models.get_entry(conn, entry["organization_id"])
        if entry["current_city_id"]:
            related_entities["current_city"] = models.get_entry(conn, entry["current_city_id"])
    elif entry["category"] == "City":
        if entry["region_id"]:
            related_entities["region"] = models.get_entry(conn, entry["region_id"])
        if entry["leader_id"]:
            related_entities["leader"] = models.get_entry(conn, entry["leader_id"])
        if entry["leading_organization_id"]:
            related_entities["leading_organization"] = models.get_entry(conn, entry["leading_organization_id"])
    elif entry["category"] == "Organization":
        if entry["headquarters_city_id"]:
            related_entities["headquarters_city"] = models.get_entry(conn, entry["headquarters_city_id"])
        if entry["leader_id"]:
            related_entities["leader"] = models.get_entry(conn, entry["leader_id"])
    elif entry["category"] == "Item":
        if entry["current_holder_id"]:
            related_entities["current_holder"] = models.get_entry(conn, entry["current_holder_id"])

    # Personal crafting/downtime projects are a Player Character thing only
    # (an NPC has no "party member" tracking anything for themselves) --
    # projects is left undefined for every other entry so the template can
    # gate the whole section on it existing at all.
    projects = None
    if entry["category"] == "Character" and entry["is_player_character"] == "Yes":
        projects = models.get_projects(conn, "character", entry_id)

    return render_template(
        "entry_detail.html",
        entry=entry,
        rendered=rendered,
        backlinks=backlinks,
        related=related,
        related_entities=related_entities,
        projects=projects,
    )


@app.route("/new", methods=["GET", "POST"])
def new_entry():
    conn = get_conn()
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        category = request.form.get("category", models.CATEGORIES[0])
        summary = request.form.get("summary", "").strip()
        content = request.form.get("content", "")
        author = request.form.get("author", "").strip()
        # Set when a D&D Beyond import (or a failed submit) already downloaded/
        # carried forward an image before this entry existed in the database.
        existing_image_filename = request.form.get("existing_image_filename") or None
        remove_image = request.form.get("remove_image") == "1"
        home_city_id = _parse_relationship_id(request.form.get("home_city"))
        organization_id = _parse_relationship_id(request.form.get("organization"))
        region_id = _parse_relationship_id(request.form.get("region"))
        headquarters_city_id = _parse_relationship_id(request.form.get("headquarters_city"))
        leader_id = _parse_relationship_id(request.form.get("leader"))
        current_city_id = _parse_relationship_id(request.form.get("current_city"))
        leading_organization_id = _parse_relationship_id(request.form.get("leading_organization"))
        current_holder_id = _parse_relationship_id(request.form.get("current_holder"))
        pc_slot = _parse_pc_slot(conn, request.form)
        details = parse_detail_fields(request.form)
        _persist_custom_options(conn, details)
        error = None
        if not name:
            error = "Please give this entry a name."
        elif models.find_entry_by_name(conn, name):
            error = f'An entry named "{name}" already exists.'
        if error:
            return render_template(
                "entry_form.html",
                mode="new",
                error=error,
                form={
                    "name": name,
                    "category": category,
                    "summary": summary,
                    "content": content,
                    "author": author,
                    "image_filename": None if remove_image else existing_image_filename,
                    "home_city_id": home_city_id,
                    "organization_id": organization_id,
                    "region_id": region_id,
                    "headquarters_city_id": headquarters_city_id,
                    "leader_id": leader_id,
                    "current_city_id": current_city_id,
                    "leading_organization_id": leading_organization_id,
                    "pc_slot": pc_slot,
                    **details,
                },
                **relationship_options(conn),
            )

        new_image_filename = images.save_upload(request.files.get("image"))
        if new_image_filename:
            if existing_image_filename and existing_image_filename != new_image_filename:
                images.delete_upload(existing_image_filename)
            image_filename = new_image_filename
        elif remove_image:
            if existing_image_filename:
                images.delete_upload(existing_image_filename)
            image_filename = None
        else:
            image_filename = existing_image_filename

        session["display_name"] = author
        entry_id = models.create_entry(
            conn, name, category, summary, content, author, image_filename,
            home_city_id=home_city_id, organization_id=organization_id,
            region_id=region_id, headquarters_city_id=headquarters_city_id,
            leader_id=leader_id, current_city_id=current_city_id,
            leading_organization_id=leading_organization_id,
            current_holder_id=current_holder_id,
            pc_slot=pc_slot,
            details=details,
        )
        return redirect(url_for("entry_detail", entry_id=entry_id))

    prefill_name = request.args.get("name", "")
    prefill_category = request.args.get("category", models.CATEGORIES[0])
    prefill_slot = request.args.get("pc_slot", type=int)
    prefill_details = models.empty_details()
    if prefill_slot:
        prefill_details["is_player_character"] = "Yes"
    return render_template(
        "entry_form.html",
        mode="new",
        error=None,
        form={
            "name": prefill_name,
            "category": prefill_category,
            "summary": "",
            "content": "",
            "author": session.get("display_name", ""),
            "image_filename": None,
            "home_city_id": None,
            "organization_id": None,
            "region_id": None,
            "headquarters_city_id": None,
            "leader_id": None,
            "current_city_id": None,
            "leading_organization_id": None,
            "current_holder_id": None,
            "pc_slot": prefill_slot,
            **prefill_details,
        },
        **relationship_options(conn),
    )


@app.route("/import/dndbeyond", methods=["GET", "POST"])
def import_dndbeyond():
    error = None
    if request.method == "POST":
        raw = request.form.get("dndbeyond_url", "")
        character_id = dndbeyond.extract_character_id(raw)
        if not character_id:
            error = (
                'Couldn\'t find a character ID in that. Paste the full D&D Beyond '
                'character URL (e.g. https://www.dndbeyond.com/characters/123456789) '
                'or just the ID number.'
            )
        else:
            try:
                data = dndbeyond.fetch_character(character_id)
                fields = dndbeyond.build_entry_fields(data)
                image_filename = images.save_from_url(fields.get("avatar_url"))
                return render_template(
                    "entry_form.html",
                    mode="new",
                    error=None,
                    imported=True,
                    form={
                        "name": fields["name"],
                        "category": "Character",
                        "summary": fields["summary"],
                        "content": fields["content"],
                        "author": session.get("display_name", ""),
                        "image_filename": image_filename,
                        "home_city_id": None,
                        "organization_id": None,
                        "region_id": None,
                        "headquarters_city_id": None,
                        "leader_id": None,
                        "current_city_id": None,
                        "leading_organization_id": None,
                        "current_holder_id": None,
                                    "pc_slot": None,
                        **{**models.empty_details(), **fields.get("details", {})},
                    },
                    **relationship_options(get_conn()),
                )
            except dndbeyond.DndBeyondError as exc:
                error = str(exc)
    return render_template("import_dndbeyond.html", error=error)


@app.route("/entry/<int:entry_id>/edit", methods=["GET", "POST"])
def edit_entry(entry_id):
    conn = get_conn()
    entry = models.get_entry(conn, entry_id)
    if entry is None:
        return render_template("not_found.html"), 404

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        category = request.form.get("category", entry["category"])
        summary = request.form.get("summary", "").strip()
        content = request.form.get("content", "")
        author = request.form.get("author", "").strip()
        remove_image = request.form.get("remove_image") == "1"
        home_city_id = _parse_relationship_id(request.form.get("home_city"))
        organization_id = _parse_relationship_id(request.form.get("organization"))
        region_id = _parse_relationship_id(request.form.get("region"))
        headquarters_city_id = _parse_relationship_id(request.form.get("headquarters_city"))
        leader_id = _parse_relationship_id(request.form.get("leader"))
        current_city_id = _parse_relationship_id(request.form.get("current_city"))
        leading_organization_id = _parse_relationship_id(request.form.get("leading_organization"))
        current_holder_id = _parse_relationship_id(request.form.get("current_holder"))
        pc_slot = _parse_pc_slot(conn, request.form, ignore_entry_id=entry_id)
        details = parse_detail_fields(request.form)
        _persist_custom_options(conn, details)
        error = None
        if not name:
            error = "Please give this entry a name."
        else:
            existing = models.find_entry_by_name(conn, name)
            if existing and existing["id"] != entry_id:
                error = f'Another entry named "{name}" already exists.'
        if error:
            return render_template(
                "entry_form.html",
                mode="edit",
                entry_id=entry_id,
                error=error,
                form={
                    "name": name,
                    "category": category,
                    "summary": summary,
                    "content": content,
                    "author": author,
                    "image_filename": entry["image_filename"],
                    "home_city_id": home_city_id,
                    "organization_id": organization_id,
                    "region_id": region_id,
                    "headquarters_city_id": headquarters_city_id,
                    "leader_id": leader_id,
                    "current_city_id": current_city_id,
                    "leading_organization_id": leading_organization_id,
                    "current_holder_id": current_holder_id,
                    "pc_slot": pc_slot,
                    **details,
                },
                **relationship_options(conn),
            )
        session["display_name"] = author

        new_image_filename = images.save_upload(request.files.get("image"))
        if new_image_filename:
            if entry["image_filename"]:
                images.delete_upload(entry["image_filename"])
            models.update_entry(
                conn, entry_id, name, category, summary, content, author, new_image_filename,
                home_city_id=home_city_id, organization_id=organization_id,
                region_id=region_id, headquarters_city_id=headquarters_city_id,
                leader_id=leader_id, current_city_id=current_city_id,
                leading_organization_id=leading_organization_id,
                current_holder_id=current_holder_id,
                pc_slot=pc_slot,
                details=details,
            )
        elif remove_image and entry["image_filename"]:
            images.delete_upload(entry["image_filename"])
            models.clear_entry_image(conn, entry_id)
            models.update_entry(
                conn, entry_id, name, category, summary, content, author,
                home_city_id=home_city_id, organization_id=organization_id,
                region_id=region_id, headquarters_city_id=headquarters_city_id,
                leader_id=leader_id, current_city_id=current_city_id,
                leading_organization_id=leading_organization_id,
                current_holder_id=current_holder_id,
                pc_slot=pc_slot,
                details=details,
            )
        else:
            models.update_entry(
                conn, entry_id, name, category, summary, content, author,
                home_city_id=home_city_id, organization_id=organization_id,
                region_id=region_id, headquarters_city_id=headquarters_city_id,
                leader_id=leader_id, current_city_id=current_city_id,
                leading_organization_id=leading_organization_id,
                current_holder_id=current_holder_id,
                pc_slot=pc_slot,
                details=details,
            )

        return redirect(url_for("entry_detail", entry_id=entry_id))

    return render_template(
        "entry_form.html",
        mode="edit",
        entry_id=entry_id,
        error=None,
        form={
            "name": entry["name"],
            "category": entry["category"],
            "summary": entry["summary"],
            "content": entry["content"],
            "author": entry["author"] or session.get("display_name", ""),
            "image_filename": entry["image_filename"],
            "home_city_id": entry["home_city_id"],
            "organization_id": entry["organization_id"],
            "region_id": entry["region_id"],
            "headquarters_city_id": entry["headquarters_city_id"],
            "leader_id": entry["leader_id"],
            "current_city_id": entry["current_city_id"],
            "leading_organization_id": entry["leading_organization_id"],
            "current_holder_id": entry["current_holder_id"],
            "pc_slot": entry["pc_slot"],
            **{col: entry[col] for col in models.DETAIL_COLUMNS},
        },
        **relationship_options(conn),
    )


@app.route("/entry/<int:entry_id>/delete", methods=["POST"])
def delete_entry_route(entry_id):
    conn = get_conn()
    entry = models.get_entry(conn, entry_id)
    if entry and entry["image_filename"]:
        images.delete_upload(entry["image_filename"])
    models.delete_entry(conn, entry_id)
    return redirect(url_for("index"))


@app.route("/city-view")
def city_view():
    """A single page with a city dropdown that pulls together everything about
    whichever city is selected — its own fields, its write-up, and every
    Character/Organization connected to it (via dropdown or wiki-link) — so a
    DM can flip between cities during a session without clicking through
    separate entry pages."""
    conn = get_conn()
    cities = models.list_entries(conn, category="City")

    city_id = request.args.get("city_id", type=int)
    if city_id is None and cities:
        city_id = cities[0]["id"]

    selected_city = models.get_entry(conn, city_id) if city_id else None
    if selected_city is not None and selected_city["category"] != "City":
        selected_city = None

    region = None
    characters = []
    party_characters = []
    npc_characters = []
    organizations_display = []
    rendered_summary = ""

    if selected_city is not None:
        if selected_city["region_id"]:
            region = models.get_entry(conn, selected_city["region_id"])

        all_backlinks = models.get_backlinks(conn, selected_city["id"])

        char_stubs = models.merge_by_id(
            models.get_characters_in_city(conn, selected_city["id"]),
            [b for b in all_backlinks if b["category"] == "Character"],
        )
        characters = [models.get_entry(conn, row["id"]) for row in char_stubs]
        party_characters, npc_characters = models.split_party_members(characters)

        org_stubs = models.merge_by_id(
            models.get_organizations_in_city(conn, selected_city["id"]),
            [b for b in all_backlinks if b["category"] == "Organization"],
        )
        for stub in org_stubs:
            org = models.get_entry(conn, stub["id"])
            leader = models.get_entry(conn, org["leader_id"]) if org["leader_id"] else None
            organizations_display.append({"entry": org, "leader": leader})

        if selected_city["content"]:
            rendered_summary = render_wiki_content(selected_city["content"], conn, exclude_name=selected_city["name"])

    return render_template(
        "city_view.html",
        cities=cities,
        selected_city=selected_city,
        region=region,
        characters=characters,
        party_characters=party_characters,
        npc_characters=npc_characters,
        organizations_display=organizations_display,
        rendered_summary=rendered_summary,
    )


@app.route("/party")
def party_roster():
    """The Player Characters tab: a fixed 5-slot party roster, each slot
    either showing its assigned Character (portrait, build, current/home
    city, key item — themed by Class) or an empty-slot card offering to
    create a new Character or assign an existing unassigned party member."""
    conn = get_conn()
    pcs = models.get_player_characters(conn)
    by_slot = {pc["pc_slot"]: pc for pc in pcs if pc["pc_slot"]}
    unassigned = [pc for pc in pcs if not pc["pc_slot"]]

    slot_cards = []
    for slot_num in range(1, models.PARTY_SLOT_COUNT + 1):
        pc = by_slot.get(slot_num)
        home_city = models.get_entry(conn, pc["home_city_id"]) if pc and pc["home_city_id"] else None
        current_city = models.get_entry(conn, pc["current_city_id"]) if pc and pc["current_city_id"] else None
        slot_cards.append({
            "slot": slot_num,
            "character": pc,
            "home_city": home_city,
            "current_city": current_city,
            "theme_slug": models.CLASS_THEME_SLUGS.get(pc["char_class"]) if pc else None,
        })

    return render_template("party.html", slot_cards=slot_cards, unassigned=unassigned)


@app.route("/party/assign", methods=["POST"])
def party_assign():
    conn = get_conn()
    slot = request.form.get("slot", type=int)
    character_id = request.form.get("character_id", type=int)
    if slot and character_id and 1 <= slot <= models.PARTY_SLOT_COUNT:
        holder = conn.execute("SELECT id FROM entry WHERE pc_slot = ?", (slot,)).fetchone()
        character = models.get_entry(conn, character_id)
        if (
            not holder and character
            and character["category"] == "Character"
            and character["is_player_character"] == "Yes"
        ):
            conn.execute("UPDATE entry SET pc_slot = ? WHERE id = ?", (slot, character_id))
            conn.commit()
    return redirect(url_for("party_roster"))


@app.route("/party/unassign", methods=["POST"])
def party_unassign():
    conn = get_conn()
    character_id = request.form.get("character_id", type=int)
    if character_id:
        conn.execute("UPDATE entry SET pc_slot = NULL WHERE id = ?", (character_id,))
        conn.commit()
    return redirect(url_for("party_roster"))


@app.route("/reference")
def reference():
    """A quick in-site lookup page for the 2024-ruleset Species and Classes
    used throughout the entry form's dropdowns -- a few sentences of original
    flavor per option (not book text) plus each Class's 4 subclass names, so
    nobody has to leave the site or dig out a physical Player's Handbook just
    to jog their memory on what a species or class is about."""
    species = [
        {"name": name, "blurb": models.SPECIES_BLURBS.get(name, "")}
        for name in models.SPECIES_OPTIONS
        if name != "Other/Homebrew"
    ]
    classes = [
        {
            "name": name,
            "blurb": models.CLASS_BLURBS.get(name, ""),
            "subclasses": models.SUBCLASS_OPTIONS_BY_CLASS.get(name, []),
            "theme_slug": models.CLASS_THEME_SLUGS.get(name),
        }
        for name in models.CLASS_OPTIONS
        if name != "Other/Homebrew"
    ]
    return render_template("reference.html", species=species, classes=classes)


def _loot_field_options(conn):
    """Just the option lists the Loot Tracker's inline-editable rows need
    (Item Type / Rarity / Status), including any custom values the party
    has typed in elsewhere via "+ Add new option...", keyed by field name
    for easy lookup in the template."""
    item_fields = models.merged_detail_fields(conn)["Item"]
    return {f["name"]: f["options"] for f in item_fields if f["type"] == "select"}


@app.route("/loot")
def loot_tracker():
    """The party's SHARED stash only -- every Item with no Current Holder
    set, editable right on this page (quick-add a new item, or update an
    existing row's Type/Quantity/Rarity/Value/Status and save it) without
    detouring through the full Entry form. An item assigned to a specific
    Character or NPC is that individual's own belonging, not party loot, so
    it drops off this list the moment a Current Holder is set on it (it's
    still viewable/editable on its own entry page, and on that holder's
    "Carried Items" list). Only items marked "In Possession" (or left with
    no Status at all, e.g. before this field existed) count toward the
    running gold total; Sold/Given Away/Used/Destroyed/Lost items still
    show up, but as history rather than current wealth."""
    conn = get_conn()
    items = models.get_shared_loot_items(conn)
    total_value = sum(
        item["estimated_value"] or 0
        for item in items
        if item["item_status"] in (None, "", "In Possession")
    )
    return render_template(
        "loot.html",
        items=items,
        total_value=total_value,
        field_options=_loot_field_options(conn),
        error=request.args.get("error"),
    )


@app.route("/loot/items", methods=["POST"])
def loot_item_add():
    """The Loot Tracker's own "+ Add Item" row -- creates a brand-new shared
    Item entry (no Current Holder, so it shows up in the list immediately)
    without going through the full New Entry form. Falls back to that full
    form via the name-collision error message's own wording, same as the
    main New Entry flow, for anything this quick form can't resolve."""
    conn = get_conn()
    name = request.form.get("name", "").strip()
    if not name:
        return redirect(url_for("loot_tracker", error="Give the new item a name."))
    if models.find_entry_by_name(conn, name):
        return redirect(url_for("loot_tracker", error=f'An entry named "{name}" already exists.'))

    item_type = (request.form.get("item_type") or "").strip() or None
    rarity = (request.form.get("rarity") or "").strip() or None
    item_status = (request.form.get("item_status") or "").strip() or None
    quantity = request.form.get("quantity", type=int) or 1
    estimated_value = request.form.get("estimated_value", type=int)

    for field_name, value in (("item_type", item_type), ("rarity", rarity), ("item_status", item_status)):
        models.add_custom_option(conn, field_name, value)

    models.create_entry(
        conn, name, "Item", "", "", session.get("display_name", ""),
        details={
            **models.empty_details(),
            "item_type": item_type,
            "rarity": rarity,
            "item_status": item_status,
            "quantity": quantity,
            "estimated_value": estimated_value,
        },
    )
    return redirect(url_for("loot_tracker"))


@app.route("/loot/items/<int:item_id>/update", methods=["POST"])
def loot_item_update(item_id):
    """Saves one inline-editable Loot Tracker row. Scoped to Items only (via
    models.update_item_loot_fields' own WHERE clause) so posting a stray/
    tampered id for some other category's entry can't touch it."""
    conn = get_conn()
    entry = models.get_entry(conn, item_id)
    if not entry or entry["category"] != "Item":
        return redirect(url_for("loot_tracker"))

    name = request.form.get("name", "").strip() or entry["name"]
    existing = models.find_entry_by_name(conn, name)
    if existing and existing["id"] != item_id:
        return redirect(url_for("loot_tracker", error=f'An entry named "{name}" already exists.'))

    item_type = (request.form.get("item_type") or "").strip() or None
    rarity = (request.form.get("rarity") or "").strip() or None
    item_status = (request.form.get("item_status") or "").strip() or None
    quantity = request.form.get("quantity", type=int) or 1
    estimated_value = request.form.get("estimated_value", type=int)

    for field_name, value in (("item_type", item_type), ("rarity", rarity), ("item_status", item_status)):
        models.add_custom_option(conn, field_name, value)

    models.update_item_loot_fields(conn, item_id, name, item_type, quantity, rarity, estimated_value, item_status)
    return redirect(url_for("loot_tracker"))


@app.route("/loot/items/<int:item_id>/delete", methods=["POST"])
def loot_item_delete(item_id):
    """A Loot Tracker-scoped delete that redirects back here instead of to
    the homepage (unlike the generic entry-delete route), so removing a
    row doesn't bounce you away from the page you were editing."""
    conn = get_conn()
    entry = models.get_entry(conn, item_id)
    if entry and entry["category"] == "Item":
        if entry["image_filename"]:
            images.delete_upload(entry["image_filename"])
        models.delete_entry(conn, item_id)
    return redirect(url_for("loot_tracker"))


@app.route("/bastion")
def bastion_page():
    """The party's shared Bastion (their floating cloud ship) -- a level
    setting drives how many Special Facility slots are unlocked (2 at
    level 5, 4 at 9, 5 at 13, 6 at 17, per the DMG), each slot lets you pick
    an official facility type (or a wholly custom homebrew one) and name
    the built instance, and there's a reference/rename section for
    retheming the official facility types themselves. No live D&D Beyond
    source exists for any of this (see bastion.py's own docstring) -- it's
    all hand-entered 2024 DMG rules text plus whatever the party overrides."""
    conn = get_conn()
    level = int(models.get_setting(conn, "bastion_level", "5") or 5)
    name = models.get_setting(conn, "bastion_name", "") or ""
    basic_facilities = models.get_bastion_facilities(conn, "Basic")
    special_facilities = models.get_bastion_facilities(conn, "Special")
    facility_types = bastion.merged_facility_types(conn)
    available_special = [f for f in facility_types["special"] if f["level"] <= level]
    facility_types_by_key = {f["key"]: f for f in facility_types["basic"] + facility_types["special"]}
    # Each Special Facility gets its own Order-progress project, one at a
    # time -- fetched up front (rather than per-row in the template) so the
    # template only ever does a dict lookup, never its own query.
    facility_projects = {
        f["id"]: models.get_projects(conn, "bastion_facility", f["id"]) for f in special_facilities
    }
    return render_template(
        "bastion.html",
        bastion_level=level,
        bastion_name=name,
        basic_facilities=basic_facilities,
        special_facilities=special_facilities,
        facility_types=facility_types,
        facility_types_by_key=facility_types_by_key,
        available_special_types=available_special,
        special_slots_total=bastion.special_slot_count(level),
        order_options=bastion.ORDER_OPTIONS,
        facility_level_tiers=bastion.FACILITY_LEVEL_TIERS,
        facility_projects=facility_projects,
    )


@app.route("/bastion/settings", methods=["POST"])
def bastion_settings_update():
    conn = get_conn()
    name = request.form.get("bastion_name", "").strip()
    level = request.form.get("bastion_level", type=int) or 1
    level = max(1, min(20, level))
    models.set_setting(conn, "bastion_name", name)
    models.set_setting(conn, "bastion_level", str(level))
    return redirect(url_for("bastion_page"))


@app.route("/bastion/facilities", methods=["POST"])
def bastion_facility_add():
    """Adds one fresh, still-unpicked slot -- Basic slots are unrestricted
    (the DMG doesn't level-gate buying more of these), Special slots are
    capped to whatever the current Bastion level allows, matching the
    dropdown's own filtering rather than trusting the client not to have
    hidden a maxed-out "+ Add" button."""
    conn = get_conn()
    slot_category = request.form.get("slot_category")
    if slot_category not in ("Basic", "Special"):
        return redirect(url_for("bastion_page"))
    if slot_category == "Special":
        level = int(models.get_setting(conn, "bastion_level", "5") or 5)
        existing = len(models.get_bastion_facilities(conn, "Special"))
        if existing >= bastion.special_slot_count(level):
            return redirect(url_for("bastion_page"))
    models.add_bastion_facility(conn, slot_category)
    return redirect(url_for("bastion_page"))


@app.route("/bastion/facilities/<int:facility_id>/update", methods=["POST"])
def bastion_facility_update(facility_id):
    conn = get_conn()
    facility = models.get_bastion_facility(conn, facility_id)
    if not facility:
        return redirect(url_for("bastion_page"))

    facility_key = (request.form.get("facility_key") or "").strip() or None
    custom_type_name = (request.form.get("custom_type_name") or "").strip() or None
    if facility_key == "__custom__":
        facility_key = None
    else:
        custom_type_name = None
    instance_name = (request.form.get("instance_name") or "").strip() or None
    current_order = (request.form.get("current_order") or "").strip() or None
    hirelings = (request.form.get("hirelings") or "").strip() or None
    notes = (request.form.get("notes") or "").strip() or None

    models.update_bastion_facility(
        conn, facility_id, facility_key, custom_type_name, instance_name,
        current_order, hirelings, notes,
    )
    return redirect(url_for("bastion_page"))


@app.route("/bastion/facilities/<int:facility_id>/delete", methods=["POST"])
def bastion_facility_delete(facility_id):
    conn = get_conn()
    models.delete_bastion_facility(conn, facility_id)
    return redirect(url_for("bastion_page"))


@app.route("/bastion/facility-types/<facility_key>/update", methods=["POST"])
def bastion_facility_type_update(facility_key):
    """Renames/re-describes an official facility TYPE for the whole party --
    e.g. retheming "Arcane Study" into "The Sky Loom" for a homebrew
    airship. Affects every slot using that type, not just one instance."""
    conn = get_conn()
    if facility_key not in bastion.ALL_BY_KEY:
        return redirect(url_for("bastion_page"))
    models.set_bastion_facility_type_override(
        conn, facility_key,
        request.form.get("custom_name", ""),
        request.form.get("custom_description", ""),
    )
    return redirect(url_for("bastion_page"))


def _safe_next(fallback_endpoint="index"):
    """Every project form carries a hidden 'next' field so Save/Delete lands
    the party back on whichever page they were on (the Bastion, or a
    Character's own page) instead of a hardcoded route. Only ever trusts a
    same-site relative path (starts with a single '/') -- anything else
    (a bare form submitted from somewhere unexpected) falls back to the
    homepage rather than redirecting off-site."""
    next_url = request.form.get("next", "")
    if next_url.startswith("/") and not next_url.startswith("//"):
        return next_url
    return url_for(fallback_endpoint)


@app.route("/projects", methods=["POST"])
def project_add():
    """Starts a new trackable project -- either a Bastion Special Facility's
    current Order (owner_type='bastion_facility') or a Player Character's own
    personal crafting project (owner_type='character'). A facility is capped
    at one active (incomplete) project at a time to match its single Current
    Order; Characters can run as many at once as they like."""
    conn = get_conn()
    owner_type = request.form.get("owner_type")
    owner_id = request.form.get("owner_id", type=int)
    if owner_type not in models.PROJECT_OWNER_TYPES or not owner_id:
        return redirect(_safe_next())
    if owner_type == "bastion_facility":
        facility = models.get_bastion_facility(conn, owner_id)
        if not facility or models.has_incomplete_project(conn, owner_type, owner_id):
            return redirect(_safe_next())
    models.add_project(
        conn, owner_type, owner_id,
        request.form.get("name", ""),
        request.form.get("unit", "days"),
        request.form.get("target_amount", type=int),
        request.form.get("notes", ""),
    )
    return redirect(_safe_next())


@app.route("/projects/<int:project_id>/update", methods=["POST"])
def project_update(project_id):
    """Edits a project's name/goal/notes -- the counterpart to the checklist
    boxes and counter field below, which only ever touch progress_amount."""
    conn = get_conn()
    models.update_project(
        conn, project_id,
        request.form.get("name", ""),
        request.form.get("unit", "days"),
        request.form.get("target_amount", type=int),
        request.form.get("notes", ""),
    )
    return redirect(_safe_next())


@app.route("/projects/<int:project_id>/progress", methods=["POST"])
def project_progress(project_id):
    """Advances (or rewinds) a project's elapsed days/hours -- posted by
    either an individual checklist box (click day 4 -> progress_amount=4) or
    the plain counter field for goals too large to render as a checklist.
    Deliberately has nothing to do with Session Log dates -- the party
    updates this by hand whenever time passes at the table, in or out of a
    session."""
    conn = get_conn()
    models.update_project_progress(conn, project_id, request.form.get("progress_amount", type=int))
    return redirect(_safe_next())


@app.route("/projects/<int:project_id>/delete", methods=["POST"])
def project_delete(project_id):
    conn = get_conn()
    models.delete_project(conn, project_id)
    return redirect(_safe_next())


@app.route("/timeline")
def timeline():
    """The campaign's story so far, as a single chronological feed: every
    Session Log entry in play order (earliest first -- a timeline reads like
    a history, not a most-recent-first activity log), each one showing
    whichever Characters/Cities/Quests/etc. its write-up actually mentions
    via [[wiki links]]. No separate "what happened this session" field to
    maintain -- it's derived straight from the links already in the log
    entry's own content."""
    conn = get_conn()
    sessions = models.list_entries(conn, category="SessionLog")
    sessions = sorted(
        sessions,
        key=lambda e: (e["session_date"] or "", e["session_number"] or 0, e["id"]),
    )
    timeline_entries = [
        {"session": s, "mentions": models.get_outgoing_links(conn, s["id"])}
        for s in sessions
    ]
    return render_template("timeline.html", timeline_entries=timeline_entries)


@app.route("/map")
def map_view():
    """The World Map page is really "whichever map is currently selected" --
    the party can have any number of maps of varying scale (a World Map, a
    city street-map, a dungeon layout...), each with its own image and its
    own independent set of pins. The "Viewing: [...]" dropdown picks which
    one via ?map_id=; with none specified (or an invalid/deleted id) this
    falls back to the first map in sort_order, matching how a single
    /map/upload used to "just work" before multi-map support existed."""
    conn = get_conn()
    maps = models.list_maps(conn)
    map_id = request.args.get("map_id", type=int)
    current_map = models.get_map(conn, map_id) if map_id else None
    if current_map is None and maps:
        current_map = maps[0]

    dm_mode = session.get("dm_mode", False)
    if current_map:
        all_pins = models.get_map_pins(conn, current_map["id"])
        # Fog of war: with DM Mode off (the default "player view"), pins the
        # DM hasn't marked as Discovered yet are excluded entirely -- players
        # should never learn a secret location exists just by noticing an
        # unlabeled dot on the map. DM Mode shows every pin, with
        # undiscovered ones flagged visually so the DM can tell at a glance
        # what's still hidden.
        pins = all_pins if dm_mode else [p for p in all_pins if p["discovered"]]
    else:
        pins = []

    city_options = models.list_entries(conn, category="City")
    character_options = models.list_entries(conn, category="Character")
    organization_options = models.list_entries(conn, category="Organization")
    return render_template(
        "map.html",
        maps=maps,
        current_map=current_map,
        pins=pins,
        dm_mode=dm_mode,
        city_options=city_options,
        character_options=character_options,
        organization_options=organization_options,
        default_pin_symbol=models.DEFAULT_CHARACTER_PIN_SYMBOL,
        default_pin_color=models.DEFAULT_CHARACTER_PIN_COLOR,
    )


@app.route("/dm-mode/toggle", methods=["POST"])
def dm_mode_toggle():
    """Flip DM Mode for this browser session. There's no login system in
    this app, so DM Mode isn't a security boundary -- it's a convenience
    switch for whoever's running the table to preview the fully-revealed
    map. Session-scoped (not a DB setting) so each browser/tab remembers
    its own choice rather than flipping the view for everyone at the table."""
    session["dm_mode"] = not session.get("dm_mode", False)
    return redirect(request.referrer or url_for("map_view"))


@app.route("/maps/new", methods=["POST"])
def map_create():
    """Add a brand-new map -- a name plus an optional starting image (you can
    always upload/replace the image afterward from the map page itself)."""
    conn = get_conn()
    name = (request.form.get("name") or "").strip()
    if not name:
        return redirect(url_for("map_view"))
    filename = images.save_upload(request.files.get("image"))
    map_id = models.create_map(conn, name, filename)
    return redirect(url_for("map_view", map_id=map_id))


@app.route("/maps/<int:map_id>/upload", methods=["POST"])
def map_upload(map_id):
    conn = get_conn()
    current_map = models.get_map(conn, map_id)
    if current_map is None:
        return redirect(url_for("map_view"))
    new_filename = images.save_upload(request.files.get("image"))
    if new_filename:
        if current_map["filename"]:
            images.delete_upload(current_map["filename"])
        models.set_map_image(conn, map_id, new_filename)
    return redirect(url_for("map_view", map_id=map_id))


@app.route("/maps/<int:map_id>/rename", methods=["POST"])
def map_rename(map_id):
    conn = get_conn()
    name = (request.form.get("name") or "").strip()
    if name and models.get_map(conn, map_id) is not None:
        models.rename_map(conn, map_id, name)
    return redirect(url_for("map_view", map_id=map_id))


@app.route("/maps/<int:map_id>/delete", methods=["POST"])
def map_delete(map_id):
    """Deletes this map, every pin on it, and its uploaded image. Any pin on
    a *different* map that drilled down into this one just loses that link
    (handled by the DB's ON DELETE SET NULL) rather than breaking."""
    conn = get_conn()
    filename = models.delete_map(conn, map_id)
    if filename:
        images.delete_upload(filename)
    return redirect(url_for("map_view"))


HEX_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


@app.route("/map/pins", methods=["POST"])
def map_pin_add():
    """Drop a new pin on the current map at a clicked point (x/y as a
    percentage of the image's own width/height, so it stays put across zoom
    levels), for a City, Character, or Organization the map-viewer clicked on
    directly. City and Organization pins are both colored by that entry's own
    Disposition field; Character pins carry a free-picked symbol and color
    from the pin-placement form (falling back to a default star/violet if
    left blank or sent malformed). A pin can also optionally name a
    target_map_id -- another map this pin should offer to "drill down" into
    (e.g. a City pin on the World Map linking to that city's own street-level
    map); leaving it unset just means this pin has no sub-map. Silently
    no-ops on bad input (out-of-range coordinates, a target that's none of
    the three, or an unknown map) rather than erroring, since this is only
    ever hit from the map page's own click-to-place control, never a
    user-facing form that needs field-level errors."""
    conn = get_conn()
    map_id = request.form.get("map_id", type=int)
    entry_id = request.form.get("entry_id", type=int)
    x = request.form.get("x", type=float)
    y = request.form.get("y", type=float)
    target_map_id = request.form.get("target_map_id", type=int)
    if target_map_id and models.get_map(conn, target_map_id) is None:
        target_map_id = None
    if (
        map_id and models.get_map(conn, map_id) is not None
        and entry_id and x is not None and y is not None and 0 <= x <= 100 and 0 <= y <= 100
    ):
        entry = models.get_entry(conn, entry_id)
        if entry and entry["category"] in ("City", "Organization"):
            models.add_map_pin(conn, map_id, entry_id, x, y, target_map_id=target_map_id)
        elif entry and entry["category"] == "Character":
            symbol = (request.form.get("symbol") or "").strip()[:4] or models.DEFAULT_CHARACTER_PIN_SYMBOL
            color = (request.form.get("color") or "").strip()
            if not HEX_COLOR_RE.match(color):
                color = models.DEFAULT_CHARACTER_PIN_COLOR
            models.add_map_pin(conn, map_id, entry_id, x, y, symbol=symbol, color=color, target_map_id=target_map_id)
    return redirect(url_for("map_view", map_id=map_id))


def _pin_map_id(conn, pin_id):
    row = conn.execute("SELECT map_id FROM map_pin WHERE id = ?", (pin_id,)).fetchone()
    return row["map_id"] if row else None


@app.route("/map/pins/<int:pin_id>/delete", methods=["POST"])
def map_pin_delete(pin_id):
    conn = get_conn()
    map_id = _pin_map_id(conn, pin_id)
    models.delete_map_pin(conn, pin_id)
    return redirect(url_for("map_view", map_id=map_id))


@app.route("/map/pins/<int:pin_id>/toggle-discovered", methods=["POST"])
def map_pin_toggle_discovered(pin_id):
    """DM-only control (only rendered in the map template while DM Mode is
    on) for flipping a pin between hidden-from-players and revealed."""
    conn = get_conn()
    pin = conn.execute("SELECT discovered, map_id FROM map_pin WHERE id = ?", (pin_id,)).fetchone()
    if pin is not None:
        models.set_pin_discovered(conn, pin_id, not pin["discovered"])
    return redirect(url_for("map_view", map_id=pin["map_id"] if pin else None))


# Make sure the database tables exist no matter how this app is started.
# This runs at import time, so it covers both `python app.py` locally and
# a production WSGI server like gunicorn importing `app:app` directly
# (which never executes the __main__ block below). init_db() only issues
# CREATE TABLE IF NOT EXISTS statements, so it's safe to run on every startup.
models.init_db()
images.ensure_upload_dir()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=os.environ.get("FLASK_DEBUG") == "1")
