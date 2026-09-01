"""Isolated document UI fixture. No user database, providers or model-generated code.

python scripts/document-ui-fixture.py
python scripts/document-ui-fixture.py --docker  # includes real DOCX/PPTX preview
"""
import argparse
import asyncio
import copy
import json
from pathlib import Path
import tempfile
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import uvicorn
from backend.config import Settings
from backend.main import create_app
from backend.models.base import ModelAdapter, ModelCapabilities, ModelStreamEvent
from backend.models.gateway import ModelGateway
from backend.artifacts.renderers import render_job
from backend.artifacts.schemas import EXAMPLES
from backend.tools.contracts import ToolContext


class FixtureAdapter(ModelAdapter):
    name = "ollama"; title = "UI fixture"; base_url = "memory://fixture"; default_model = "fixture"
    async def list_models(self): return [self.default_model]
    def get_capabilities(self, model): return ModelCapabilities()
    async def stream_chat(self, request): yield ModelStreamEvent(type="text_delta", delta="Это тестовый стенд интерфейса. Настоящая модель не вызывается.")
    async def cancel(self, request_id): pass
    async def health(self): return True, "fixture"


class LocalFixtureRenderer:
    async def render(self, job, on_output=None): render_job(job)


async def seed(app, docker):
    runtime = app.state.runtime
    if not docker: runtime.artifacts.runner = LocalFixtureRenderer()
    session = runtime.repository.create_session(title="Документы · Stage 5 QA", provider="ollama", model="fixture", system_prompt="", context_window=16384, max_output=2048)
    created = runtime.repository.create_turn(session["id"], "Создай отчёт и таблицу на тестовых данных.")
    turn = created["turn"]
    await runtime.turn_service.emit(turn["id"], "turn.started", {})
    context = ToolContext(session_id=session["id"], turn_id=turn["id"])
    for format in (["pdf", "xlsx", "docx", "pptx"] if docker else ["pdf", "xlsx"]):
        spec = copy.deepcopy(EXAMPLES[format])
        if format == "pdf":
            spec = {"title": "Проект в цифрах", "subtitle": "Демонстрационные данные · Август 2026", "preset": "clean_report", "sections": [
                {"heading": "Коротко о результатах", "paragraphs": ["Команда завершила план работ. Этот отчёт создан доверенным рендерером из структурированного JSON; код для создания документа модель не писала."], "callout": "Выручка: 120 000. План: 100 000. Выполнение плана: 120%.", "chart": {"title": "План и факт", "labels": ["План", "Факт"], "values": [100000, 120000]}},
                {"heading": "Подробные данные", "table": {"columns": ["Период", "План", "Факт"], "rows": [[f"Неделя {i}", 10000, 12000] for i in range(1, 25)]}},
            ], "citations": ["Тестовый набор данных Symphony. Не финансовая отчётность."]}
        path = runtime.workspaces.resolve(session["id"], f"{format}.json")
        path.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
        result = await runtime.artifacts.render(context, format, f"{format}.json", None)
        await runtime.turn_service.emit(turn["id"], "artifact.created", result)
        if format == "pdf":
            spec["title"] = "Проект в цифрах — обновление"
            path.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
            result = await runtime.artifacts.render(context, format, f"{format}.json", result["id"])
            await runtime.turn_service.emit(turn["id"], "artifact.created", result)
    runtime.repository.append_assistant_delta(turn["assistant_message_id"], "Готовы тестовые документы. Откройте карточку: версии, страницы и таблицы доступны в боковой панели.")
    runtime.repository.set_message_status(turn["assistant_message_id"], "complete")
    runtime.repository.set_turn_status(turn["id"], "completed", finished=True)
    await runtime.turn_service.emit(turn["id"], "turn.completed", {})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("--docker", action="store_true"); parser.add_argument("--port", type=int, default=8767)
    args = parser.parse_args()
    fixture_root = Path(tempfile.mkdtemp(prefix="symphony-document-ui-"))
    settings = Settings(database_path=fixture_root / "fixture.db", workspace_root=fixture_root / "workspaces", skills_root=fixture_root / "skills", seed_bundled_skills=False)
    application = create_app(settings, ModelGateway({"ollama": FixtureAdapter()}))
    asyncio.run(seed(application, args.docker))
    print(f"Fixture data: {fixture_root}", flush=True)
    uvicorn.run(application, host="127.0.0.1", port=args.port)
