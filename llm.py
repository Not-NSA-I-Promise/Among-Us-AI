"""Shared Ollama client.

chatGPT.py had its own copy of the config loading and HTTP call; the sabotage
decision needs the same thing, so it lives here once.
"""
import os
import re

import requests

DEFAULTS = {
    "HOST": "http://localhost:11434",
    "MODEL": "llama3.2",
    "NUM_PREDICT": "80",
    "TEMPERATURE": "0.8",
    "THINK": "false",
}


def _load():
    cfg = dict(DEFAULTS)
    try:
        with open("OllamaConfig.txt") as f:
            for line in f:
                m = re.match(r"^([A-Za-z_]+)\s*=\s*(.+?)\s*$", line)
                if m:
                    cfg[m.group(1).upper()] = m.group(2)
    except FileNotFoundError:
        pass
    return cfg


CFG = _load()
HOST = CFG["HOST"]
MODEL = CFG["MODEL"]
NUM_PREDICT = int(CFG["NUM_PREDICT"])
TEMPERATURE = float(CFG["TEMPERATURE"])
THINK = CFG["THINK"].lower() in ("1", "true", "yes")


def reachable():
    try:
        return requests.get(f"{HOST}/api/tags", timeout=5).ok
    except requests.RequestException:
        return False


def ask(messages, num_predict=None, temperature=None, timeout=90):
    """Chat completion. Returns a string (empty string on failure)."""
    payload = {
        "model": MODEL,
        "messages": messages,
        "stream": False,
        "think": THINK,
        "options": {
            "num_predict": NUM_PREDICT if num_predict is None else num_predict,
            "temperature": TEMPERATURE if temperature is None else temperature,
        },
    }
    try:
        r = requests.post(f"{HOST}/api/chat", json=payload, timeout=timeout)
        r.raise_for_status()
        return (r.json().get("message", {}) or {}).get("content", "") or ""
    except requests.RequestException:
        return ""
    except Exception:
        return ""
