async def test_code_and_snapshot_diff_are_read_only_and_scoped(client, app):
    first = (await client.post('/api/sessions', json={})).json()['id']
    second = (await client.post('/api/sessions', json={})).json()['id']
    runtime = app.state.runtime
    file = runtime.workspaces.resolve(first, 'index.html')
    file.write_bytes(b'before\n')
    snapshot = runtime.tools.snapshots.create(first, 'turn1', 'test')
    file.write_bytes(b'after\n')
    runtime.workspaces.resolve(first, 'new.js').write_text('const x = 1;', encoding='utf-8')
    response = await client.get(f'/api/sessions/{first}/files', params={'path': 'index.html'})
    assert response.json()['content'] == 'after\n'
    diff = (await client.get(f'/api/sessions/{first}/changes')).json()
    assert diff['snapshot']['id'] == snapshot['id']
    assert [(f['path'], f['status']) for f in diff['files']] == [('index.html', 'modified'), ('new.js', 'added')]
    assert '-before\n+after' in diff['files'][0]['diff']
    assert file.read_text() == 'after\n'
    assert (await client.get(f'/api/sessions/{second}/files', params={'path': 'index.html'})).status_code == 404
    assert (await client.get(f'/api/sessions/{second}/changes', params={'snapshot_id': snapshot['id']})).status_code == 404
    for path in ['../index.html', 'C:\\Windows\\win.ini', '/etc/passwd']:
        assert (await client.get(f'/api/sessions/{first}/files', params={'path': path})).status_code == 400


async def test_inspection_bounds_binary_deleted_and_default_turn_snapshot(client, app):
    sid = (await client.post('/api/sessions', json={})).json()['id']
    runtime = app.state.runtime
    file = runtime.workspaces.resolve(sid, 'gone.txt')
    file.write_text('old')
    first = runtime.tools.snapshots.create(sid, 'turn1', 'first edit')
    runtime.workspaces.resolve(sid, 'binary.bin').write_bytes(b'\x00\xff')
    runtime.tools.snapshots.create(sid, 'turn1', 'second edit')
    file.unlink()
    runtime.workspaces.resolve(sid, 'big.txt').write_text('x' * 300_000)
    code = (await client.get(f'/api/sessions/{sid}/files', params={'path': 'big.txt'})).json()
    assert code['truncated'] and len(code['content']) == 256_000
    assert (await client.get(f'/api/sessions/{sid}/files', params={'path': 'binary.bin'})).json()['binary']
    changes = (await client.get(f'/api/sessions/{sid}/changes')).json()
    assert changes['snapshot']['id'] == first['id']
    assert next(f for f in changes['files'] if f['path'] == 'gone.txt')['status'] == 'deleted'
    assert next(f for f in changes['files'] if f['path'] == 'big.txt')['truncated']
    assert (await client.get(f'/api/sessions/{sid}/changes', params={'snapshot_id': '../bad'})).status_code == 422
