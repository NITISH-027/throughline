"""Tiny date helper: turns phrases like 'by Friday' into a real date."""
import re
from datetime import date, timedelta

MONTHS = {m: i + 1 for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july",
     "august", "september", "october", "november", "december"])}
for _full, _n in list(MONTHS.items()):
    MONTHS[_full[:3]] = _n
MONTHS["sept"] = 9
WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def find_deadline(text, meeting_date):
    """Return (iso_date or None, matched_phrase or None)."""
    t = text.lower()
    # "by December 5", "on 5th Dec", "December 5th"
    m = re.search(r"\b(?:by|on|before)?\s*(?:the\s+)?(" + "|".join(MONTHS) + r")\.?\s+(\d{1,2})(?:st|nd|rd|th)?\b", t)
    if m:
        return _month_day(MONTHS[m.group(1)], int(m.group(2)), meeting_date), m.group(0).strip()
    m = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?(" + "|".join(MONTHS) + r")\b", t)
    if m:
        return _month_day(MONTHS[m.group(2)], int(m.group(1)), meeting_date), m.group(0).strip()
    if re.search(r"\btomorrow\b", t):
        return (meeting_date + timedelta(days=1)).isoformat(), "tomorrow"
    if re.search(r"\b(today|tonight|end of day|eod)\b", t):
        return meeting_date.isoformat(), "today"
    m = re.search(r"\b(?:by|on|before|this|next)?\s*(" + "|".join(WEEKDAYS) + r")\b", t)
    if m:
        target = WEEKDAYS.index(m.group(1))
        delta = (target - meeting_date.weekday()) % 7 or 7
        # "next Friday" said on a Monday usually means the Friday of NEXT week.
        if "next" in m.group(0) and meeting_date.weekday() + delta < 7:
            delta += 7
        return (meeting_date + timedelta(days=delta)).isoformat(), m.group(0).strip()
    if re.search(r"\bend of (the )?month\b", t):
        nxt = date(meeting_date.year + (meeting_date.month == 12), meeting_date.month % 12 + 1, 1)
        return (nxt - timedelta(days=1)).isoformat(), "end of month"
    if re.search(r"\bnext week\b", t):
        return (meeting_date + timedelta(days=7)).isoformat(), "next week"
    if re.search(r"\b(end of (the )?week|this week)\b", t):
        delta = (4 - meeting_date.weekday()) % 7
        return (meeting_date + timedelta(days=delta)).isoformat(), "end of week"
    return None, None


def _month_day(month, day, meeting_date):
    try:
        d = date(meeting_date.year, month, day)
    except ValueError:
        return None
    if d < meeting_date:
        d = date(meeting_date.year + 1, month, day)
    return d.isoformat()


def is_ambiguous(sentence):
    """True when the phrase has more than one reasonable reading, so a human should check."""
    t = sentence.lower()
    return bool(re.search(r"\bnext (" + "|".join(WEEKDAYS) + r")\b|\bnext week\b|\bend of (the )?month\b|\bthis week\b|\bsoon\b|\bsometime\b|\bASAP\b", t, re.I))
