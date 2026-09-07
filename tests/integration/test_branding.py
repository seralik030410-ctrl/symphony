from __future__ import annotations


async def test_public_api_metadata_uses_finctrl_brand(client):
    openapi = (await client.get("/openapi.json")).json()
    diagnostics = (await client.get("/api/diagnostics")).json()

    assert openapi["info"]["title"] == "FinCtrl"
    assert diagnostics["application"] == "FinCtrl"
