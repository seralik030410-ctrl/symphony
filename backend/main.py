from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
import os
import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.responses import JSONResponse
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
from backend.api.providers import router as providers_router
from backend.api.media import router as media_router
from backend.api.voice import router as voice_router
from backend.providers import ProviderRegistry, SecretStore
from backend.providers.secrets import SENSITIVE_KEY
from backend.media.assets import MediaAssetStore
from backend.media.jobs import MediaJobStore
from backend.media.service import MediaService
from backend.voice import VoiceGateway, VoiceService, VoiceStore
from backend.agent.task_store import AgentTaskStore
from backend.agent.executor import AgentExecutor
from backend.agent.orchestrator import AgentOrchestrator
from backend.tools.delegation import AgentControlTool, DelegateTool, ExecuteBatchTool, ProposeLearningTool
from backend.tools.discovery import ToolSearchTool
from backend.api.agents import router as agents_router
from backend.agent.learning import LearningProposalStore
from backend.agent.heartbeat import AgentHeartbeatService
from backend.agent.history_search import HistorySearch
from backend.runtime import ResourceCoordinator
from backend.api.resources import router as resources_router
from backend.api.comfyui import router as comfyui_router
from backend.api.search import router as search_router
from backend.api.office import router as office_router
from backend.tools.office import OfficeInspectTool, OfficeCreateTool, OfficePatchTool, OfficeConvertTool


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
    providers: ProviderRegistry
    secrets: SecretStore
    media: MediaService
    voice: VoiceService
    agent_tasks: AgentTaskStore
    agents: AgentOrchestrator
    agent_learning: LearningProposalStore
    agent_heartbeats: AgentHeartbeatService
    history_search: HistorySearch
    resources: ResourceCoordinator


def create_app(settings: Settings | None = None, gateway: ModelGateway | None = None) -> FastAPI:
    active_settings = settings or Settings.from_env()
    database = Database(active_settings.database_path)
    database.initialize()
    repository = Repository(database)
    active_gateway = gateway or ModelGateway.from_settings(active_settings)
    active_gateway.database = database
    secrets = SecretStore(active_settings.provider_secrets)
    active_settings.provider_secrets.clear()
    providers = ProviderRegistry(database, active_settings, secrets)
    resources = ResourceCoordinator(database, secrets)
    media_root = active_settings.media_root
    if media_root == PROJECT_ROOT / "data" / "media" and active_settings.database_path.parent != PROJECT_ROOT / "data":
        media_root = active_settings.database_path.parent / "media"
    media = MediaService(
        MediaAssetStore(database, media_root),
        MediaJobStore(database, repository),
        secrets,
        resources=resources,
    )
    active_gateway.registry = providers
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
                 WebSearchTool(research, web_client), WebOpenTool(research, web_client),
                 OfficeInspectTool(workspaces), OfficeCreateTool(workspaces), OfficePatchTool(workspaces), OfficeConvertTool(workspaces)]:
        tools.tools[tool.name] = tool
    agent_tasks = AgentTaskStore(database, lazy_tools_default=active_settings.agent_lazy_tools_enabled)
    agent_learning = LearningProposalStore(database)
    agent_heartbeats = AgentHeartbeatService(database, agent_tasks)
    history_search = HistorySearch(database)
    agent_executor = AgentExecutor(agent_tasks, repository, active_gateway, tools, policy, resources)
    agents = AgentOrchestrator(agent_tasks, repository, agent_executor, tools, agent_heartbeats)
    tools.tools["agent.delegate"] = DelegateTool(agents)
    tools.tools["agent.control"] = AgentControlTool(agents)
    tools.tools["agent.execute_batch"] = ExecuteBatchTool(tools, repository, policy)
    tools.tools["agent.propose_learning"] = ProposeLearningTool(agent_learning)
    tools.tools["tool.search"] = ToolSearchTool(tools)
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
    turn_service.agents = agents
    turn_service.resources = resources
    voice = VoiceService(VoiceStore(database, repository), VoiceGateway(providers), repository, turn_service, secrets, media.assets,
                         resources=resources)
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
        providers=providers,
        secrets=secrets,
        media=media,
        voice=voice,
        agent_tasks=agent_tasks,
        agents=agents,
        agent_learning=agent_learning,
        agent_heartbeats=agent_heartbeats,
        history_search=history_search,
        resources=resources,
    )

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        repository.mark_inflight_interrupted()
        agent_tasks.recover()
        resources.initialize()
        agent_heartbeats.reconcile_after_restart()
        agents.start_monitor()
        agent_heartbeats.start()
        application.state.runtime = runtime
        # Best effort at startup, mandatory/retried before any later execution.
        from backend.tools.contracts import ToolError
        try:
            await sandbox.recover_orphans()
        except (ToolError, TimeoutError):
            pass
        await media.start()
        voice.store.recover()
        yield
        await voice.shutdown()
        await agent_heartbeats.shutdown()
        await agents.shutdown()
        await media.shutdown()
        await turn_service.shutdown()

    application = FastAPI(
        title="FinCtrl",
        version="0.20.0-dev",
        description="FinCtrl multimodal runtime with durable subagent orchestration",
        lifespan=lifespan,
    )
    application.state.runtime = runtime

    @application.exception_handler(RequestValidationError)
    async def validation_error(_request: Request, exc: RequestValidationError):
        errors = []
        for source in exc.errors():
            error = dict(source)
            location = tuple(str(part) for part in error.get("loc", ()))
            if any(SENSITIVE_KEY.search(part) for part in location):
                error["input"] = "***"
            errors.append(secrets.redact(error))
        return JSONResponse(status_code=422, content={"detail": jsonable_encoder(errors)})
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
    application.include_router(providers_router)
    application.include_router(media_router)
    application.include_router(voice_router)
    application.include_router(agents_router)
    application.include_router(resources_router)
    application.include_router(comfyui_router)
    application.include_router(search_router)
    application.include_router(office_router)

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
