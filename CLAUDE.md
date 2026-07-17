# Ascension Campaign Codex — Project Status & Handoff

*Written 2026-07-17 as a handoff brief for a fresh Claude Code session picking up this project. Read this first before touching code.*

## What this project is

A Flask + SQLite D&D campaign wiki, built from scratch for one home game ("the Ascension campaign"). No login system, no build step, no JS framework — server-rendered Jinja2 templates, vanilla CSS, raw `sqlite3`. It's meant to be simple enough that the DM (the user, Bambi) can keep extending it herself with Claude's help, and robust enough that the whole party can use it as their shared reference during sessions.

**Where it lives:**
- Real working copy: `C:\Users\bjone\Desktop\dnd-wiki\Ascension-Campaign-Codex\` on the user's Windows machine (reached in this session via the Claude desktop device bridge).
- GitHub remote: `bjones99578-cloud/Ascension-Campaign-Codex`, pushed via GitHub Desktop.
- Live deployment: PythonAnywhere, user account "CallMeBambi", live at `callmebambi.pythonanywhere.com`.
- Deploy workflow: push from GitHub Desktop → click the in-app "Check for Updates" footer button → it fetches, fast-forward-only pulls, and auto-reloads the live app via PythonAnywhere's API. No Bash console needed for routine updates anymore (see "Just fixed" below for a bug in this that was just resolved).

## Tech stack & architecture

- **Backend:** `app.py` (Flask routes, ~1400 lines, see full route list below), `models.py` (all SQL/schema/CRUD, ~1900 lines), `bastion.py` (Bastion-specific logic split out), `images.py` (upload pipeline), `dndbeyond.py` (D&D Beyond character import), `rendering.py` (markdown + `[[Entry Name]]` auto-link rendering), `backup.py` (SQLite backup-API-based daily backup script), `updater.py` (self-update button logic).
- **Frontend:** Jinja2 templates in `templates/`, one hand-written `static/style.css` (no framework, no preprocessor), a handful of SVG icons in `static/icons/`.
- **Data:** SQLite (`wiki.db`), WAL mode. One big polymorphic `entry` table covers all seven wiki categories (see below) via a shared schema plus category-specific "detail columns." Separate tables for `map`, `map_pin`, `bastion_facility`, `project`, `custom_option`, `setting` (generic key/value store).
- **No auth.** Every route and button is open to anyone with the link — a deliberate choice since it's a small home-game tool, but it means every feature has to be safe to expose publicly (no destructive action without confirmation, no secrets in the repo).

### Wiki categories (the `entry` table)
`Region`, `City`, `Character`, `Organization`, `Item`, `Quest`, `SessionLog` — each with its own detail fields (see `models.DETAIL_FIELDS`), all sharing the same base entry columns (name, summary, content, author, image, timestamps, cross-reference FKs) plus auto `[[Name]]` linking between entries.

### Full current route map (`app.py`)
```
/                                  homepage (recent entries, category tiles)
/category/<category>              generic category listing (used by 6 of 7 categories)
/search                            full-text-ish search across entries
/entry/<id>                        entry detail page
/new, /entry/<id>/edit, /delete    entry CRUD
/import/dndbeyond                  D&D Beyond character sheet import
/city-view                         city-centric browsing view
/party, /party/assign, /unassign   Party Roster (5 fixed PC slots)
/reference                         Species/Class quick-reference cards
/loot, /loot/items[...]            Loot Tracker
/bastion, /bastion/settings        Bastion overview + settings
/bastion/facilities[...]           Bastion facility CRUD + images
/bastion/facility-types/<key>      per-facility-type config
/projects[...]                     crafting/building progress-tracker widget
                                    (shared between Bastion facilities and PCs)
