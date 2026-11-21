"""Throughline: meeting-to-execution agent. Flask backend.

Run:  python app.py   then open http://127.0.0.1:5000
Data lives in throughline.db (SQLite, next to this file). Delete it to start fresh.
"""
import os
import re
import json
import sqlite3
from datetime import date, timedelta
from flask import Flask, jsonify, request, send_from_directory, g

import llm
import tracker
import conflicts as conflict_engine
from extractor import extract
from dates import is_ambiguous

BASE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE, "throughline.db")
app = Flask(__name__, static_folder="static", static_url_path="/static")

SCHEMA = """
CREATE TABLE IF NOT EXISTS meetings(id INTEGER PRIMARY KEY, title TEXT, date TEXT, transcript TEXT,
    status TEXT DEFAULT 'review', mode TEXT, note TEXT, speakers TEXT);
CREATE TABLE IF NOT EXISTS decisions(id INTEGER PRIMARY KEY, meeting_id INT, text TEXT, topic TEXT, speaker TEXT,
    status TEXT DEFAULT 'proposed', superseded_by INT);
CREATE TABLE IF NOT EXISTS actions(id INTEGER PRIMARY KEY, meeting_id INT, task TEXT, owner TEXT, deadline TEXT,
    quote TEXT, status TEXT DEFAULT 'staged', approved INT DEFAULT 0, tracker_ref TEXT, flags TEXT DEFAULT '[]');
CREATE TABLE IF NOT EXISTS conflicts(id INTEGER PRIMARY KEY, meeting_id INT, new_decision_id INT, old_decision_id INT,
    explanation TEXT, resolution TEXT);
"""


def db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.executescript(SCHEMA)
    return g.db


@app.teardown_appcontext
def close_db(_):
    d = g.pop("db", None)
    if d:
        d.close()


def rows(sql, *args):
    return [dict(r) for r in db().execute(sql, args).fetchall()]


def one(sql, *args):
    r = db().execute(sql, args).fetchone()
    return dict(r) if r else None


# ------------------------------------------------------------ pipeline
def process_meeting(title, meeting_date, transcript):
    """Extract -> detect conflicts -> store everything as 'proposed' (nothing is posted yet)."""
    out = extract(meeting_date, transcript)
    c = db()
    mid = c.execute("INSERT INTO meetings(title,date,transcript,mode,note,speakers) VALUES(?,?,?,?,?,?)",
                    (title, meeting_date.isoformat(), transcript, out["mode"], out["note"],
                     json.dumps(out["speakers"]))).lastrowid
    memory = rows("""SELECT d.id, d.text, d.topic, m.title AS meeting_title, m.date AS meeting_date
                     FROM decisions d JOIN meetings m ON m.id=d.meeting_id WHERE d.status='active'""")
    new_ids = []
    for d in out["decisions"]:
        new_ids.append(c.execute("INSERT INTO decisions(meeting_id,text,topic,speaker) VALUES(?,?,?,?)",
                                 (mid, d["text"], d["topic"], d["speaker"])).lastrowid)
    found, cmode = conflict_engine.detect(out["decisions"], memory)
    for f in found:
        c.execute("INSERT INTO conflicts(meeting_id,new_decision_id,old_decision_id,explanation) VALUES(?,?,?,?)",
                  (mid, new_ids[f["new_index"]], f["old_id"], f["explanation"]))
    open_tasks = rows("SELECT id, task, owner FROM actions WHERE status IN ('posted','staged') AND approved>=0")
    first_names = {s.split()[0].lower() for s in out["speakers"]}
    for a in out["actions"]:
        flags = []
        owner = a["owner"]
        if owner.lower() in ("unassigned", "someone", "somebody", "team", "everyone", ""):
            owner = "Unassigned"
            flags.append("no_owner")
        elif owner.split()[0].lower() not in first_names:
            flags.append("unknown_owner")
        if not a["deadline"]:
            flags.append("no_deadline")
        elif is_ambiguous(a.get("quote", "")):
            flags.append("check_date")
        dup = _find_duplicate(a, owner, open_tasks)
        if dup:
            flags.append(f"duplicate:{dup}")
        # Pre-tick only clean tasks. Tasks with no owner or a possible duplicate start unticked.
        pre = 0 if any(f == "no_owner" or f.startswith("duplicate:") for f in flags) else 1
        c.execute("INSERT INTO actions(meeting_id,task,owner,deadline,quote,flags,approved) VALUES(?,?,?,?,?,?,?)",
                  (mid, a["task"], owner, a["deadline"], a.get("quote", ""), json.dumps(flags), pre))
    c.commit()
    return mid, cmode


