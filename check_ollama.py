import os
import re
import sys

import requests

cfg = {}
try:
    with open("OllamaConfig.txt") as f:
        for line in f:
            m = re.match(r"^([A-Za-z_]+)\s*=\s*(.+?)\s*$", line)
            if m:
                cfg[m.group(1).upper()] = m.group(2)
except FileNotFoundError:
    pass

host = cfg.get("HOST") or os.environ.get("OLLAMA_HOST", "http://localhost:11434")
model = cfg.get("MODEL", "llama3.2")

try:
    tags = requests.get(f"{host}/api/tags", timeout=5).json()
    names = [m.get("name", "") for m in tags.get("models", [])]
except Exception as exc:
    print(f"[FAIL] {host} unreachable ({type(exc).__name__})")
    sys.exit(1)

print(f"[OK]   {host} - {len(names)} models")
if model not in names:
    print(f"[WARN] MODEL={model} is not installed on that host.")
    print(f"       available: {', '.join(names[:12])}")
    sys.exit(2)
print(f"[OK]   model '{model}' present")
sys.exit(0)
