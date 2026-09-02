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


async def test_empty_trash_permanently_removes_database_rows_and_session_files(client, app):
    sessions = [(await client.post('/api/sessions', json={})).json() for _ in range(2)]
    for index, session in enumerate(sessions):
        source = app.state.runtime.workspaces.resolve(session['id'], f'note-{index}.txt')
        source.write_text(f'private session {index}', encoding='utf-8')
        app.state.runtime.file_index.index_file(session['id'], source.name)
        assert (await client.delete(f"/api/sessions/{session['id']}")).status_code == 200

    response = await client.delete('/api/trash')
    assert response.status_code == 200
    assert response.json()['deleted'] == 2
    assert response.json()['storage_warnings'] == []
    assert (await client.get('/api/trash')).json() == []

    for session in sessions:
        assert not (app.state.runtime.settings.workspace_root / session['id']).exists()
        assert (await client.post(f"/api/sessions/{session['id']}/restore")).status_code == 404

    with app.state.runtime.database.read() as connection:
        assert connection.execute('SELECT COUNT(*) FROM file_chunks_fts').fetchone()[0] == 0
        assert connection.execute('SELECT COUNT(*) FROM sessions').fetchone()[0] == 0
