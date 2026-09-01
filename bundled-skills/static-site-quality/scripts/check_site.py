from pathlib import Path
import sys

target = Path(sys.argv[1] if len(sys.argv) > 1 else "dist/index.html")
if not target.is_file():
    raise SystemExit(f"missing: {target}")
text = target.read_text(encoding="utf-8")
required = ["<!DOCTYPE html", "<title", "<main", "<h1"]
missing = [item for item in required if item.lower() not in text.lower()]
if missing:
    raise SystemExit("missing structural markers: " + ", ".join(missing))
print(f"site structure ok: {target}")
