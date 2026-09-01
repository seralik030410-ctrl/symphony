"""Opt-in public-network + local Ollama checks using an isolated database.

Only two fixed public URLs/queries may leave the process. No user chats or files
are loaded. Search-provider blocking is recorded separately, never called success.
"""
import asyncio
import json
import os
from pathlib import Path
import sys
import time
import uuid

import httpx

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "data" / "acceptance" / ("stage7-" + uuid.uuid4().hex[:10])
os.environ.update(SYMPHONY_DATABASE_PATH=str(RUN / "symphony.db"),
                  SYMPHONY_WORKSPACE_ROOT=str(RUN / "workspaces"),
                  SYMPHONY_SKILLS_ROOT=str(RUN / "skills"), SYMPHONY_SEED_BUNDLED_SKILLS="0")

from backend.config import Settings
from backend.main import create_app
from backend.tools.contracts import ToolContext, ToolError
from backend.tools.web import SearchInput

URL = "https://docs.python.org/3/library/asyncio.html"


async def main():
    model = os.getenv("SYMPHONY_LIVE_MODEL", "qwen3.5:9b")
    app = create_app(Settings.from_env())
    runtime = app.state.runtime
    report = {"ok": False, "model": model, "checks": {}}
    try:
        async with app.router.lifespan_context(app), httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/sessions", json={"title": "Stage 7 public research QA", "provider": "ollama", "model": model})
            response.raise_for_status(); session_id = response.json()["id"]
            response = await client.put(f"/api/sessions/{session_id}/research", json={"enabled": True, "allowed_domains": ["docs.python.org"]})
            response.raise_for_status()
            response = await client.post(f"/api/sessions/{session_id}/turns", json={"content": f"Use web.open to read {URL}. In one sentence explain what asyncio is for, linking the page you actually read and stating when you checked it. Do not search or run other tools."})
            response.raise_for_status(); turn_id = response.json()["turn"]["id"]
            print("Local Ollama + public HTTPS page", flush=True)
            deadline = time.monotonic() + 240
            while time.monotonic() < deadline:
                current = runtime.repository.get_turn(turn_id)
                if current["status"] in {"completed", "failed", "interrupted", "cancelled"}: break
                # Never approve an unexpected model request.
                if (await client.get(f"/api/sessions/{session_id}/approvals")).json():
                    await runtime.turn_service.cancel(turn_id)
                    raise AssertionError("Model requested unexpected approval; test did not grant it")
                await asyncio.sleep(.5)
            else:
                await runtime.turn_service.cancel(turn_id)
                raise AssertionError("Local-model check timed out")
            assert current["status"] == "completed", current["status"]
            sources = (await client.get(f"/api/sessions/{session_id}/research/sources?turn_id={turn_id}")).json()
            answer = runtime.repository.get_message(current["assistant_message_id"])["content"]
            assert any(source["url"] == URL and source["kind"] == "page" for source in sources), "No verified page source"
            assert URL in answer, "No citation to the read page"
            events = runtime.repository.list_events(turn_id)
            assert {"research.requested", "research.received", "research.sources"} <= {item["type"] for item in events}
            report["checks"]["page_and_citation"] = {"answer": answer, "sources": sources}
            # Explicit opt-in to this fixed, public test query only. Production
            # model searches still require the real approval flow (pytest covers it).
            print("Public search-adapter check", flush=True)
            try:
                result = await runtime.tools.get("web.search").execute(
                    ToolContext(session_id, turn_id, network_approved=True), SearchInput(query="Python asyncio documentation"))
                report["checks"]["search"] = {"ok": True, "sources": result.output["sources"]}
            except ToolError as error:
                report["checks"]["search"] = {"ok": False, "code": error.code, "message": str(error)}
            other = (await client.post("/api/sessions", json={"title": "Stage 7 isolation QA"})).json()["id"]
            assert not (await client.get(f"/api/sessions/{other}/research")).json()["enabled"]
            assert not (await client.get(f"/api/sessions/{other}/research/sources")).json()
            report["checks"]["new_chat_isolation"] = True
            report["ok"] = report["checks"]["search"]["ok"]
    finally:
        RUN.mkdir(parents=True, exist_ok=True)
        (RUN / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"ok": report["ok"], "report": str(RUN / "report.json")}), flush=True)
    return report["ok"]


if __name__ == "__main__":
    sys.exit(0 if asyncio.run(main()) else 1)