/timeline                          session log timeline view
/map, /maps/[...]                  world map(s), upload, pins, DM Mode
/dm-mode/toggle                    toggles DM-only map reveal controls
/map/pins[...]                     pin placement/discovery toggling
/check-for-updates                 the self-update button (see below)
```

## Feature inventory (everything that currently exists)

1. **Core wiki** — 7 categories, full CRUD, markdown content with `[[Entry Name]]` auto-linking (including retroactive resolution when a new entry's name matches existing dangling links), search, a generic `category.html` listing template shared by 6 of the 7 categories.
2. **World Map** — multiple uploadable maps, click-to-place pins linked to entries, "discovered" toggle per pin, DM Mode (gates pin visibility/placement), now has its own **"wooden tabletop" visual theme** (see Recent Work).
3. **Party Roster** — a fixed 5-slot roster (assign/unassign existing PCs or create new ones straight into a slot), per-class color theming (`CLASS_THEME_SLUGS` → `.class-<slug>` CSS), now has its own **"sports promotion" trading-card visual theme** (see Recent Work).
4. **Loot Tracker** — party inventory/gold ledger, item history (sold/used/lost items shown struck-through rather than deleted). **Not yet themed** ("bank" theme planned).
5. **Bastion** — BG3/2024-rules-style stronghold tracker: overall Bastion settings + image, individual Special Facilities each with their own image, and a **Projects** system (see below). **Not yet themed** ("cloud ship" theme planned).
6. **Projects** (crafting/building progress tracker) — polymorphic, owned by either a Bastion Facility (one active project per facility) or a Character (unlimited simultaneous — this is where party crafters track their personal builds). Freeform text description, progress tracked either as a checklist (≤14 items, `PROJECT_CHECKLIST_MAX`) or a numeric counter (days/hours/etc. via `PROJECT_UNIT_OPTIONS`) depending on scale. Shared Jinja macros in `templates/_project_widget.html`, imported into both `bastion.html` and `entry_detail.html`.
7. **Custom images** — Bastion (overall + per-facility) and Characters (single portrait) can all have uploaded images. Shared pipeline in `images.py`: downscale to 2048px longest edge, re-encode JPEG/PNG based on alpha, UUID filenames, cleanup-on-delete. Deliberately not optimized further — current pipeline was confirmed sufficient.
8. **Reference page** — static-ish Species/Class quick-lookup cards, class cards share the same `.class-<slug>` theming as Party Roster.
9. **Timeline** — chronological session log view.
10. **D&D Beyond import** — pulls a character sheet from a D&D Beyond URL into a new Character entry.
11. **Self-update button** — footer "Check for Updates" button; fetches + fast-forward-only pulls from GitHub, then (if 3 PythonAnywhere env vars are set) calls PythonAnywhere's reload API to restart the live site automatically. Fully open, no DM-mode gating. **Just had a real production bug fixed** — see below.
12. **Backups** — `backup.py` does a consistent SQLite-backup-API copy (safe under WAL mode, unlike a raw file copy of a running DB).

## Established conventions (read before writing more CSS/templates)

These patterns were deliberately established during the "make every tab feel unique" work and should be followed for any further page-specific styling:

- **`page_class` body hook.** `base.html`'s `<body class="{% block page_class %}{% endblock %}">` lets any template scope page-specific CSS without touching shared components. (There's also an older, narrower `body_class` block scoped to `<main>` only — `page_class` is the newer, broader one; both currently coexist.)
- **CSS variable system.** `--cat-color` / `--cat-light` / `--cat-glow` drive all category theming (`.cat-region`, `.cat-character`, etc., defined once in `:root`-adjacent rules) and are reused for the 12 D&D class themes (`.class-barbarian` … `.class-wizard`). Any new page theme should reuse these variables rather than hardcoding new colors, so it stays visually related to the rest of the site.
- **"Reskin the opaque, working elements only" rule.** Established on the Map theme and reused on Party Roster: a page's *decorative* surface (map table wood-grain, roster card background) can go fully dark/thematic because it's a single self-contained opaque box, but *functional* elements that assume the site's normal light-parchment contrast (form labels, buttons with `.btn`'s own opaque background, empty-state hints) are either left alone or explicitly overridden with their own readable colors. Never reskin `<body>` or a whole transparent-background page section — it breaks text contrast on elements that weren't designed for it.
- **One page, one bold accent font, used sparingly.** `--font-sport` (Anton, via Google Fonts) was added specifically for Party Roster's jersey numbers/stats and is deliberately not used anywhere else — the fantasy-manuscript fonts (`--font-display` / `--font-heading` / `--font-body`) remain the site's default everywhere else. Future themes (bank, cloud ship, mountain) should each get their own single restrained accent choice rather than freely mixing fonts across the site.
- **Restructure, don't just recolor.** Per explicit user preference: each themed tab should get its own information layout (e.g. Party Roster's stat-bar + jersey number + league-record badge is a different arrangement of the same underlying data, not just a Party-Roster-colored version of a generic card), not just new colors on the existing generic layout.
- **Verification depth expected for any page-visual change:** Jinja syntax check (`jinja2.Environment(...).get_template()`), CSS brace-balance sanity check, boot the app with representative seeded test data (varying/missing fields, at least one empty state), Playwright screenshots at full-page + close-up + mobile width, confirm no regressions to the page's forms/actions via direct route hits, clean up all test data/artifacts before finishing, then deliver screenshots first and ask for approval before moving to the next page.

## Recent work timeline (most recent first)

1. **[Just delivered, awaiting feedback] Loot Tracker "bank" theme.** Added a "statement summary" panel (balance in a monospaced ledger font, holdings/historical counts, a highest-rarity badge), a 7-tier rarity color system (`--rarity-color` custom property per tier, driving a left-edge ledger tab per row plus the inline rarity `<select>`'s own color), row numbering, right-aligned/monospaced numeric columns (new `--font-ledger`, IBM Plex Mono), and a bordered "New Deposit" slip around the quick-add form. Required a small `app.py` change too (the `/loot` route now computes `holdings_count`/`history_count`/`highest_rarity`, ranked against `models.OPTIONS_BY_FIELD['rarity']` so a custom rarity value can't misrank). Also fixed a real, pre-existing mobile bug while testing: the ledger table (7-8 columns of inputs/selects) was blowing out the whole page's width on narrow viewports instead of scrolling contained — wrapped it in a new `.loot-table-scroll` (`overflow-x: auto`) div, scoped to this page only. Verified via seeded test data (9 items spanning all 7 rarities + 3 history statuses + missing type/value fields), full add/update/delete route checks, and screenshots at full-page/statement-closeup/table-closeup/mobile/empty-state. Files delivered: `loot.html`, `base.html` (added the IBM Plex Mono font import), `style.css`, `app.py`.
2. **[Fixed, delivered, awaiting live confirmation] Update-button 502 bug.** The "Check for Updates" button's reload call was firing synchronously from inside the same HTTP request rendering the success page — PythonAnywhere could restart the worker mid-response, producing a raw "502 :-(" proxy error even though the underlying git pull + reload both actually succeeded. Fixed by deferring the actual reload API call to a background thread (`RELOAD_DELAY = 3` seconds) so the response finishes sending first. Verified against a simulated behind-by-one-commit local git repo + a mocked PythonAnywhere API via a real Flask test client (confirmed: response returns in ~50ms, mocked reload call provably hasn't fired yet at that point). `updater.py`, `templates/update_result.html` (auto-redirect bumped 5s→10s), and `README.md` all updated and written back to the real repo. **The user has not yet re-tested this fix live** — next push + button click should confirm it, though the *very first* click after pushing this fix will still run the old buggy code (chicken-and-egg), so one more transient 502 on that specific click is expected and fine.
3. **Party Roster "sports promotion" theme — approved, locked in.** Restructured `party.html` (jersey numbers, AC/HP/SPD/PP stat-bar, league-record header badge, position-tag/level-badge) and added the corresponding CSS (dark foil trading-card reskin with a diagonal team-color corner banner per class, `--font-sport`).
4. **Map "wooden tabletop" theme — delivered and explicitly approved** by the user ("looks good keep going"). Established the `page_class` hook and the "reskin only opaque elements" principle used since.
5. Bastion custom images (overall + per-facility), reusing the existing `images.py` pipeline unchanged.
6. Bastion/Character Projects system (crafting/building progress tracking, checklist-or-counter).
7. Self-update button's *original* build (before today's bug fix) — `updater.py`, `/check-for-updates` route, footer button, full README setup docs for the 3 PythonAnywhere env vars.

## The user's current/open objective

The active plan (user-approved, "one at a time" pacing) is to give each of the 5 main nav tabs its own visual identity **and** its own data layout:

| Tab | Theme | Status |
|---|---|---|
| Map | Wooden tabletop | ✅ Done, approved |
| Party Roster | Sports promotion / trading cards | ✅ Done, approved |
| Loot Tracker | Orderly / bank / ledger | ✅ Done, delivered, awaiting feedback |
| Bastion | Cloud ship | ⬜ Not started |
| Regions | Mountain | ⬜ Not started (also needs a design decision — see below) |

**Then the user broadened the ask** (message was originally cut off mid-send, but has since been clarified — see decisions below):

> "I want to further refine and tune all the existing pages to continue to develop the website in its overall feel, completeness, and constructability"

### Clarified decisions (as of 2026-07-17)

All four open questions from the first version of this doc have been answered directly by the user:

1. **"Constructability" scope — all three meanings apply, deliberately:** (a) codebase maintainability (more automated tests, better structure/docs, a safety net for destructive actions), (b) leaning further into the Bastion's literal construction/Projects feature, and (c) building out functionality broadly across the site. Treat this as a standing, multi-pronged objective rather than a single narrow task — pick whichever angle fits whatever page/feature is being touched at the time.
2. **Party Roster theme — approved, locked in.** No further changes requested. Treat it as done, same tier as Map.
3. **Priority order — finish the 5-tab theme plan first, then move to the broader all-pages polish/completeness/maintainability work.** Do not interleave; do not pivot early. Sequence is: Loot Tracker → Bastion → Regions → then the broader pass.
4. **Regions template — give it its own dedicated route/template**, splitting it out of the shared `category.html` (same pattern as Map/Party Roster/loot already getting their own templates), rather than trying to theme it from inside the template still shared by City/Character/Organization/Item/Quest.

## Recommended next steps for whoever picks this up

1. **Loot Tracker "bank" theme is done, delivered, awaiting feedback** — check whether the user has responded; if not, treat it like Party Roster and nudge for sign-off before starting Bastion. Note while testing it, a real pre-existing mobile bug was found and fixed along the way (the loot table overflowed the whole page sideways on narrow viewports instead of scrolling contained) — worth remembering that `.related-table` elsewhere in the app (entry detail related-entries tables, etc.) probably has the same gap, since it was never actually tested at mobile width before this. That's a good candidate for the later maintainability/completeness pass rather than something to chase down right now.
2. **Bastion ("cloud ship") is next in the theme sequence**, then Regions ("mountain", after splitting it out of `category.html` into its own template).
3. Once all 5 tabs are themed, move to the broader "refine all pages" pass — this now has three legitimate angles to work through (see clarified decisions above), so it's worth treating as its own multi-step project rather than one pass: (a) a maintainability/testing pass (the standing list of foundational gaps — no hard-delete undo/safety net, no revision history, zero automated tests, single point of failure hosting, and now the `.related-table` mobile-overflow gap noted above — is a good starting checklist), (b) deepen the Bastion construction/Projects feature specifically, (c) a visual/completeness pass over the remaining un-themed pages (entry detail, generic category listing, search, reference, timeline, entry forms, homepage) so they don't feel like the odd ones out next to 5 fully themed tabs.
4. Confirm the update-button fix actually resolved the live 502 (ask the user to push + click once more and report back), if that hasn't already happened.

## Testing/verification tooling available in a fresh session

- `jinja2.Environment(loader=jinja2.FileSystemLoader('templates')).get_template(name)` for template syntax.
- `ast.parse(open('app.py').read())` for Python syntax.
- Boot with `nohup python3 app.py & disown`, hit routes with `curl`, always `rm -f wiki.db` (and any `static/uploads/*`, `__pycache__`) before/after a test run to keep the real seed data out of test screenshots.
- Playwright is preinstalled at `/opt/pw-browsers/chromium` — use `executablePath` explicitly, don't run `playwright install`.
- For `updater.py` changes specifically: build a throwaway bare git repo + clone to simulate the GitHub remote, and `unittest.mock.patch('updater.requests.post', ...)` to simulate the PythonAnywhere reload API — never hit the real GitHub/PythonAnywhere infrastructure from tests (and note: this cloud sandbox's own network policy blocks outbound calls to pythonanywhere.com anyway, so mocking is required, not optional).
- Delivery pattern: `SendUserFile` the changed files/screenshots into the conversation, then (if a desktop is connected — check via `mcp__remote-devices__get_device_info`) `mcp__remote-devices__device_commit_files` to write them into the real repo at `C:\Users\bjone\Desktop\dnd-wiki\Ascension-Campaign-Codex\...`.

## One environment note for whoever's running this

This cloud sandbox is ephemeral — a prior session's working copy at `/root/dnd-wiki/` was already wiped by the time this doc was written (new container). The **real** source of truth is always the user's own machine at the path above; stage files from there via the device bridge rather than assuming anything persisted in `/root/` or `/home/claude/` from a previous session.
