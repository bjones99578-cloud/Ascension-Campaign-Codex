# Ascension Campaign Codex

A tiny shared wiki for your D&D party: track regions, cities, characters,
organizations, locations, items, and quests, with wiki-style `[[links]]`
between entries and automatic "what links here" backlinks — like a mini
Wikipedia for your world.

Built with Flask + SQLite. No build step, no JavaScript framework, one database
file.

## Running it locally

Requires Python 3.9+.

```bash
cd dnd-wiki
pip install -r requirements.txt
python app.py
```

Then open http://localhost:5000 in your browser. The first run creates
`wiki.db` automatically (a single SQLite file that holds every entry).

To let people on your home network reach it while your computer is on:
find your computer's local IP (e.g. `192.168.1.23`) and share
`http://192.168.1.23:5000` — everyone must be on the same Wi-Fi.

## How it works

- **Categories**: Region, City, Character, Organization, Location, Item,
  Quest, Session Log. Browse by category from the top nav, or use the search bar.
- **Structured relationships**: alongside free-text `[[wiki links]]`, a few
  entry types have explicit dropdown fields so the connection is guaranteed
  to show up in the right table even if nobody remembers to write a link:
  Characters can pick a **Home City** and an **Organization**, Cities can
  pick a **Region**, a **Leader** (any Character who rules it), and a
  **Leading Organization** (a group that governs it instead of a single
  ruler), and Organizations can pick a **Headquarters City** and a **Leader**
  (any Character). Set these when creating or editing an entry — the
  dropdown only appears once you've picked the matching category. Entries
  linked either way (dropdown or `[[wiki link]]`) show up together in the
  same table, de-duplicated. Two more such relationships: an Item can pick a
  **Current Holder** (the Character carrying it right now — shows up on the
  Item as "Carried by" and on that Character's own page as a "Carried Items"
  table), and a Location can pick a **Controlling Organization** (the faction
  that owns or runs the place — shows up on the Location as "Controlled by"
  and on that Organization's own page as a "Controlled Locations" table).
- **Typical D&D fields per category**: each category also has a few
  quick-reference fields shown right under the title, separate from the
  free-text content — fill in whichever apply, everything's optional:
  - **Character**: Species, Class, Level, Alignment, Background, Status
    (Alive / Dead / Missing / Retired), Armor Class (AC), Hit Points (HP),
    Speed, Passive Perception, Deity / Patron, Personality Traits
  - **City**: Settlement Size, Government, Population, Disposition
    (Friendly / Neutral / Hostile — toward the party)
  - **Organization**: Organization Type, Alignment, Status (Active /
    Disbanded / Dissolved / Dormant), Disposition (Friendly / Neutral /
    Hostile — toward the party, same field City uses)
  - **Region**: Terrain, Climate
  - **Location**: Location Type, Danger Level
  - **Item**: Item Type, Rarity, Requires Attunement, Estimated Value (gp),
    Status (In Possession / Sold / Given Away / Used-Consumed / Destroyed /
    Lost)
  - **Quest**: Status, Difficulty (Easy / Medium / Hard / Deadly), Level
    Range, Quest Giver, Reward, XP Reward, Gold Reward

  These fields only appear on the form once you've picked the matching
  category, and most are dropdowns of standard 5e-style options (with an
  "Other" choice for homebrew) so entries stay consistent across the party.
  A Player Character's AC/HP/Speed/Passive Perception also surface as a
  compact "Combat" line on their Party Roster card, so the numbers you need
  most mid-fight are visible without opening their full entry.
- **Adding your own dropdown options**: any of those dropdowns can be
  extended on the spot — pick "+ Add new option…" at the bottom of the list,
  type your own text (a homebrew class, a custom settlement size, whatever
  doesn't fit the standard list), and save the entry. That value is saved
  permanently, so it shows up as a normal option in that same dropdown for
  every entry and every player from then on — no editing code, no restart.
- **Party Members vs. other characters**: everywhere Characters are listed
  together — the Characters category page, a City's or Organization's page,
  and City View — they're split into a "Party Members" table and an "Other
  Characters"/"Other Members" table, so the actual party never gets lost
  among all the NPCs a campaign accumulates. Each table shows Species, Class
  (with Subclass), Level, Status, and (on the Characters page) Home City at a
  glance, instead of just a name and a one-line summary.
- **Everything in tables**: category listing pages (Cities, Organizations,
  Regions, Locations, Items, Quests) and the relationship sections on an
  entry's own page (a City's Factions/Quests, an Organization's Members, a
  Region's Cities) render as proper tables of that category's typical
  fields — Settlement Size/Government/Population for Cities, Type/Leader/
  Status/Alignment for Organizations, and so on — rather than a bare list of
  names, so you can scan and compare entries at a glance instead of opening
  each one.
- **City View**: the "City View" link in the nav is a one-page watchboard for
  running a session — pick a city from the dropdown and see its picture (if
  it has one), its Region, Settlement Size, Government, and Population, its
  write-up, and live tables of every Character (with Class/Level/Status) and
  Organization (with Type/Leader/Status/Alignment) connected to it, all on
  one screen instead of clicking through separate entry pages as the party
  travels around.
- **A theme per category**: each of the eight categories has its own custom
  icon and ink color — deep gold for Regions, brown-gold for Cities, violet
  for Characters, deep rose for Organizations, teal for Locations, rust for
  Items, indigo for Quests, and warm brown for Session Logs — carried through
  the nav, category badges, category pages, and entry pages, so each type of
  entry has its own distinct look at a glance.
- **Look and feel**: the whole codex is styled like a hand-kept fantasy
  journal rather than a flat wiki — a warm aged-parchment background with a
  subtle paper-grain texture, ink-brown text, an illuminated-manuscript-style
  banner atop every page, and data-heavy sections (category listings, City
  View, the Party Roster's combat stats, Loot Tracker, and every entry's
  relationship tables) restyled as ledger pages, with ink-line rows, old-style
  numerals, and a colored header bar per category.
- **Party Roster**: the "Party Roster" link in the nav is a fixed 5-slot
  page for your actual player characters. Mark any Character entry as a
  **Party Member** (a field right on the Character form) and fill in their
  **Player Name**, **Subclass**, **Key Item**, and **Current City** (handy
  for tracking where everyone is as the party travels), then seat them in an
  open slot — either "+ Create New Character" straight into that slot, or
  assign an existing party member who isn't seated yet. Each occupied slot
  is themed by the character's **Class**: a Ranger's card glows woodland
  green, a Wizard's glows arcane blue, a Paladin's glows radiant gold, and so
  on for all twelve core classes. "Remove from Roster" just frees the slot —
  it never deletes the character entry itself.
- **Loot Tracker**: the "Loot Tracker" link in the nav is a shared party
  inventory view, one level up from browsing Items one at a time. Every Item
  with a **Current Holder** set to a Party Member shows up under that
  character's own "Haul" table; anything held by an NPC lands in its own
  "Held by Others" section; anything with no Current Holder at all shows up
  as "Unclaimed". A **Party Treasury** total at the top adds up the
  Estimated Value of everything currently marked **Status: In Possession**
  across the party's hauls and the unclaimed pile — items marked Sold, Given
  Away, Used/Consumed, Destroyed, or Lost still show up (struck through) for
  the historical record, but drop out of that total, so the number at the
  top always reflects what the party could actually spend or trade right
  now.
- **Timeline**: the "Timeline" link in the nav is the campaign's story so
  far as a single chronological feed — every Session Log entry in play
  order (earliest first), each showing its Session #, Session Date,
  In-Game Date, summary, and a row of tags for whichever Characters,
  Cities, Quests, and other entries that session's write-up mentions via
  `[[wiki links]]`. There's nothing extra to fill in for this — it's built
  entirely from the Session Date field and the links already in each Session
  Log's content, so it stays accurate automatically as you keep logging
  sessions.
- **Search filters**: the "Search" page (click the search box's Search
  button, or just visit it directly) does more than a plain keyword match —
  pick a Category and the page adds that category's own filter dropdowns
  (Disposition and Status for Organizations, Status for Characters and
  Quests, Rarity and Status for Items, Difficulty for Quests, and so on,
  straight from that category's own typical fields), so you can find, say,
  every Hostile Organization or every Active Quest without a keyword at all.
  Keyword, Category, and any of those filters combine — narrow to
  "Organizations, Hostile, containing 'cult'" in one search. "Clear filters"
  resets back to a blank search.
- **Wiki links**: in any entry's content, type `[[Entry Name]]` to link to
  another entry, or `[[Entry Name|custom display text]]`. If the target
  doesn't exist yet, the link shows up dashed/orange — click it to create
  that entry on the spot.
- **Backlinks**: every entry page has a "What links here" section, computed
  automatically from other entries' content.
- **Markdown**: entry content supports standard Markdown (headings, bold,
  lists, tables, code blocks).
- **No login system**: anyone with the link can create and edit entries, which
  keeps things simple for a small trusted party. There's an optional "Your
  name" field on each entry so people can see who wrote or last touched it.
- **Pictures**: any entry can have an image attached (a character portrait,
  city art, an item illustration) — add one when creating or editing an entry.
- **World Map (multiple maps)**: the "Map" link in the nav holds as many maps
  as the party needs — a World Map, a city street-map, a dungeon layout,
  whatever scale is useful — each with its own image and its own independent
  set of pins. A "Viewing: [...]" picker at the top switches between them,
  and each has its own **Rename** and **Delete This Map** controls (deleting
  a map removes its pins too, but never the entries those pins pointed at).
  "Add a new map" at the bottom of the page creates another one — just give
  it a name; the image is optional and can be added or replaced anytime from
  whichever map is currently selected. Every map gets its own zoom in/out
  controls and click-to-pan.
  - **Sub-map drilldown**: any pin can optionally link to another map — e.g.
    a City pin on the World Map pointing at that city's own street-level
    map. Set this when placing the pin ("Links to sub-map"); if set, hovering
    the pin shows a "View sub-map: [name] →" link that jumps straight there.
    Leave it unset for pins that don't need one — not every map uses this.
    Deleting the target map just clears that link from the pin rather than
    breaking anything.
  - **City pins**: click "📍 Add City Pin", then click anywhere on the map —
    a marker drops right where you clicked and you just pick which City
    entry it is. From then on that pin is a clickable hotspot: click it to
    jump straight to that city's Dynamic City View, or just hover over it for
    a quick glance at who's Led by (its Leader, or its Leading Organization if
    it has no single Leader) and its Settlement Size, without leaving the
    map. A pin's color reflects that City's **Disposition** field — blue for
    Friendly, red for Hostile, and the standard gold for Neutral or
    unset — so you can read the political map at a glance before you even
    hover. Pins stay put on the same spot no matter how far you zoom in or
    out. Hover a pin and use "Remove pin" to unpin it (the City entry itself
    is untouched — it just comes off the map).
  - **Character pins**: click "★ Add Character Pin" to mark a notable
    person's last-known whereabouts — a hideout, a battlefield, wherever the
    party met them — the same click-to-place flow as City pins, just picking
    a Character instead. Character pins are deliberately smaller than City
    dots so the two never get confused, and each one is yours to customize:
    type any single letter or emoji as its **Symbol** and pick its **Pin
    color** from a color wheel, so Aldric the paladin's pin can look nothing
    like Old Marrow the missing wizard's. Leave either blank and it falls
    back to a default star/violet marker. Hover a Character pin for their
    name and **Last Known Status** (Alive/Dead/Missing/Retired), click it to
    jump to their entry, and "Remove pin" takes it off the map without
    touching the Character entry itself.
  - **Organization pins**: click "🚩 Add Organization Pin" to mark a guild
    hall, cult hideout, or any other faction headquarters — same
    click-to-place flow again, picking an Organization this time. These
    render as a small diamond/banner shape so they're never mistaken for a
    City's round dot or a Character's round symbol badge, and — like City
    pins — their color comes straight from that Organization's own
    **Disposition** field (blue Friendly, red Hostile, gold Neutral/unset),
    so a hostile cult's hideout reads red on the map without you picking a
    color by hand. Hover for their Leader and Organization Type, click to
    jump to their entry, "Remove pin" to unpin.
  - **DM Mode / fog of war**: any pin (City, Character, or Organization) can
    be kept secret from the party until they've actually found it. The
    "🕯️ DM Mode" button on the map toggles a DM-only view of the map for
    your own browser/session — flip it on and every pin appears, including
    ones marked undiscovered (shown dimmed with a dashed outline and a
    "Hidden from players" tag on hover, plus a "Mark Discovered" /
    "Mark Undiscovered" link). With DM Mode off — the default view everyone
    else sees — undiscovered pins don't render on the map at all, so a
    secret lair doesn't tip its own existence just by showing up as an
    unlabeled dot. New pins default to discovered/visible, matching how the
    map already worked before this feature existed; mark one undiscovered
    only when you're deliberately hiding something the party hasn't found
    yet. Since there's no login system, DM Mode isn't a security boundary —
    it's just a convenience switch, remembered per browser, for whoever's
    running the table.
- **Session Log**: a dedicated category for session recaps, separate from
  the world's own entries. Give one a **Session #**, a **Session Date** (the
  real-world date you played), and an **In-Game Date** (free text, since most
  campaigns run on their own fantasy calendar rather than the real one), then
  write the recap itself in the normal Content field — mention any
  `[[City Name]]`, `[[Character Name]]`, or `[[Quest Name]]` and it links up
  and shows as a backlink on that entry automatically. Unlike every other
  category (which lists alphabetically), the Session Logs page sorts
  most-recent-first by Session Date, so the newest recap is always at the
  top.
- **Relationship tables**: every City entry automatically grows Characters /
  Notable Factions / Missions & Quests tables (from the Home City /
  Headquarters City dropdowns and from other entries linking to it with
  `[[City Name]]`); every Organization entry grows a Members table; and every
  Region entry grows a Cities in this Region table. No manual linking step
  needed beyond picking the dropdown or writing the `[[link]]`.
- **Import from D&D Beyond**: on the New Entry page, "Import from D&D Beyond"
  lets you paste a character's D&D Beyond URL (the character's sheet privacy
  must be set to Public) and pre-fill a new Character entry — not just the
  write-up, but the actual structured fields too: Species, Class, Subclass,
  Level (total, across every class for a multiclassed character), Alignment,
  Background, Player Name (their D&D Beyond username), Personality Traits,
  and Deity/Patron (when D&D Beyond has one on file); Status/Party Member
  default to Alive/Yes since an importable sheet is always an active PC.
  Armor Class, Hit Points, Speed, and Passive Perception are deliberately
  left blank rather than guessed — D&D Beyond derives those from equipped
  gear and a pile of conditional bonuses this unofficial endpoint doesn't
  expose pre-computed, so they're quick to fill in by hand instead of risking
  a silently wrong combat stat. The write-up itself still gets stats,
  personality traits, and backstory.
  A race, class, or background D&D Beyond has that isn't one of the form's
  standard dropdown choices (a less common race, Artificer, a homebrew
  background) still comes through as-is rather than getting forced into
  "Other" — and becomes a real dropdown option itself the moment you save the
  entry, per "Adding your own dropdown options" above. Review everything
  before saving; this relies on an internal D&D Beyond endpoint that isn't an
  official, supported API — D&D Beyond staff have said outright they can
  change or break it without notice — so treat it as a convenience that might
  stop working someday, not something to depend on. If it ever fails, "Enter
  manually instead" is right there on the same page.

