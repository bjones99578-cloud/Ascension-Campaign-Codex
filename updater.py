"""Self-update support for the "Check for Updates" button in the site
footer: pulls the latest code from GitHub and, if PythonAnywhere's reload
API is configured, restarts the live web app to actually start running it
-- all without anyone needing to open a Bash console.

Deliberately conservative in a few ways, since this runs unattended from a
web button click with nobody at a terminal to fix things if it goes wrong:
  - "Check" is a real check, not just a bare `git pull` -- it fetches and
    compares against upstream first, so a click when there's nothing new
    never touches the working tree at all.
  - A real pull is always `--ff-only`. It will never create a merge commit
    or touch a file that's diverged, and fails loudly (changing nothing)
    rather than risk a conflict nobody's around to resolve.
  - The auto-reload half is entirely optional. If the three PythonAnywhere
    env vars below aren't set, the code still gets pulled -- reloading is
    just left as a manual "click Reload on your Web tab" step, same as the
    README's existing deployment instructions.
"""
import os
import subprocess

import requests

APP_ROOT = os.path.dirname(os.path.abspath(__file__))

# A slow/hung network call shouldn't hang the request (or the whole web
# worker) forever -- these are generous but bounded.
GIT_TIMEOUT = 60
RELOAD_TIMEOUT = 30

# Only needed for the auto-reload half -- see the README for exactly where
# to find these in your PythonAnywhere account (Account -> API Token tab)
# and how to set them as WSGI environment variables, the same way SECRET_KEY
# already gets set there. PYTHONANYWHERE_API_TOKEN in particular is a
# credential for your whole PythonAnywhere account (not just this one app),
# so it belongs only in the WSGI config file on PythonAnywhere itself --
# never in the public GitHub repo.
PYTHONANYWHERE_USERNAME = os.environ.get("PYTHONANYWHERE_USERNAME")
PYTHONANYWHERE_DOMAIN = os.environ.get("PYTHONANYWHERE_DOMAIN")
PYTHONANYWHERE_API_TOKEN = os.environ.get("PYTHONANYWHERE_API_TOKEN")


def is_git_repo():
    return os.path.isdir(os.path.join(APP_ROOT, ".git"))


def _run_git(*args):
    """Runs a git command in this app's own directory. Returns
    (success, output) -- output is stdout+stderr combined, since git puts
    plenty of useful detail on stderr even on success (e.g. fetch's summary
    of new refs). Never raises: a missing git binary, a timeout, or a
    non-zero exit all come back as success=False with a human-readable
    message rather than a traceback, since this always runs from a button
    click with nobody around to read one."""
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=APP_ROOT,
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT,
        )
    except FileNotFoundError:
        return False, "git isn't installed/available on this server."
    except subprocess.TimeoutExpired:
        return False, f"git {' '.join(args)} timed out after {GIT_TIMEOUT}s."
    output = (result.stdout + result.stderr).strip()
    return result.returncode == 0, output


def check_and_pull():
    """The whole "Check for Updates" flow. Returns a dict:
      status: 'not_a_repo' | 'error' | 'up_to_date' | 'pulled'
      message: human-readable detail (git's own output, or an error)
      reload: None if no reload was attempted (nothing was pulled, or the
              pull itself failed), else the dict trigger_reload() returns.
    """
    if not is_git_repo():
        return {
            "status": "not_a_repo",
            "message": "This copy of the app isn't a git checkout, so there's nothing to pull from GitHub here.",
            "reload": None,
        }

    ok, out = _run_git("fetch", "origin")
    if not ok:
        return {"status": "error", "message": f"git fetch failed: {out}", "reload": None}

    ok, head = _run_git("rev-parse", "HEAD")
    if not ok:
        return {"status": "error", "message": f"Couldn't read the current commit: {head}", "reload": None}
    ok, upstream = _run_git("rev-parse", "@{u}")
    if not ok:
        return {
            "status": "error",
            "message": "This checkout has no upstream branch set, so there's no way to tell what's new: " + upstream,
            "reload": None,
        }

    if head.strip() == upstream.strip():
        return {"status": "up_to_date", "message": "Already up to date — nothing new to pull.", "reload": None}

    ok, out = _run_git("pull", "--ff-only", "origin")
    if not ok:
        return {
            "status": "error",
            "message": (
                "git pull --ff-only failed, so nothing was changed on disk: " + out +
                ". This usually means a tracked file was edited directly on the server outside "
                "of git — whoever set up this deployment will need to sort it out from a Bash console."
            ),
            "reload": None,
        }

    return {"status": "pulled", "message": out, "reload": trigger_reload()}


def trigger_reload():
    """Calls PythonAnywhere's official web-app reload API so the already-
    running process actually starts executing the code that was just
    pulled -- a git pull alone only changes the files on disk; the live
    process keeps running the old code in memory until something reloads
    it. Returns {'configured': False, ...} if the three env vars above
    aren't all set -- that's not an error, it just means whoever's running
    this needs to click Reload on the PythonAnywhere Web tab by hand once
    to finish applying the update."""
    if not (PYTHONANYWHERE_USERNAME and PYTHONANYWHERE_DOMAIN and PYTHONANYWHERE_API_TOKEN):
        return {
            "configured": False,
            "ok": False,
            "message": "Code pulled, but auto-reload isn't set up — click Reload on your PythonAnywhere Web tab to finish applying the update.",
        }
    url = f"https://www.pythonanywhere.com/api/v0/user/{PYTHONANYWHERE_USERNAME}/webapps/{PYTHONANYWHERE_DOMAIN}/reload/"
    try:
        resp = requests.post(
            url, headers={"Authorization": f"Token {PYTHONANYWHERE_API_TOKEN}"}, timeout=RELOAD_TIMEOUT
        )
    except requests.RequestException as exc:
        return {"configured": True, "ok": False, "message": f"Code pulled, but the reload API call failed: {exc}"}
    if resp.status_code == 200:
        return {
            "configured": True,
            "ok": True,
            "message": "Reload triggered — the site will be running the new code within a few seconds.",
        }
    return {
        "configured": True,
        "ok": False,
        "message": f"Code pulled, but the reload API returned HTTP {resp.status_code}: {resp.text[:200]}",
    }
