# Throughline: meeting-to-execution agent (Product Space PS 03)

Paste a meeting transcript. Throughline finds the decisions, action items, owners and
deadlines, checks the decisions against what the team decided in EARLIER meetings, and
posts tasks to a tracker only after you confirm.

## Run it (Windows PowerShell)

Open PowerShell inside this folder (the one with app.py), then run these one at a time:

```
python -m venv venv
venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py
```

Then open http://127.0.0.1:5000 in your browser.

If PowerShell blocks the activate step, run this once, then activate again:

```
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

## Turn on the real AI (optional, your own key)

Get a Gemini API key from Google AI Studio. Set it in the SAME PowerShell window, before `python app.py`:

```
$env:GEMINI_API_KEY = "paste-your-key-here"
```

Optional model override:

```
$env:GEMINI_MODEL = "gemini-2.5-flash"
```

The top-right chip shows "AI LIVE" when a key is found, otherwise "AI: FALLBACK RULES".
The key is only read from the environment. It is never saved in a file.

## Optional: real GitHub Issues

```
$env:GITHUB_TOKEN = "your-token"
$env:GITHUB_REPO = "yourname/yourrepo"
```

## Demo in 60 seconds

1. Top of the page, press "Load demo" in the nav. This confirms last week's kickoff meeting into memory.
2. Capture opens with the "replanning" meeting filled in. Press Analyze.
3. Review: four conflict cards (launch date, database, budget, desktop vs mobile). Choose Replace or Keep for each.
4. Tick the tasks you want, press Review and confirm, then Confirm and post.
5. Memory shows each decision's history. Board shows reminders. Change the TODAY date (top right) to see reminders move. Digest shows one summary per person.

## What is real and what is not

REAL
- Transcript parsing with speaker names.
- Decision and action extraction by Gemini when you set a key.
- Conflict judging against stored decisions (Gemini with a key).
- Memory in a SQLite file (throughline.db). Delete the file to reset.
- The confirmation gate: the server refuses to post or save anything without confirm=true.
- Local task board, deadline reminders (computed from the TODAY date), per-person digest.
- GitHub Issues posting if you set the two variables above (not tested by the author).

SIMPLE OR NOT REAL
- Without a key, "fallback rules" use plain Python patterns. They handle clear sentences like
  "Ravi, can you fix the bug by Friday?" and "We decided to ...", and miss subtle ones.
- The Gemini path was written to the public API format but not run with a live key by the author.
  If the AI call fails, the app tells you and falls back to rules.
- Reminders show inside the app only. No email, WhatsApp or push.
- The digest is shown on screen. It is not sent to anyone.
- The sample meetings are made up.

## Edge cases it handles

- Decision reversed later: both stay in Memory, the old one struck through and linked to the new one.
- Same decision repeated: not flagged as a conflict.
- No owner ("someone should..."): shown as Unassigned, cannot be approved until you type a name.
- Owner not in the meeting: amber warning.
- "next Friday", "end of month", "next week": amber "Check the date" warning.
- No deadline: allowed, shown in the digest as "needs a deadline", never in reminders.
- Task similar to an open one: shown unticked with a button to update the old task instead of creating a copy.
- Task you do not tick: marked rejected, never sent.
- Speaker mix-ups: "Ravi, can you..." goes to Ravi, not the speaker. The original sentence is shown under every task and every field is editable.

## Files

- app.py: Flask server and database. Start reading here.
- extractor.py: transcript to decisions and actions (AI or rules).
- conflicts.py: compares new decisions with memory.
- dates.py: turns "by Friday" into a date.
- tracker.py: posts a task to the board (and GitHub if set).
- llm.py: the Gemini call, standard library only.
- index.html, static/style.css, static/app.js: the interface.
- IMAGE_PROMPTS.md: prompts for optional hero art.

## Art

The 3D art is already in the static folder (heroobj.png, av1-5.png, pin1-4.png, bit1-4.png).
To swap any image, save a new file with the same name. The page has plain fallbacks if a file is missing.
