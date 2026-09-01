import asyncio

import httpx
import pytest

from backend.main import create_app
from backend.models.base import ModelStreamEvent, ToolCall
from backend.models.gateway import ModelGateway
from conftest import FakeAdapter, wait_for_final


class Writer(FakeAdapter):
    async def stream_chat(self, request):
        self.requests.append(request)
        if len(self.requests) == 1:
            yield ModelStreamEvent(type="tool_call", tool_call=ToolCall("write", "fs.write", {"path": "proof.txt", "content": "approved"}))
        else:
            yield ModelStreamEvent(type="text_delta", delta="Done.")


@pytest.mark.parametrize("decision", ["approve", "deny", "cancel"])
async def test_read_only_write_waits_for_exact_one_time_decision(settings, decision):
    adapter = Writer("ollama")
    app = create_app(settings, ModelGateway({"ollama": adapter}))
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            session = (await client.post("/api/sessions", json={})).json()
            await client.patch(f"/api/sessions/{session['id']}", json={"policy_profile": "read_only"})
            created = (await client.post(f"/api/sessions/{session['id']}/turns", json={"content": "write file"})).json()
            turn_id = created["turn"]["id"]
            for _ in range(100):
                approvals = (await client.get(f"/api/sessions/{session['id']}/approvals")).json()
                if approvals:
                    break
                await asyncio.sleep(.01)
            assert approvals
            file = app.state.runtime.workspaces.resolve(session["id"], "proof.txt")
            assert not file.exists()
            # A fresh client models page refresh; the same pending decision survives.
            assert approvals == (await client.get(f"/api/sessions/{session['id']}/approvals")).json()
            approval_id = approvals[0]["id"]
            if decision == "cancel":
                await client.post(f"/api/turns/{turn_id}/cancel")
                assert (await client.post(f"/api/approvals/{approval_id}/decision", json={"approved": True})).status_code == 409
            else:
                assert (await client.post(f"/api/approvals/{approval_id}/decision", json={"approved": decision == "approve"})).status_code == 200
            await wait_for_final(client, turn_id)
            assert file.exists() is (decision == "approve")
            saved = (await client.get(f"/api/sessions/{session['id']}")).json()
            assert saved["policy_profile"] == "read_only"  # Approval never widens future permissions.


class FailingWriter(FakeAdapter):
    async def stream_chat(self, request):
        self.requests.append(request)
        yield ModelStreamEvent(type="tool_call", tool_call=ToolCall(str(len(self.requests)), "fs.read", {"path": f"missing-{len(self.requests)}.txt"}))


async def test_two_repair_attempts_then_stops(settings):
    adapter = FailingWriter("ollama")
    app = create_app(settings, ModelGateway({"ollama": adapter}))
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            session = (await client.post("/api/sessions", json={})).json()
            created = (await client.post(f"/api/sessions/{session['id']}/turns", json={"content": "read"})).json()
            final = await wait_for_final(client, created["turn"]["id"])
            assert final["status"] == "failed"
            assert len(adapter.requests) == 3
            events = (await client.get(f"/api/turns/{final['id']}/events")).json()
            assert events[-1]["payload"]["code"] == "repair_limit"
