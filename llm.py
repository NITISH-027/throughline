"""Talks to the Gemini API using only the Python standard library.

The key is read from the GEMINI_API_KEY environment variable. It is never stored
in a file and never shown in the app.
"""
import os
import json
import urllib.request

MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")


def available():
    return bool(os.environ.get("GEMINI_API_KEY"))


def _call(prompt, as_json):
    key = os.environ["GEMINI_API_KEY"]
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"
    config = {"temperature": 0.1}
    if as_json:
        config["responseMimeType"] = "application/json"
    body = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": config}
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "x-goog-api-key": key},
    )
    with urllib.request.urlopen(req, timeout=90) as resp:
        data = json.load(resp)
    return data["candidates"][0]["content"]["parts"][0]["text"]


def ask_json(prompt):
    text = _call(prompt, True).strip()
    if text.startswith("```"):  # some models wrap JSON in code fences
        text = text.strip("`")
        text = text[text.find("\n") + 1:]
    return json.loads(text)


def ask_text(prompt):
    return _call(prompt, False).strip()
