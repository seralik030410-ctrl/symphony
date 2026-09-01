"""An explicit, privacy-minimal report: no chats, filenames, environment or keys."""
import io
import json
import os
import platform
import shutil
import sqlite3
import zipfile
from importlib.metadata import PackageNotFoundError, version

from fastapi import APIRouter, Request, Response

from backend.storage.database import utc_now

router = APIRouter(prefix="/api/diagnostics")


async def report(runtime):
    packages = {}
    for name in ("fastapi", "httpx", "uvicorn", "pydantic", "pymupdf", "openpyxl"):
        try: packages[name] = version(name)
        except PackageNotFoundError: packages[name] = "missing"
    ready, _ = await runtime.sandbox.health()
    docker_hint = "Запустите Docker Desktop. Если runtime ещё не установлен, раскройте «Установка зависимостей» ниже и скачайте установочный набор. Для обычного чата Docker не нужен."
    checks = [
        {"name": "Docker runtime", "ready": ready, "hint": "Готов" if ready else docker_hint},
        {"name": "Ollama executable", "ready": bool(shutil.which("ollama")), "hint": "Для локального чата установите Ollama и скачайте модель; API-провайдер не требует Ollama"},
    ]
    with runtime.database.read() as connection:
        migrations = [row[0] for row in connection.execute("SELECT version FROM schema_migrations ORDER BY version")]
    desktop = os.getenv("SYMPHONY_DESKTOP") == "1"
    return {"schema_version": 1, "generated_at": utc_now(), "application": "Symphony 2.0", "release": "0.7.0-dev",
            "platform": platform.system(), "architecture": platform.machine(), "python": platform.python_version(),
            "installation_mode": "desktop-sidecar" if desktop else "local-web",
            "sqlite": sqlite3.sqlite_version, "packages": packages, "checks": checks, "migrations": migrations,
            "privacy": "No conversation, file paths, environment variables, source URLs, API keys or logs included.",
            "macos_acceptance": "pending: installer, Keychain, native drag/drop and signed update require a Mac"}


@router.get("")
async def diagnostics(request: Request):
    return await report(request.app.state.runtime)


@router.get("/bundle")
async def bundle(request: Request):
    payload = await report(request.app.state.runtime)
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("diagnostics.json", json.dumps(payload, ensure_ascii=False, indent=2))
        archive.writestr("README.txt", "Symphony diagnostics. This archive intentionally omits chats, files, keys, environment variables and raw logs. Review diagnostics.json before sharing.\n")
    return Response(output.getvalue(), media_type="application/zip", headers={"Content-Disposition": 'attachment; filename="symphony-diagnostics.zip"', "Cache-Control": "no-store"})
