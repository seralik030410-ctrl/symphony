"""Acceptance against a RUNNING app, real local Ollama and real Docker.

Creates a labelled QA chat. Does not write project files or approve commands.
Any approval must be reviewed in the UI. Evidence remains in data/acceptance/.
"""
import argparse
import asyncio
import json
import time
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin

import httpx


async def verify_saved_turn(client, turn_id, report_dir, base_url):
    turn = (await client.get(f"/api/turns/{turn_id}")).json()
    session = (await client.get(f"/api/sessions/{turn['session_id']}")).json()
    events = (await client.get(f"/api/turns/{turn_id}/events")).json()
    preview = next((e["payload"]["preview_url"] for e in reversed(events) if e["type"] == "preview.ready"), None)
    outputs = [e["payload"] for e in events if e["type"] == "tool.output" and e["payload"].get("name") == "sandbox.shell"]
    commands = [item["output"]["command"] for item in outputs]
    response = await client.get(preview) if preview else None
    preview_ok = response is not None and response.status_code == 200
    assets = {}
    if preview_ok:
        for ref in re.findall(r'(?:src|href)=["\']([^"\']+)["\']', response.text):
            if ref.endswith(('.css', '.js')) and not ref.startswith(('http:', 'https:', '//')):
                assets[ref] = (await client.get(urljoin(preview, ref))).status_code
    # A prior test may already have emitted index.html. A real subsequent build
    # can legitimately change only CSS/JS; require dist changes AND usable assets.
    built_dist = any(any(path.startswith("dist/") for path in item.get("changed_files", [])) for item in outputs if "build" in item["output"]["command"])
    passed = turn["status"] == "completed" and preview_ok and built_dist and all(code == 200 for code in assets.values()) and any("test" in c for c in commands)
    elapsed = (datetime.fromisoformat(turn["finished_at"]) - datetime.fromisoformat(turn["created_at"])).total_seconds() if turn["finished_at"] else None
    report = {"passed": passed, "session_id": session["id"], "turn_id": turn_id,
              "provider": turn["provider"], "model": turn["model"], "context_window": session["context_window"],
              "elapsed_seconds": elapsed, "turn": turn, "commands": commands,
              "preview_url": base_url + preview if preview else None, "preview_http_ok": preview_ok,
              "assets": assets, "build_created_dist": built_dist,
              "events": [e for e in events if e["type"] not in {"model.delta", "model.reasoning_delta", "tool.output_delta"}]}
    path = report_dir / f"stage3-{turn_id}-verified.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"passed": passed, "report": str(path), "preview": report["preview_url"]}), flush=True)
    if not passed:
        raise SystemExit(1)


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8765")
    parser.add_argument("--model", default="qwen3.5:9b")
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument("--verify-turn", help="Recheck saved events/artifacts without calling a model or executing code")
    args = parser.parse_args()
    if args.model.endswith(":cloud"):
        raise SystemExit("Choose an installed local model, not a cloud model")
    report_dir = Path(__file__).resolve().parents[1] / "data" / "acceptance"
    report_dir.mkdir(parents=True, exist_ok=True)
    async with httpx.AsyncClient(base_url=args.url, timeout=30) as client:
        health = (await client.get("/api/health")).json()
        assert health["sandbox"]["ready"], health
        if args.verify_turn:
            await verify_saved_turn(client, args.verify_turn, report_dir, args.url)
            return
        response = await client.post("/api/sessions", json={"title": "Проверка этапа 3 — сайт", "provider": "ollama", "model": args.model})
        response.raise_for_status()
        session = response.json()
        response = await client.post(f"/api/sessions/{session['id']}/turns", json={
            "content": "Создай простой сайт кофейни «Утро»: заголовок, меню из трёх напитков, контакты и кнопка с работающим JavaScript. Собери проект, проверь тестом и покажи preview."
        })
        response.raise_for_status()
        turn_id = response.json()["turn"]["id"]
        print(json.dumps({"session_id": session["id"], "turn_id": turn_id, "model": args.model, "context": session["context_window"]}), flush=True)
        started = time.monotonic()
        cursor = 0
        events = []
        announced_approvals = set()
        while time.monotonic() - started < args.timeout:
            batch = (await client.get(f"/api/turns/{turn_id}/events", params={"after": cursor})).json()
            for event in batch:
                cursor = event["sequence"]
                events.append(event)
                if event["type"] in {"tool.requested", "tool.completed", "tool.failed", "preview.ready", "turn.failed"}:
                    payload = event["payload"]
                    print(json.dumps({"event": event["type"], "name": payload.get("name"),
                                      "path": payload.get("arguments", {}).get("path"),
                                      "command": payload.get("arguments", {}).get("command"),
                                      "message": payload.get("message")}, ensure_ascii=True), flush=True)
            for approval in (await client.get(f"/api/sessions/{session['id']}/approvals")).json():
                if approval["id"] not in announced_approvals:
                    print("REVIEW_APPROVAL " + json.dumps(approval, ensure_ascii=True), flush=True)
                    announced_approvals.add(approval["id"])
            turn = (await client.get(f"/api/turns/{turn_id}")).json()
            if turn["status"] in {"completed", "failed", "cancelled", "interrupted"}:
                break
            await asyncio.sleep(2)
        else:
            await client.post(f"/api/turns/{turn_id}/cancel")
            turn = (await client.get(f"/api/turns/{turn_id}")).json()
        await verify_saved_turn(client, turn_id, report_dir, args.url)


if __name__ == "__main__":
    asyncio.run(main())
