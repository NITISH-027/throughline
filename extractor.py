"""Step 1 of the pipeline: transcript -> speaker lines -> decisions + action items.

Two modes:
  * AI mode   : Gemini reads the transcript and returns structured JSON (real LLM).
  * Fallback  : plain Python rules (regex). Works offline, less clever. Used when no
                key is set or the API call fails, so the demo never breaks.
"""
import re
from datetime import date
import llm
from dates import find_deadline

LINE = re.compile(r"^\s*(?:\[?\d{1,2}:\d{2}(?::\d{2})?\]?\s*)?([A-Za-z][\w .'-]{0,30}):\s*(.+)$")

# Topic words: used by the fallback to decide which decisions talk about the same thing.
TOPICS = [
    ("budget", ["budget", "spend", "cost"]),
    ("database", ["database", "postgres", "mongodb", "mysql", "sqlite", "db "]),
    ("platform", ["desktop", "mobile", "web version", "platform"]),
    ("launch date", ["launch", "go live", "release date", "ship on"]),
]

DECISION_CUES = ["we decided", "we agreed", "decision:", "the team agreed", "let's go with", "lets go with",
                 "we will go with", "we're moving", "we are moving", "switch the", "switch to",
                 "we will also", "we'll also", "final call", "it's settled"]
ACTION_CUES = [r"\bi'll\b", r"\bi will\b", r"\bi can take\b", r"\bcan you\b", r"\bplease\b",
               r"\baction:", r"\b\w+ will\b", r"\bneeds to\b", r"\bshould\b"]


def parse_transcript(text):
    """Split into [{speaker, text}]. Lines without 'Name:' join the previous line."""
    turns = []
    for raw in text.splitlines():
        if not raw.strip():
            continue
        m = LINE.match(raw)
        if m:
            turns.append({"speaker": m.group(1).strip(), "text": m.group(2).strip()})
        elif turns:
            turns[-1]["text"] += " " + raw.strip()
    return turns


def extract(meeting_date, transcript):
    """Returns {decisions, actions, mode, note, speakers}."""
    turns = parse_transcript(transcript)
    speakers = sorted({t["speaker"] for t in turns})
    if not turns:
        raise ValueError("No speaker lines found. Use lines like 'Asha: We decided to ...'")
    if llm.available():
        try:
            out = _extract_ai(meeting_date, turns)
            out.update(mode="ai", note="Extracted by " + llm.MODEL, speakers=speakers)
            return out
        except Exception as e:  # network, quota, bad JSON ... never crash the demo
            out = _extract_rules(meeting_date, turns)
            out.update(mode="fallback", note=f"AI call failed ({type(e).__name__}); used rules", speakers=speakers)
            return out
    out = _extract_rules(meeting_date, turns)
    out.update(mode="fallback", note="No GEMINI_API_KEY set; used simple rules", speakers=speakers)
    return out


# ---------------------------------------------------------------- AI mode
def _extract_ai(meeting_date, turns):
    transcript = "\n".join(f"{t['speaker']}: {t['text']}" for t in turns)
    prompt = f"""You read a meeting transcript and extract structure. The meeting happened on {meeting_date.isoformat()} ({meeting_date.strftime('%A')}).
Return ONLY JSON of this shape:
{{"decisions":[{{"text":"short statement of what was decided","topic":"1-3 word topic e.g. 'launch date'","speaker":"who stated it"}}],
 "actions":[{{"task":"short imperative task","owner":"person who must do it, exactly as named in the transcript","deadline":"YYYY-MM-DD or null","speaker":"who assigned or volunteered","quote":"the original sentence"}}]}}
Rules: a decision is something the group settled, not a suggestion or a task. An action has one owner. Resolve relative dates ("Friday", "tomorrow") from the meeting date. Do not invent people or deadlines. If the owner is unclear use "Unassigned".

TRANSCRIPT:
{transcript}"""
    data = llm.ask_json(prompt)
    decisions = [{"text": str(d["text"]), "topic": str(d.get("topic") or "general"),
                  "speaker": str(d.get("speaker") or "")} for d in data.get("decisions", [])]
    actions = [{"task": str(a["task"]), "owner": str(a.get("owner") or "Unassigned"),
                "deadline": a.get("deadline") if a.get("deadline") not in ("null", "") else None,
                "quote": str(a.get("quote") or "")} for a in data.get("actions", [])]
    return {"decisions": decisions, "actions": actions}


# ---------------------------------------------------------------- fallback mode
def topic_of(text):
    t = text.lower() + " "
    for name, words in TOPICS:
        if any(w in t for w in words):
            return name
    return "general"


def _sentences(text):
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]


def _extract_rules(meeting_date, turns):
    decisions, actions = [], []
    names = {t["speaker"].split()[0].lower(): t["speaker"] for t in turns}
    for turn in turns:
        for sent in _sentences(turn["text"]):
            low = sent.lower()
            if any(c in low for c in DECISION_CUES):
                text = re.sub(r"^(decision:|we decided( to| on)?|we agreed( to| on)?|the team agreed( to)?)\s*", "", sent, flags=re.I)
                decisions.append({"text": text[:1].upper() + text[1:], "topic": topic_of(sent), "speaker": turn["speaker"]})
                continue
            if any(re.search(c, low) for c in ACTION_CUES):
                owner = turn["speaker"]
                m = re.match(r"^(\w+),\s*(can you|could you|please)", sent, flags=re.I)  # "Ravi, can you ..."
                if re.match(r"^(someone|somebody|we|the team)\s+(should|needs? to|must)\b", low):
                    owner = "Unassigned"  # nobody was named: the UI forces a human to pick
                elif m and m.group(1).lower() in names:
                    owner = names[m.group(1).lower()]
                else:
                    m2 = re.match(r"^(\w+) will\b", sent)
                    if m2 and m2.group(1).lower() in names:
                        owner = names[m2.group(1).lower()]
                    elif not re.search(r"\bi'll\b|\bi will\b|\bi can take\b", low):
                        continue  # vague sentence, no owner: skip rather than guess
                deadline, phrase = find_deadline(sent, meeting_date)
                task = re.sub(r"^\w+,\s*(can you|could you|please)\s*", "", sent, flags=re.I)
                task = re.sub(r"^(i'll|i will|\w+ will|(someone|somebody|we|the team) (should|needs? to|must))\s*", "", task, flags=re.I)
                if phrase:
                    task = re.sub(r"\s*" + re.escape(phrase) + r"\W*$", "", task, flags=re.I)
                task = re.sub(r"\s+(by|on|before)\W*$", "", task.strip(" .?!"), flags=re.I)
                actions.append({"task": task[:1].upper() + task[1:], "owner": owner,
                                "deadline": deadline, "quote": sent, "deadline_phrase": phrase})
    # Keep one decision per topic per meeting (the last one wins), except 'general'.
    seen, kept = set(), []
    for d in reversed(decisions):
        if d["topic"] != "general" and d["topic"] in seen:
            continue
        seen.add(d["topic"])
        kept.append(d)
    return {"decisions": list(reversed(kept)), "actions": actions}