def _find_duplicate(a, owner, open_tasks):
    """Same owner and mostly the same words as a task that is already open."""
    words = lambda t: set(re.findall(r"[a-z]{3,}", t.lower()))
    mine = words(a["task"])
    for t in open_tasks:
        if t["owner"].split()[0].lower() != owner.split()[0].lower():
            continue
        theirs = words(t["task"])
        if mine and len(mine & theirs) / len(mine | theirs) >= 0.5:
            return t["id"]
    return None


def meeting_view(mid):
    m = one("SELECT * FROM meetings WHERE id=?", mid)
    if not m:
        return None
    m["speakers"] = json.loads(m["speakers"] or "[]")
    m["decisions"] = rows("SELECT * FROM decisions WHERE meeting_id=?", mid)
    acts = rows("SELECT * FROM actions WHERE meeting_id=?", mid)
    for a in acts:
        a["flags"] = json.loads(a["flags"])
    m["actions"] = [a for a in acts if a["status"] != "merged"]
    m["merged"] = [a for a in acts if a["status"] == "merged"]
    m["conflicts"] = rows("""SELECT c.*, nd.text AS new_text, od.text AS old_text, om.title AS old_meeting,
                             om.date AS old_date FROM conflicts c
                             JOIN decisions nd ON nd.id=c.new_decision_id
                             JOIN decisions od ON od.id=c.old_decision_id
                             JOIN meetings om ON om.id=od.meeting_id WHERE c.meeting_id=?""", mid)
    return m


# ------------------------------------------------------------ routes
@app.route("/")
def home():
    return send_from_directory(BASE, "index.html")


@app.route("/api/status")
def status():
    import glob
    art = {k: sorted("/static/" + os.path.basename(p) for p in glob.glob(os.path.join(BASE, "static", k + "*.png")))
           for k in ("av", "pin", "bit")}
    return jsonify(ai=llm.available(), model=llm.MODEL if llm.available() else None,
                   github=tracker.github_enabled(), today=date.today().isoformat(), art=art)


@app.route("/api/meetings", methods=["GET", "POST"])
def meetings():
    if request.method == "GET":
        return jsonify(rows("SELECT id,title,date,status,mode FROM meetings ORDER BY date DESC, id DESC"))
    body = request.get_json(force=True)
    try:
        d = date.fromisoformat(body.get("date") or date.today().isoformat())
        mid, cmode = process_meeting((body.get("title") or "Untitled meeting").strip(), d, body.get("transcript", ""))
    except ValueError as e:
        return jsonify(error=str(e)), 400
    v = meeting_view(mid)
    v["conflict_mode"] = cmode
    return jsonify(v)


@app.route("/api/meetings/<int:mid>")
def meeting(mid):
    v = meeting_view(mid)
    return (jsonify(v), 200) if v else (jsonify(error="not found"), 404)


@app.route("/api/actions/<int:aid>", methods=["PATCH"])
def edit_action(aid):
    b = request.get_json(force=True)
    c = db()
    a = one("SELECT * FROM actions WHERE id=?", aid)
    if not a or a["status"] != "staged":
        return jsonify(error="only staged tasks can be edited"), 400
    task = b.get("task", a["task"])
    owner = b.get("owner", a["owner"]).strip() or "Unassigned"
    deadline = b.get("deadline", a["deadline"]) or None
    flags = [f for f in json.loads(a["flags"]) if f not in ("no_owner", "unknown_owner", "no_deadline", "check_date")
             or (f == "no_owner" and owner == "Unassigned") or (f == "no_deadline" and not deadline)]
    approved = int(b.get("approved", a["approved"]))
    if approved == 1 and owner == "Unassigned":
        return jsonify(error="Pick an owner before approving this task"), 400
    c.execute("UPDATE actions SET task=?, owner=?, deadline=?, approved=?, flags=? WHERE id=?",
              (task, owner, deadline, approved, json.dumps(flags), aid))
    c.commit()
    return jsonify(ok=True, flags=flags)


@app.route("/api/actions/<int:aid>/merge", methods=["POST"])
def merge_action(aid):
    """A revised task: update the existing open task instead of creating a second one."""
    a = one("SELECT * FROM actions WHERE id=?", aid)
    old_id = request.get_json(force=True).get("into")
    old = one("SELECT * FROM actions WHERE id=? AND status='posted'", old_id)
    if not a or not old or a["status"] != "staged":
        return jsonify(error="nothing to merge into"), 400
    c = db()
    c.execute("UPDATE actions SET deadline=?, owner=?, task=? WHERE id=?", (a["deadline"] or old["deadline"], a["owner"], a["task"], old_id))
    c.execute("UPDATE actions SET status='merged', approved=0, tracker_ref=? WHERE id=?", (f"merged into TL-{old_id}", aid))
    c.commit()
    return jsonify(ok=True)


