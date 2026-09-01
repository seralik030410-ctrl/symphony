"""Fixed entry point. Only launched by the document runner, inside its container."""
import json
from pathlib import Path
import sys

from .renderers import render_job


if __name__ == "__main__":
    try:
        render_job(Path(sys.argv[1]))
        print(json.dumps({"ok": True}))
    except Exception as error:
        print(json.dumps({"ok": False, "error": str(error)[:2000]}))
        sys.exit(1)
