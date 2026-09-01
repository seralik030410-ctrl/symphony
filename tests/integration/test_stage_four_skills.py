from collections.abc import AsyncIterator

import httpx

from backend.main import create_app
from backend.models.base import ChatRequest, ModelCapabilities, ModelStreamEvent, ToolCall
from backend.models.gateway import ModelGateway
from conftest import FakeAdapter, wait_for_final


class SkillAdapter(FakeAdapter):
    def get_capabilities(self, model: str) -> ModelCapabilities:
        return ModelCapabilities(native_tools=True)

    async def stream_chat(self, request: ChatRequest) -> AsyncIterator[ModelStreamEvent]:
        self.requests.append(request)
        if len(self.requests) == 1:
            system = request.messages[0]["content"]
            skill_id = system.split('<activated_skill id="', 1)[1].split('"', 1)[0]
            yield ModelStreamEvent(type="tool_call", tool_call=ToolCall("resource", "skill.read_resource",
                {"skill_id": skill_id, "path": "references/check.md"}))
        else:
            yield ModelStreamEvent(type="text_delta", delta="Навык и его checklist прочитаны.")


async def test_skill_api_and_trace_prove_selection_full_read_and_resource_tool(settings, tmp_path):
    source = tmp_path / "source-skill"
    source.mkdir(); (source / "references").mkdir()
    (source / "SKILL.md").write_text("---\nname: UI audit\ndescription: Review accessibility and interface quality\n---\n# UI audit\nRead `references/check.md`.\n", encoding="utf-8")
    (source / "references" / "check.md").write_text("check keyboard focus", encoding="utf-8")
    adapter = SkillAdapter("ollama")
    app = create_app(settings, ModelGateway({"ollama": adapter}))
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            installed = (await client.post("/api/skills/install", json={"source_type": "folder", "source": str(source), "mode": "explicit"})).json()
            assert (await client.post("/api/skills/test", json={"prompt": "$ui-audit inspect this"})).json()["selected"][0]["id"] == installed["id"]
            session = (await client.post("/api/sessions", json={})).json()
            created = (await client.post(f"/api/sessions/{session['id']}/turns", json={"content": "$ui-audit inspect this"})).json()
            final = await wait_for_final(client, created["turn"]["id"])
            events = (await client.get(f"/api/turns/{final['id']}/events")).json()
            detail = (await client.get(f"/api/skills/{installed['id']}")).json()
            exported = await client.get(f"/api/skills/{installed['id']}/export")
    types = [event["type"] for event in events]
    assert final["status"] == "completed"
    assert types.index("skill.selected") < types.index("skill.read") < types.index("tool.requested") < types.index("skill.resource_read")
    assert adapter.requests[0].messages[0]["content"].count("check keyboard focus") == 0  # reference stays disclosed later
    assert "check keyboard focus" in adapter.requests[1].messages[-1]["content"]
    assert detail["resources"] and exported.headers["content-type"] == "application/zip"


async def test_skill_run_script_requires_approval_even_in_build_profile(settings, tmp_path):
    source = tmp_path / "script-skill"; source.mkdir(); (source / "scripts").mkdir()
    (source / "SKILL.md").write_text("---\nname: Script check\ndescription: Run a project verification script\n---\n# Script check\n", encoding="utf-8")
    (source / "scripts" / "check.py").write_text("print('ok')", encoding="utf-8")

    class ScriptAdapter(SkillAdapter):
        async def stream_chat(self, request):
            self.requests.append(request)
            skill_id = request.messages[0]["content"].split('<activated_skill id="', 1)[1].split('"', 1)[0]
            yield ModelStreamEvent(type="tool_call", tool_call=ToolCall("script", "skill.run_script",
                {"skill_id": skill_id, "path": "scripts/check.py"}))

    adapter = ScriptAdapter("ollama")
    app = create_app(settings, ModelGateway({"ollama": adapter}))
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            installed = app.state.runtime.skills.install_folder(str(source), mode="explicit")
            session = (await client.post("/api/sessions", json={})).json()
            turn = (await client.post(f"/api/sessions/{session['id']}/turns", json={"content": "$script-check verify"})).json()["turn"]
            for _ in range(100):
                approvals = (await client.get(f"/api/sessions/{session['id']}/approvals")).json()
                if approvals: break
                import asyncio; await asyncio.sleep(.01)
            assert approvals[0]["request"]["name"] == "skill.run_script"
            await client.post(f"/api/turns/{turn['id']}/cancel")