@app.route("/api/conflicts/<int:cid>/resolve", methods=["POST"])
def resolve(cid):
    r = request.get_json(force=True).get("resolution")
    if r not in ("replace", "keep_old"):
        return jsonify(error="resolution must be replace or keep_old"), 400
    db().execute("UPDATE conflicts SET resolution=? WHERE id=?", (r, cid))
    db().commit()
    return jsonify(ok=True)


@app.route("/api/meetings/<int:mid>/commit", methods=["POST"])
def commit(mid):
    """The confirmation gate. Nothing is posted or saved to memory unless confirm is true."""
    if not request.get_json(force=True).get("confirm"):
        return jsonify(error="Confirmation required before posting"), 400
    m = meeting_view(mid)
    if not m or m["status"] != "review":
        return jsonify(error="meeting is not awaiting review"), 400
    if any(c["resolution"] is None for c in m["conflicts"]):
        return jsonify(error="Resolve every conflict first (replace the old decision or keep it)"), 400
    c = db()
    # 1) memory: apply conflict choices
    losing_new = set()
    for cf in m["conflicts"]:
        if cf["resolution"] == "replace":
            c.execute("UPDATE decisions SET status='superseded', superseded_by=? WHERE id=?",
                      (cf["new_decision_id"], cf["old_decision_id"]))
        else:
            losing_new.add(cf["new_decision_id"])
    for d in m["decisions"]:
        c.execute("UPDATE decisions SET status=? WHERE id=?", ("rejected" if d["id"] in losing_new else "active", d["id"]))
    # 2) tracker: post ONLY approved tasks; the rest are marked rejected and never sent
    posted = []
    for a in m["actions"]:
        if a["approved"] == 1:
            ref = tracker.post({**a, "meeting_title": m["title"]})
            c.execute("UPDATE actions SET status='posted', tracker_ref=? WHERE id=?", (ref, a["id"]))
            posted.append({"id": a["id"], "ref": ref, "task": a["task"]})
        else:
            c.execute("UPDATE actions SET status='rejected' WHERE id=?", (a["id"],))
    c.execute("UPDATE meetings SET status='committed' WHERE id=?", (mid,))
    c.commit()
    return jsonify(ok=True, posted=posted)


@app.route("/api/meetings/<int:mid>/discard", methods=["POST"])
def discard(mid):
    c = db()
    c.execute("UPDATE decisions SET status='rejected' WHERE meeting_id=?", (mid,))
    c.execute("UPDATE actions SET status='rejected' WHERE meeting_id=?", (mid,))
    c.execute("UPDATE meetings SET status='discarded' WHERE id=?", (mid,))
    c.commit()
    return jsonify(ok=True)


@app.route("/api/memory")
def memory():
    ds = rows("""SELECT d.*, m.title AS meeting_title, m.date AS meeting_date FROM decisions d
                 JOIN meetings m ON m.id=d.meeting_id WHERE d.status IN ('active','superseded')
                 ORDER BY m.date, d.id""")
    return jsonify(ds)


@app.route("/api/board")
def board():
    acts = rows("""SELECT a.*, m.title AS meeting_title FROM actions a JOIN meetings m ON m.id=a.meeting_id
                   WHERE a.status IN ('posted','done') ORDER BY a.deadline IS NULL, a.deadline""")
    return jsonify(acts)


@app.route("/api/actions/<int:aid>/done", methods=["POST"])
def done(aid):
    db().execute("UPDATE actions SET status=? WHERE id=?",
                 ("done" if request.get_json(force=True).get("done", True) else "posted", aid))
    db().commit()
    return jsonify(ok=True)


def _today():
    try:
        return date.fromisoformat(request.args.get("today", ""))
    except ValueError:
        return date.today()


@app.route("/api/reminders")
def reminders():
    """Open tasks that are overdue or due within 2 days of the (demo) 'today'."""
    t = _today()
    out = []
    for a in rows("SELECT * FROM actions WHERE status='posted' AND deadline IS NOT NULL ORDER BY deadline"):
        days = (date.fromisoformat(a["deadline"]) - t).days
        if days <= 2:
            kind = "overdue" if days < 0 else ("today" if days == 0 else "soon")
            msg = (f"{a['owner']}: '{a['task']}' was due {abs(days)} day(s) ago" if days < 0 else
                   f"{a['owner']}: '{a['task']}' is due " + ("today" if days == 0 else f"in {days} day(s)"))
            out.append({**a, "kind": kind, "days": days, "message": msg})
    return jsonify(out)


