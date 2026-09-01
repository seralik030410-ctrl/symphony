from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
import os
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.agent.context import ContextBuilder
from backend.agent.turn_service import TurnService
from backend.api.routes import router
from backend.config import PROJECT_ROOT, Settings
from backend.models.gateway import ModelGateway
from backend.sandbox.policy import PolicyEngine
from backend.sandbox.runtime import DockerSandboxRuntime
from backend.storage.database import Database
from backend.storage.repository import Repository
from backend.tools.registry import ToolRegistry
from backend.tools.workspace import WorkspaceManager
from backend.skills.store import SkillStore
from backend.artifacts.store import ArtifactStore
from backend.artifacts.runner import DocumentRunner
from backend.tools.artifacts import DocumentSchemaTool, RenderDocumentTool, InspectArtifactTool, ReadTableTool
from backend.api.artifacts import router as artifacts_router
from backend.api.context import router as context_router
from backend.agent.retrieval import FileIndex
from backend.agent.memory import MemoryStore
from backend.agent.extraction import IsolatedExtractor
from backend.tools.context import IndexFileTool, SearchContextTool, OcrImageTool
from backend.research.network import SafeWebClient
from backend.research.store import ResearchStore
from backend.tools.web import WebSearchTool, WebOpenTool
from backend.api.research import router as research_router
from backend.api.diagnostics import router as diagnostics_router
from backend.api.setup import router as setup_router


@dataclass(slots=True)
class Runtime:
    settings: Settings
    database: Database
    repository: Repository
    gateway: ModelGateway
    turn_service: TurnService
    tools: ToolRegistry
    workspaces: WorkspaceManager
    sandbox: DockerSandboxRuntime
    policy: PolicyEngine
    skills: SkillStore
    artifacts: ArtifactStore
    file_index: FileIndex
    memory: MemoryStore
    research: ResearchStore


def create_app(settings: Settings | None = None, gateway: ModelGateway | None = None) -> FastAPI:
    active_settings = settings or Settings.from_env()
    database = Database(active_settings.database_path)
    database.initialize()
    repository = Repository(database)
    active_gateway = gateway or ModelGateway.from_settings(active_settings)
    active_gateway.database = database
    workspaces = WorkspaceManager(active_settings.workspace_root)
    sandbox = DockerSandboxRuntime(
        workspaces,
        image=active_settings.sandbox_image,
        memory=active_settings.sandbox_memory,
        cpus=active_settings.sandbox_cpus,
        pids_limit=active_settings.sandbox_pids_limit,
        output_limit=active_settings.sandbox_output_limit,
    )
    policy = PolicyEngine()
    skills = SkillStore(database, active_settings.skills_root, active_settings.bundled_skills_root)
    if active_settings.seed_bundled_skills:
        skills.ensure_bundled()
    tools = ToolRegistry.stage_four(workspaces, sandbox, skills)
    artifacts = ArtifactStore(database, workspaces, DocumentRunner(sandbox))
    file_index = FileIndex(database, workspaces, IsolatedExtractor(sandbox))
    memory = MemoryStore(database)
    research = ResearchStore(database)
    web_client = SafeWebClient()
    for tool in [DocumentSchemaTool(), RenderDocumentTool(artifacts), InspectArtifactTool(artifacts), ReadTableTool(workspaces),
                 IndexFileTool(file_index), SearchContextTool(file_index), OcrImageTool(file_index, sandbox),
                 WebSearchTool(research, web_client), WebOpenTool(research, web_client)]:
        tools.tools[tool.name] = tool
    turn_service = TurnService(
        repository,
        active_gateway,
        ContextBuilder(repository),
        tools,
        policy,
        skills,
        file_index=file_index,
        memory=memory,
        max_tool_calls=active_settings.max_tool_calls,
    )
    runtime = Runtime(
        settings=active_settings,
        database=database,
        repository=repository,
        gateway=active_gateway,
        turn_service=turn_service,
        tools=tools,
        workspaces=workspaces,
        sandbox=sandbox,
        policy=policy,
        skills=skills,
        artifacts=artifacts,
        file_index=file_index,
        memory=memory,
        research=research,
    )

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        repository.mark_inflight_interrupted()
        application.state.runtime = runtime
        # Best effort at startup, mandatory/retried before any later execution.
        from backend.tools.contracts import ToolError
        try:
            await sandbox.recover_orphans()
        except (ToolError, TimeoutError):
            pass
        yield
        await turn_service.shutdown()

    application = FastAPI(
        title="Symphony 2.0",
        version="0.7.0-dev",
        description="Stage 7 research preview: direct chat, bounded host networking and local-first desktop shell",
        lifespan=lifespan,
    )
    application.state.runtime = runtime
    application.add_middleware(
        CORSMiddleware,
        allow_origins=active_settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.include_router(router)
    application.include_router(artifacts_router)
    application.include_router(context_router)
    application.include_router(research_router)
    application.include_router(diagnostics_router)
    application.include_router(setup_router)

    frontend_dist = PROJECT_ROOT / "frontend" / "dist"
    if frontend_dist.exists():
        assets = frontend_dist / "assets"
        if assets.exists():
            application.mount("/assets", StaticFiles(directory=assets), name="assets")

        @application.get("/{path:path}", include_in_schema=False)
        async def frontend(path: str):
            if path == "api" or path.startswith("api/"):
                raise HTTPException(status_code=404, detail="API route not found")
            candidate = (frontend_dist / path).resolve()
            if candidate.is_file() and frontend_dist.resolve() in candidate.parents:
                return FileResponse(candidate)
            return FileResponse(frontend_dist / "index.html")

    return application


# The frozen desktop entrypoint receives secrets through a private pipe and
# creates its app explicitly. Do not initialize a second store on import.
app = None if os.getenv("SYMPHONY_DESKTOP") == "1" else create_app()


if __name__ == "__main__":
    config = Settings.from_env()
    uvicorn.run("backend.main:app", host=config.host, port=config.port, reload=False)
