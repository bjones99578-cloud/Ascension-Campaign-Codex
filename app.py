import os

from flask import Flask, g, redirect, render_template, request, session, url_for

import dndbeyond
import images
import models
from rendering import render_wiki_content

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-me")
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024  # 8 MB per upload, plenty for a photo


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
        "category_counts": models.category_counts(conn),
        "current_author": session.get("display_name", ""),
        "detail_fields": models.merged_detail_fields(conn),
    }


@app.route("/")
def index():
    conn = get_conn()
    recent = conn.execute(
        "SELECT * FROM entry ORDER BY updated_at DESC LIMIT 8"
    ).fetchall()
    map_filename = models.get_setting(conn, "map_filename")
    return render_template("index.html", recent=recent, map_filename=map_filename)


@app.route("/category/<category>")
def category_view(category):
    conn = get_conn()
    if category not in models.CATEGORIES:
        return redirect(url_for("index"))
    entries = models.list_entries(conn, category=category)
    return render_template("category.html", category=category, entries=entries)


@app.route("/search")
def search():
    conn = get_conn()
    q = request.args.get("q", "").strip()
    results = models.list_entries(conn, query=q) if q else []
    return render_template("search.html", query=q, results=results)


@app.route("/entry/<int:entry_id>")
def entry_detail(entry_id):
    conn = get_conn()
    entry = models.get_entry(conn, entry_id)
    if entry is None:
        return render_template("not_found.html"), 404
    rendered = render_wiki_content(entry["content"], conn)
    all_backlinks = models.get_backlinks(conn, entry_id)

    related = None
    backlinks = all_backlinks
    if entry["category"] == "City":
        # Cities get their linked Characters, Organizations, and Quests broken
        # out into their own tables — populated both from the explicit Home
        # City / Headquarters City dropdowns and from [[City Name]] wiki-link
        # backlinks, merged and de-duplicated. Anything else that links here
        # (a Location, an Item, another City) still shows up below as a
        # general backlink so nothing gets lost.
        related = {
            "characters": models.merge_by_id(
                models.get_characters_in_city(conn, entry_id),
                [b for b in all_backlinks if b["category"] == "Character"],
            ),
            "factions": models.merge_by_id(
                models.get_organizations_in_city(conn, entry_id),
                [b for b in all_backlinks if b["category"] == "Organization"],
            ),
            "quests": [b for b in all_backlinks if b["category"] == "Quest"],
        }
        backlinks = [
            b for b in all_backlinks
            if b["category"] not in ("Character", "Organization", "Quest")
        ]
    elif entry["category"] == "Organization":
        related = {
            "members": models.merge_by_id(
                models.get_characters_in_organization(conn, entry_id),
                [b for b in all_backlinks if b["category"] == "Character"],
            ),
        }
        backlinks = [b for b in all_backlinks if b["category"] != "Character"]
    elif entry["category"] == "Region":
        related = {
            "cities": models.merge_by_id(
                models.get_cities_in_region(conn, entry_id),
                [b for b in all_backlinks if b["category"] == "City"],
            ),
        }
        backlinks = [b for b in all_backlinks if b["category"] != "City"]

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
    elif entry["category"] == "Organization":
        if entry["headquarters_city_id"]:
            related_entities["headquarters_city"] = models.get_entry(conn, entry["headquarters_city_id"])
        if entry["leader_id"]:
            related_entities["leader"] = models.get_entry(conn, entry["leader_id"])

    return render_template(
        "entry_detail.html",
        entry=entry,
        rendered=rendered,
        backlinks=backlinks,
        related=related,
        related_entities=related_entities,
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
            leader_id=leader_id, current_city_id=current_city_id, pc_slot=pc_slot,
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
                leader_id=leader_id, current_city_id=current_city_id, pc_slot=pc_slot,
                details=details,
            )
        elif remove_image and entry["image_filename"]:
            images.delete_upload(entry["image_filename"])
            models.clear_entry_image(conn, entry_id)
            models.update_entry(
                conn, entry_id, name, category, summary, content, author,
                home_city_id=home_city_id, organization_id=organization_id,
                region_id=region_id, headquarters_city_id=headquarters_city_id,
                leader_id=leader_id, current_city_id=current_city_id, pc_slot=pc_slot,
                details=details,
            )
        else:
            models.update_entry(
                conn, entry_id, name, category, summary, content, author,
                home_city_id=home_city_id, organization_id=organization_id,
                region_id=region_id, headquarters_city_id=headquarters_city_id,
                leader_id=leader_id, current_city_id=current_city_id, pc_slot=pc_slot,
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

        org_stubs = models.merge_by_id(
            models.get_organizations_in_city(conn, selected_city["id"]),
            [b for b in all_backlinks if b["category"] == "Organization"],
        )
        for stub in org_stubs:
            org = models.get_entry(conn, stub["id"])
            leader = models.get_entry(conn, org["leader_id"]) if org["leader_id"] else None
            organizations_display.append({"entry": org, "leader": leader})

        if selected_city["content"]:
            rendered_summary = render_wiki_content(selected_city["content"], conn)

    return render_template(
        "city_view.html",
        cities=cities,
        selected_city=selected_city,
        region=region,
        characters=characters,
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


@app.route("/map")
def map_view():
    conn = get_conn()
    map_filename = models.get_setting(conn, "map_filename")
    return render_template("map.html", map_filename=map_filename)


@app.route("/map/upload", methods=["POST"])
def map_upload():
    conn = get_conn()
    new_filename = images.save_upload(request.files.get("image"))
    if new_filename:
        old_filename = models.get_setting(conn, "map_filename")
        if old_filename:
            images.delete_upload(old_filename)
        models.set_setting(conn, "map_filename", new_filename)
    return redirect(url_for("map_view"))


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
