from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from typing import Any

from backend.media.assets import MediaAssetStore
from backend.media.jobs import MediaJobStore
from backend.media.providers.comfyui import ComfyUIConnection, ComfyUIConnector, ComfyUIProcessManager
from backend.media.workflows import WorkflowCatalog
from backend.providers.secrets import SecretStore
from backend.storage.database import utc_now
from backend.storage.repository import ConflictError
from backend.tools.contracts import ToolError
from backend.runtime.contracts import ResourceClaim, ResourceClass, ResourceRequestStatus
from backend.runtime.resources import ResourceCoordinator


Progress = Callable[[float, str], Awaitable[None]]
Handler = Callable[[dict[str, Any], dict[str, Any], Progress], Awaitable[str | list[str]]]


class MediaService:
    def __init__(self, assets: MediaAssetStore, jobs: MediaJobStore, secrets: SecretStore, *,
                 comfyui: ComfyUIConnector | None = None, comfyui_process: ComfyUIProcessManager | None = None,
                 workflow_catalog: WorkflowCatalog | None = None,
                 resources: ResourceCoordinator | None = None) -> None:
        self.assets, self.jobs, self.secrets = assets, jobs, secrets
        self.comfyui = comfyui
        self.comfyui_process = comfyui_process
        self.workflows = workflow_catalog or WorkflowCatalog()
        self.resources = resources
        self.handlers: dict[str, Handler] = {
            "media.preview": self._preview,
            "media.comfyui.image": self._comfyui,
            "media.comfyui.video": self._comfyui,
        }
        self._wake = asyncio.Event()
        self._runner: asyncio.Task[None] | None = None

    async def start(self) -> None:
        self.jobs.recover()
        if not self._runner or self._runner.done():
            self._runner = asyncio.create_task(self._run(), name="media-job-worker")
            self._wake.set()

    async def shutdown(self) -> None:
        if self._runner:
            self._runner.cancel()
            await asyncio.gather(self._runner, return_exceptions=True)
            self._runner = None
        if self.comfyui:
            await self.comfyui.close()
        if self.comfyui_process:
            await self.comfyui_process.stop()

    def configure_comfyui(self, base_url: str, *, allow_private_network: bool = False,
                          timeout_seconds: float = 120.0) -> dict[str, Any]:
        """Replace the single approved ComfyUI origin for this runtime."""
        next_connector = ComfyUIConnector(
            ComfyUIConnection(base_url, allow_private_network=allow_private_network, timeout_seconds=timeout_seconds)
        )
        previous = self.comfyui
        self.comfyui = next_connector
        if previous:
            # Deliberately do not await close from a synchronous settings route;
            # the old client has no in-flight request when configuration changes.
            asyncio.create_task(previous.close())
        return {"origin": next_connector.origin, "allow_private_network": allow_private_network}

    async def comfyui_health(self) -> dict[str, Any]:
        if not self.comfyui:
            raise ToolError("comfyui_not_configured", "ComfyUI is not configured")
        return await self.comfyui.health()

    def quick_generate(self, session_id: str, kind: str, template_id: str, values: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        if kind not in {"image", "video"}:
            raise ToolError("invalid_media_job", "Quick Generate supports image or video")
        if not self.comfyui:
            raise ToolError("comfyui_not_configured", "Connect ComfyUI before generating media")
        template = self.workflows.get(template_id)
        if template.kind != kind:
            raise ToolError("invalid_workflow_template", "Workflow template does not match the requested media kind")
        workflow, provenance = self.workflows.bind(template_id, values)
        return self.enqueue(session_id, f"media.comfyui.{kind}", {
            "workflow": workflow,
            "workflow_provenance": provenance,
        }, **kwargs)

    def enqueue_workflow(self, session_id: str, kind: str, workflow: dict[str, Any], *, title: str = "Workflow Studio", **kwargs: Any) -> dict[str, Any]:
        """Queue an explicitly submitted Studio graph without exposing node mutation APIs."""
        if kind not in {"image", "video"} or not isinstance(workflow, dict) or not workflow:
            raise ToolError("invalid_workflow", "Workflow Studio requires a non-empty image or video workflow")
        if not self.comfyui:
            raise ToolError("comfyui_not_configured", "Connect ComfyUI before running a workflow")
        return self.enqueue(session_id, f"media.comfyui.{kind}", {
            "workflow": workflow,
            "workflow_provenance": {"source": "studio", "title": title[:160]},
        }, **kwargs)

    def enqueue(self, session_id: str, kind: str, input_value: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        if kind not in self.handlers:
            raise ToolError("unsupported_media_job", f"Unsupported media job kind: {kind}")
        if kind == "media.preview":
            self.assets.get(session_id, str(input_value.get("asset_id", "")))
        job = self.jobs.create(session_id, kind, input_value, **kwargs)
        self._wake.set()
        return job

    def cancel(self, session_id: str, job_id: str) -> dict[str, Any]:
        result = self.jobs.cancel(session_id, job_id)
        self._wake.set()
        return result

    def retry(self, session_id: str, job_id: str) -> dict[str, Any]:
        result = self.jobs.retry(session_id, job_id)
        self._wake.set()
        return result

    async def _run(self) -> None:
        while True:
            job = self.jobs.claim_next()
            if not job:
                self._wake.clear()
                try:
                    await asyncio.wait_for(self._wake.wait(), timeout=2.0)
                except TimeoutError:
                    pass
                continue
            await self._execute(job)

    async def _execute(self, job: dict[str, Any]) -> None:
        session_id, job_id = job["session_id"], job["id"]
        resource_id: str | None = None
        try:
            if self.jobs.get(session_id, job_id)["cancel_requested"]:
                self.jobs.transition(session_id, job_id, "cancelled")
                return
            if self.resources and job["kind"].startswith("media.comfyui."):
                resource_class = ResourceClass.VIDEO if job["kind"].endswith("video") else ResourceClass.IMAGE
                request = self.resources.submit(
                    owner_type="media_job", owner_id=job_id, session_id=session_id,
                    resource_class=resource_class,
                    claims=[ResourceClaim("gpu:local", 100)],
                    metadata={"restart_policy": "requeue", "job_kind": job["kind"]},
                )
                resource_id = request.id
                while True:
                    admitted = await self.resources.wait_for_admission(resource_id, timeout_seconds=1.0)
                    if self.jobs.get(session_id, job_id)["cancel_requested"]:
                        self.resources.cancel(resource_id)
                        self.jobs.transition(session_id, job_id, "cancelled")
                        return
                    if admitted.status in {ResourceRequestStatus.ADMITTED, ResourceRequestStatus.CANCELLED,
                                          ResourceRequestStatus.FAILED}:
                        break
                if admitted.status is ResourceRequestStatus.CANCELLED:
                    self.jobs.transition(session_id, job_id, "cancelled")
                    return
                if admitted.status is not ResourceRequestStatus.ADMITTED:
                    raise ToolError("resource_unavailable", "Media resource request was not admitted")
                self.resources.start(resource_id)
            self.jobs.transition(session_id, job_id, "running", progress=0.05)

            async def progress(value: float, message: str) -> None:
                current = self.jobs.get(session_id, job_id)
                if current["cancel_requested"]:
                    if self.resources and resource_id:
                        self.resources.cancel(resource_id)
                    raise asyncio.CancelledError
                if self.resources and resource_id:
                    self.resources.heartbeat(resource_id)
                self.jobs.progress(session_id, job_id, value, message)

            result = await self.handlers[job["kind"]](job, job["input"], progress)
            asset_ids = [result] if isinstance(result, str) else result
            if not asset_ids:
                raise ToolError("media_output_missing", "Media job completed without an output")
            current = self.jobs.get(session_id, job_id)
            if current["cancel_requested"]:
                self.jobs.transition(session_id, job_id, "cancelled")
                return
            for asset_id in asset_ids:
                self.assets.link(session_id, asset_id, relation="job.output", turn_id=job.get("turn_id"), job_id=job_id)
            self.jobs.transition(session_id, job_id, "completed", result_asset_id=asset_ids[0])
            if self.resources and resource_id:
                self.resources.complete(resource_id)
        except asyncio.CancelledError:
            if self._runner and self._runner.cancelling():
                raise
            try: self.jobs.transition(session_id, job_id, "cancelled")
            except ConflictError: pass
            if self.resources and resource_id:
                request = self.resources.cancel(resource_id)
                if request.status is ResourceRequestStatus.RUNNING:
                    self.resources.acknowledge_cancel(resource_id)
        except Exception as exc:
            message = self.secrets.redact_text(str(exc))[:1000] or type(exc).__name__
            code = exc.code if isinstance(exc, ToolError) else "media_job_failed"
            try: self.jobs.transition(session_id, job_id, "failed", error_code=code, error_message=message)
            except ConflictError: pass
            if self.resources and resource_id:
                try: self.resources.fail(resource_id, error_code=code, error_message=message)
                except Exception: pass

    async def _preview(self, job: dict[str, Any], input_value: dict[str, Any], progress: Progress) -> str:
        asset_id = str(input_value.get("asset_id", ""))
        if not asset_id:
            raise ToolError("invalid_job_input", "media.preview requires asset_id")
        self.assets.get(job["session_id"], asset_id)
        await progress(0.2, "Preparing media")
        await asyncio.to_thread(self.assets.regenerate_preview, job["session_id"], asset_id)
        await progress(0.9, "Preview ready")
        return asset_id

    async def _comfyui(self, job: dict[str, Any], input_value: dict[str, Any], progress: Progress) -> list[str]:
        connector = self.comfyui
        if not connector:
            raise ToolError("comfyui_not_configured", "ComfyUI is not configured")
        workflow = input_value.get("workflow")
        if not isinstance(workflow, dict):
            raise ToolError("invalid_workflow", "ComfyUI media job has no workflow snapshot")
        await progress(0.12, "Submitting workflow to ComfyUI")
        prompt_id = await connector.queue_prompt(workflow, extra_data={"fincctrl_job_id": job["id"]})
        # Keep the remote prompt id and immutable workflow provenance together
        # with the job, so retries retain the exact same snapshot.
        with self.jobs.database.transaction() as connection:
            row = connection.execute("SELECT input_json FROM media_jobs WHERE id=?", (job["id"],)).fetchone()
            if not row:
                raise ToolError("media_job_missing", "Media job disappeared")
            saved = json.loads(row["input_json"])
            saved["comfyui_prompt_id"] = prompt_id
            connection.execute("UPDATE media_jobs SET input_json=?,updated_at=? WHERE id=?", (json.dumps(saved, ensure_ascii=False, separators=(",", ":")), utc_now(), job["id"]))
        await progress(0.2, "Waiting for ComfyUI")
        loops = max(1, int(connector.connection.timeout_seconds))
        history: dict[str, Any] | None = None
        for attempt in range(loops):
            current = self.jobs.get(job["session_id"], job["id"])
            if current["cancel_requested"]:
                await connector.cancel(prompt_id)
                raise asyncio.CancelledError
            history = await connector.history(prompt_id)
            if history:
                status = history.get("status")
                status_text = status.get("status_str") if isinstance(status, dict) else ""
                if status_text == "error":
                    messages = status.get("messages", []) if isinstance(status, dict) else []
                    raise ToolError("comfyui_execution_failed", str(messages or "ComfyUI workflow failed")[:1000])
                outputs = connector.outputs(history)
                if outputs:
                    break
            queue_state = await connector.queue_state(prompt_id)
            await progress(min(0.92, 0.2 + attempt / max(2, loops) * 0.7), "ComfyUI is generating" if queue_state == "running" else "Waiting in ComfyUI queue")
            await asyncio.sleep(1)
        else:
            raise ToolError("comfyui_timeout", "ComfyUI did not finish before the configured timeout")
        outputs = connector.outputs(history)
        if not outputs:
            raise ToolError("comfyui_output_missing", "ComfyUI finished without a usable output")
        asset_ids: list[str] = []
        provenance = input_value.get("workflow_provenance", {})
        for index, output in enumerate(outputs):
            raw, filename, mime_type = await connector.fetch_output(output)
            asset, _created = self.assets.put(
                job["session_id"], raw, filename=filename, mime_type=mime_type, source="comfyui",
                provenance={"provider": "comfyui", "origin": connector.origin, "prompt_id": prompt_id,
                            "output": output, "workflow": provenance},
                provider_profile_id=job.get("provider_profile_id"),
            )
            asset_ids.append(asset["id"])
            await progress(min(0.98, 0.94 + (index + 1) / max(1, len(outputs)) * 0.04), "Saving ComfyUI output")
        return asset_ids
