"""Step 2: compare NEW decisions against the cross-meeting memory.

This is what turns a summariser into a system. AI mode asks the LLM to judge
contradictions; fallback mode uses topic matching plus a text-difference check.
"""
import re
import llm


def detect(new_decisions, memory):
    """new_decisions: [{text, topic}] ; memory: [{id, text, topic, meeting_title, meeting_date}].
    Returns [{new_index, old_id, explanation}] and the mode used."""
    if not new_decisions or not memory:
        return [], "none"
    if llm.available():
        try:
            return _detect_ai(new_decisions, memory), "ai"
        except Exception:
            pass
    return _detect_rules(new_decisions, memory), "fallback"


def _detect_ai(new, memory):
    old = "\n".join(f'{m["id"]}: [{m["meeting_date"]}] {m["text"]}' for m in memory)
    nw = "\n".join(f"{i}: {d['text']}" for i, d in enumerate(new))
    prompt = f"""You check a team's decision memory for contradictions.
EARLIER ACTIVE DECISIONS (id: [date] text):
{old}

NEW DECISIONS FROM TODAY'S MEETING (index: text):
{nw}

Find new decisions that CONTRADICT or REVERSE an earlier decision (same subject, different outcome). Ignore decisions that merely repeat or add to an earlier one.
Return ONLY JSON: {{"conflicts":[{{"new_index":0,"old_id":3,"explanation":"one plain sentence saying what changed"}}]}}"""
    data = llm.ask_json(prompt)
    valid_ids = {m["id"] for m in memory}
    out = []
    for c in data.get("conflicts", []):
        if int(c["old_id"]) in valid_ids and 0 <= int(c["new_index"]) < len(new):
            out.append({"new_index": int(c["new_index"]), "old_id": int(c["old_id"]),
                        "explanation": str(c["explanation"])})
    return out


def _nice(iso):
    from datetime import date
    d = date.fromisoformat(iso)
    return f"{d.day} {d.strftime('%b')}"


def _words(text):
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def _detect_rules(new, memory):
    out = []
    for i, d in enumerate(new):
        if d["topic"] == "general":
            continue
        for m in memory:
            if m["topic"] != d["topic"]:
                continue
            a, b = _words(d["text"]), _words(m["text"])
            overlap = len(a & b) / max(1, len(a | b))
            if overlap > 0.7:
                continue  # basically the same decision restated
            out.append({"new_index": i, "old_id": m["id"],
                        "explanation": f'Same topic ("{d["topic"]}") as the decision from "{m["meeting_title"]}" ({_nice(m["meeting_date"])}), but the outcome is different.'})
    return out
