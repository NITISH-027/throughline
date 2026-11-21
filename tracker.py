"""Step 3: post approved tasks to a task tracker.

Local tracker (always on): tasks live in this app's own board. REAL, but local.
GitHub Issues (optional): set GITHUB_TOKEN and GITHUB_REPO (owner/name) and approved
tasks also become real GitHub issues. Not tested against your repo by the author.
"""
import os
import json
import urllib.request


def github_enabled():
    return bool(os.environ.get("GITHUB_TOKEN") and os.environ.get("GITHUB_REPO"))


def post(action):
    """Called ONLY after the user presses Confirm. Returns a reference string."""
    ref = f"TL-{action['id']}"
    if github_enabled():
        try:
            repo = os.environ["GITHUB_REPO"]
            body = {"title": action["task"],
                    "body": f"Owner: {action['owner']}\nDeadline: {action['deadline'] or 'none'}\nFrom meeting: {action.get('meeting_title', '')}"}
            req = urllib.request.Request(
                f"https://api.github.com/repos/{repo}/issues",
                data=json.dumps(body).encode(),
                headers={"Authorization": "Bearer " + os.environ["GITHUB_TOKEN"],
                         "Accept": "application/vnd.github+json", "Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=20) as r:
                ref = f"GH#{json.load(r)['number']}"
        except Exception:
            ref += " (GitHub failed, saved locally)"
    return ref