Note on renaming: if you rename an entry, any existing `[[OldName]]` links
elsewhere will show up as a "click to create" link until someone edits that
page to point at the new name — same as how a real wiki behaves.

## Deploying it so the whole party can use it

This app is a small, always-on server with a local database file, so it's a
good fit for a traditional free host (not Vercel/Netlify — those are
serverless and don't keep a persistent SQLite file between requests).

### Option A: Render.com (recommended, free, ~5 minutes)

1. Push this folder to a new GitHub repo (Render deploys from GitHub).
2. Go to https://render.com → New → Web Service → connect your repo.
3. Settings:
   - Runtime: Python 3
   - Build command: `pip install -r requirements.txt`
   - Start command: `gunicorn app:app`
4. Add an environment variable `SECRET_KEY` set to any random string.
5. Deploy. Render gives you a URL like `https://your-app.onrender.com` — share
   that with your party.

Render's free tier spins the service down after inactivity (it wakes back up
in a few seconds when someone visits), and the filesystem is wiped on
redeploy — so treat `wiki.db` as safe for regular play, but avoid redeploying
once your party's data matters, or upgrade to a paid instance with a
persistent disk if you want redeploys to be safe too.

### Option B: PythonAnywhere (free, persistent disk, no redeploy risk)

1. Create a free account at https://www.pythonanywhere.com.
2. Upload this project folder (Files tab, or clone via git from the Bash
   console they provide).
3. Web tab → Add a new web app → Flask → point it at `app.py`.
4. In the WSGI config file it generates, make sure it imports `app` from this
   project's `app.py`.
5. Reload the web app. Your site is live at `yourusername.pythonanywhere.com`,
   and the SQLite file persists on disk permanently (no spin-down, no wipe).

### Option C: Fly.io / Railway

Both work well too if you're comfortable with a CLI and want a custom domain
or a persistent volume for `wiki.db`. The app is a standard Flask + gunicorn
app, so their default Python/Flask guides apply directly — just make sure
whichever one you pick gives `wiki.db` a persistent volume/disk, not just
ephemeral container storage.

## Backing up your world

`wiki.db` holds all your text entries, and `static/uploads/` holds every
picture and the world map. Copy both anywhere to back up your whole codex, or
to move it between hosts.

## A note on the free-tier hosts and uploaded images

On Render's free tier specifically, both `wiki.db` and anything in
`static/uploads/` live on the same ephemeral disk — a redeploy wipes both
together. PythonAnywhere's free tier keeps both permanently since its disk
isn't ephemeral. Same trade-off as before, just now it covers images too.
