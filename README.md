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
  Quest. Browse by category from the top nav, or use the search bar.
- **Structured relationships**: alongside free-text `[[wiki links]]`, a few
  entry types have explicit dropdown fields so the connection is guaranteed
  to show up in the right table even if nobody remembers to write a link:
  Characters can pick a **Home City** and an **Organization**, Cities can
  pick a **Region**, and Organizations can pick a **Headquarters City** and a
  **Leader** (any Character). Set these when creating or editing an entry —
  the dropdown only appears once you've picked the matching category. Entries
  linked either way (dropdown or `[[wiki link]]`) show up together in the
  same table, de-duplicated.
- **Typical D&D fields per category**: each category also has a few
  quick-reference fields shown right under the title, separate from the
  free-text content — fill in whichever apply, everything's optional:
  - **Character**: Species, Class, Level, Alignment, Background, Status
    (Alive / Dead / Missing / Retired)
  - **City**: Settlement Size, Government, Population
  - **Organization**: Organization Type, Alignment, Status (Active /
    Disbanded / Dissolved / Dormant)
  - **Region**: Terrain, Climate
  - **Location**: Location Type, Danger Level
  - **Item**: Item Type, Rarity, Requires Attunement
  - **Quest**: Status, Quest Giver, Reward

  These fields only appear on the form once you've picked the matching
  category, and most are dropdowns of standard 5e-style options (with an
  "Other" choice for homebrew) so entries stay consistent across the party.
- **Adding your own dropdown options**: any of those dropdowns can be
  extended on the spot — pick "+ Add new option…" at the bottom of the list,
  type your own text (a homebrew class, a custom settlement size, whatever
  doesn't fit the standard list), and save the entry. That value is saved
  permanently, so it shows up as a normal option in that same dropdown for
  every entry and every player from then on — no editing code, no restart.
- **City View**: the "City View" link in the nav is a one-page watchboard for
  running a session — pick a city from the dropdown and see its Region,
  Settlement Size, Government, and Population, its write-up, and live tables
  of every Character (with Class/Level/Status) and Organization (with
  Type/Leader/Status/Alignment) connected to it, all on one screen instead of
  clicking through separate entry pages as the party travels around.
- **A theme per category**: each of the seven categories has its own custom
  icon and arcane glow color — emerald for Regions, gold for Cities, violet
  for Characters, rose for Organizations, cyan for Locations, copper for
  Items, and indigo for Quests — carried through the nav, category badges,
  category pages, and entry pages, so each type of entry has its own
  distinct, glowing fantasy feel.
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
- **World Map**: the "Map" link in the nav holds a single shared map image
  (great for a hand-drawn world map) with zoom in/out controls and scrolling
  to pan around it. Uploading a new map there replaces it for everyone.
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
  Background, Player Name (their D&D Beyond username), and Status/Party
  Member default to Alive/Yes since an importable sheet is always an active
  PC. The write-up itself still gets stats, personality traits, and backstory.
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
