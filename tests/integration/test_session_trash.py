from conftest import wait_for_final


async def test_delete_and_restore_preserve_history_and_project(client, app):
    session = (await client.post('/api/sessions', json={})).json()
    created = (await client.post(f"/api/sessions/{session['id']}/turns", json={'content': 'hello'})).json()
    await wait_for_final(client, created['turn']['id'])
    path = app.state.runtime.workspaces.resolve(session['id'], 'keep.txt')
    path.write_text('keep')
    before = (await client.get(f"/api/sessions/{session['id']}")).json()
    response = await client.delete(f"/api/sessions/{session['id']}")
    assert response.json()['recoverable'] is True
    assert session['id'] not in [s['id'] for s in (await client.get('/api/sessions')).json()]
    assert (await client.get(f"/api/sessions/{session['id']}")).status_code == 404
    assert (await client.post(f"/api/sessions/{session['id']}/turns", json={'content': 'no'})).status_code == 404
    assert (await client.get('/api/trash')).json()[0]['id'] == session['id']
    restored = (await client.post(f"/api/sessions/{session['id']}/restore")).json()
    assert restored['messages'] == before['messages']
    assert path.read_text() == 'keep'
    assert (await client.get('/api/trash')).json() == []


async def test_delete_active_chat_cancels_turn_first(client, adapters):
    session = (await client.post('/api/sessions', json={})).json()
    adapter = adapters['ollama']
    adapter.pause_after_first = True
    adapter.release.clear()
    created = (await client.post(f"/api/sessions/{session['id']}/turns", json={'content': 'hello'})).json()
    await adapter.first_chunk_sent.wait()
    assert (await client.delete(f"/api/sessions/{session['id']}")).status_code == 200
    turn = (await client.get(f"/api/turns/{created['turn']['id']}")).json()
    assert turn['status'] == 'cancelled'
    assert (await client.post(f"/api/sessions/{session['id']}/restore")).status_code == 200
