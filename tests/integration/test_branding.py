from __future__ import annotations


async def test_public_api_metadata_uses_finctrl_brand(client):
    openapi = (await client.get("/openapi.json")).json()
    diagnostics = (await client.get("/api/diagnostics")).json()

    assert openapi["info"]["title"] == "FinCtrl"
    assert diagnostics["application"] == "FinCtrl"


async def test_openapi_operation_ids_are_unique(client):
    openapi = (await client.get("/openapi.json")).json()
    operation_ids = [
        operation["operationId"]
        for path in openapi["paths"].values()
        for operation in path.values()
        if isinstance(operation, dict) and "operationId" in operation
    ]
    assert len(operation_ids) == len(set(operation_ids))