@app.route("/api/digest")
def digest():
    t = _today()
    week_end = t + timedelta(days=7)
    people = {}
    for a in rows("SELECT * FROM actions WHERE status IN ('posted','done')"):
        p = people.setdefault(a["owner"], {"person": a["owner"], "overdue": [], "due_week": [], "no_deadline": [], "done": []})
        if a["status"] == "done":
            p["done"].append(a)
        elif not a["deadline"]:
            p["no_deadline"].append(a)
        else:
            d = date.fromisoformat(a["deadline"])
            if d < t:
                p["overdue"].append(a)
            elif d <= week_end:
                p["due_week"].append(a)
    changed = rows("""SELECT d.text, d.speaker, m.date FROM decisions d JOIN meetings m ON m.id=d.meeting_id
                      WHERE d.status='active' AND m.date>=?""", (t - timedelta(days=7)).isoformat())
    for p in people.values():
        p["narrative"] = _narrative(p, changed, t)
    return jsonify(list(people.values()))


def _narrative(p, decisions, t):
    facts = (f"Person: {p['person']}. Overdue: {[x['task'] for x in p['overdue']]}. "
             f"Due in the next 7 days: {[(x['task'], x['deadline']) for x in p['due_week']]}. "
             f"No deadline set: {[x['task'] for x in p['no_deadline']]}. Done: {len(p['done'])}. "
             f"Recent team decisions: {[d['text'] for d in decisions]}.")
    if llm.available():
        try:
            return llm.ask_text("Write a friendly weekly digest of 3 to 4 short sentences for this person, in second "
                                "person, plain words, no headings. Use ONLY these facts, invent nothing.\n" + facts)
        except Exception:
            pass
    bits = []
    if p["overdue"]:
        bits.append(f"{len(p['overdue'])} overdue, start with '{p['overdue'][0]['task']}'")
    if p["due_week"]:
        bits.append(f"{len(p['due_week'])} due this week")
    if p["no_deadline"]:
        bits.append(f"{len(p['no_deadline'])} still need a deadline")
    return (f"{p['person']}: " + ("; ".join(bits) if bits else "nothing open, nice.") + ".")


# ------------------------------------------------------------ demo helpers
def _sample_texts(today):
    f = lambda d: d.strftime("%B %d").replace(" 0", " ")
    d1, d2 = today - timedelta(days=7), today
    m1 = f"""Asha: Okay, kickoff for the Orbit app. First the launch date. We decided to launch on December 5.
Ravi: For the database, let's go with Postgres.
Meera: I'll deliver the onboarding mockups by {f(today + timedelta(days=1))}.
Kabir: The budget for the launch campaign is 2 lakh rupees. We agreed on a budget of 2 lakh.
Asha: Ravi, can you set up the staging server by {f(today - timedelta(days=3))}?
Kabir: I will draft the launch announcement by December 1.
Asha: Decision: the app will be mobile only, no desktop version.
Asha: Someone should check the app store rules."""
    m2 = f"""Asha: Update time. Because of the vendor delay, we are moving the launch to December 19.
Ravi: The team agreed to switch to MongoDB for the database, it fits our data better.
Kabir: We decided to raise the campaign budget to 3 lakh rupees.
Meera: I'll finish the onboarding mockups by {f(today + timedelta(days=4))}.
Asha: Ravi, can you fix the login bug by tomorrow?
Asha: Decision: we will also build a desktop version in the first release.
Kabir: I will send the investor update by next Friday.
Priya: I'll prepare the demo script."""
    return (d1, m1), (d2, m2)


@app.route("/api/sample")
def sample():
    (d1, m1), (d2, m2) = _sample_texts(date.today())
    return jsonify(meeting1={"title": "Orbit kickoff", "date": d1.isoformat(), "transcript": m1},
                   meeting2={"title": "Orbit replanning", "date": d2.isoformat(), "transcript": m2})


@app.route("/api/demo", methods=["POST"])
def demo():
    """Loads meeting 1 straight into memory, so meeting 2 can show conflicts."""
    c = db()
    old = c.execute("SELECT id FROM meetings WHERE title='Orbit kickoff' AND status='committed'").fetchone()
    if old:  # pressing the button twice must not add the same decisions twice
        return jsonify(ok=True, meeting_id=old["id"], already_loaded=True)
    (d1, m1), _ = _sample_texts(date.today())
    mid, _ = process_meeting("Orbit kickoff", d1, m1)
    c.execute("UPDATE actions SET approved=1 WHERE meeting_id=? AND owner!='Unassigned'", (mid,))
    c.commit()
    with app.test_request_context(json={"confirm": True}):
        commit(mid)
    return jsonify(ok=True, meeting_id=mid)


@app.route("/api/reset", methods=["POST"])
def reset():
    c = db()
    for t in ("meetings", "decisions", "actions", "conflicts"):
        c.execute(f"DELETE FROM {t}")
    c.commit()
    return jsonify(ok=True)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
