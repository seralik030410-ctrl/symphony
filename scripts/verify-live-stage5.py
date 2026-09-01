"""Live Ollama acceptance. Creates only a labelled QA chat; never auto-approves tools."""
from pathlib import Path
import json
import time
import httpx

ROOT = Path(__file__).resolve().parents[1]


def main():
    evidence = {"prompts": [], "ok": False}
    with httpx.Client(base_url="http://127.0.0.1:8765", timeout=30) as client:
        response = client.post("/api/sessions", json={"title": "Stage 5 live QA · Documents", "provider": "ollama", "model": "qwen3.5:9b"})
        response.raise_for_status(); session = response.json(); evidence["session_id"] = session["id"]
        prompts = [
            ("pdf", "Создай короткий PDF-отчёт на русском с заголовком «Результаты пилота». Только тестовые данные: план 100, факт 120, превышение плана 20%. Добавь таблицу план/факт и один вывод. Дай готовый файл для скачивания."),
            ("xlsx", "Теперь создай Excel-книгу «Бюджет пилота»: столбцы «Статья» (текст) и «Сумма» (число), строки «Работа» 100, «Материалы» 20 и «Итого» с формулой SUM двух сумм. Дай готовый XLSX для скачивания."),
        ]
        for format, prompt in prompts:
            response = client.post(f"/api/sessions/{session['id']}/turns", json={"content": prompt}); response.raise_for_status()
            turn = response.json()["turn"]; print(json.dumps({"format": format, "turn_id": turn["id"]}), flush=True)
            deadline = time.monotonic() + 360; after = 0; events = []
            while time.monotonic() < deadline:
                chunk = client.get(f"/api/turns/{turn['id']}/events", params={"after": after}).json()
                events.extend(chunk)
                for event in chunk:
                    after = max(after, event["sequence"])
                    if event["type"] in {"tool.started", "tool.failed", "artifact.created", "turn.failed", "turn.completed"}:
                        print(json.dumps({"type": event["type"], "payload": event["payload"]}, ensure_ascii=True), flush=True)
                if any(event["type"] == "approval.requested" for event in chunk):
                    print("Approval is required; review in the Symphony UI. This helper does not approve.", flush=True)
                turn = client.get(f"/api/turns/{turn['id']}").json()
                if turn["status"] in {"completed", "failed", "cancelled", "interrupted"}: break
                time.sleep(2)
            else:
                client.post(f"/api/turns/{turn['id']}/cancel")
                turn = client.get(f"/api/turns/{turn['id']}").json()
            artifacts = [event["payload"] for event in events if event["type"] == "artifact.created" and event["payload"].get("format") == format]
            for artifact in artifacts:
                download = client.get(artifact["download_url"])
                artifact["download_status"] = download.status_code
                artifact["download_size"] = len(download.content)
            evidence["prompts"].append({"prompt": prompt, "turn": turn, "artifacts": artifacts, "events": events})
        evidence["ok"] = all(item["turn"]["status"] == "completed" and item["artifacts"] and all(a["download_status"] == 200 for a in item["artifacts"]) for item in evidence["prompts"])
    destination = ROOT / "data" / "acceptance" / f"stage5-live-{evidence['session_id']}.json"
    destination.parent.mkdir(exist_ok=True, parents=True)
    destination.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"ok": evidence["ok"], "evidence": str(destination)}), flush=True)
    return 0 if evidence["ok"] else 1


if __name__ == "__main__": raise SystemExit(main())
