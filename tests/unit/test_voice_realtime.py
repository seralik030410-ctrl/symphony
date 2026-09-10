import asyncio

import pytest

from backend.voice.realtime import MockRealtimeAdapter
from backend.voice.contracts import RealtimeEvent
from backend.voice.contracts import RealtimeConfig, VoiceError
from backend.voice.realtime import OpenAICompatibleRealtimeAdapter
from websockets.asyncio.server import serve
import json


async def setup_voice(app):
    runtime = app.state.runtime
    chat = runtime.repository.create_session(title='Voice', provider='openai', model='test-model',
        system_prompt='Only this chat.', context_window=4096, max_output=512)
    service = runtime.voice
    service.store.update_settings(chat['id'], {'mode': 'omni', 'realtime_profile_id': 'builtin-openai'})
    adapter = MockRealtimeAdapter()
    service.gateway.register_realtime('builtin-openai', adapter)
    voice = service.store.create(chat['id'])
    voice = service.store.transition(chat['id'], voice['id'], 'listening')
    messages = []
    async def send(value): messages.append(value)
    await service.prepare(voice, {}, send, send)
    return service, voice, adapter.last_connection, service._omni[voice['id']], messages


@pytest.mark.asyncio
async def test_transcript_before_client_commit(app):
    service, voice, connection, controller, messages = await setup_voice(app)
    await connection._events.put(RealtimeEvent('transcript_final', 2, text='Hello'))
    await connection._events.put(RealtimeEvent('completed', 3))
    await asyncio.wait_for(controller.task, 2)
    assert service.store.get(voice['session_id'], voice['id'])['status'] == 'idle'


@pytest.mark.asyncio
async def test_response_before_transcript(app):
    service, voice, connection, controller, messages = await setup_voice(app)
    for event in [RealtimeEvent('text_delta', 2, text='Answer'), RealtimeEvent('completed', 3),
                  RealtimeEvent('transcript_final', 4, text='Hello')]:
        await connection._events.put(event)
    await asyncio.wait_for(controller.task, 2)
    assert service.store.get(voice['session_id'], voice['id'])['status'] == 'idle'
    assert service.repository.get_session(voice['session_id'], include_history=True)['messages'][-1]['content'] == 'Answer'


@pytest.mark.asyncio
async def test_clean_disconnect_is_terminal(app):
    service, voice, connection, controller, messages = await setup_voice(app)
    await connection.close()
    await asyncio.wait_for(controller.task, 2)
    assert service.store.get(voice['session_id'], voice['id'])['status'] == 'error'


@pytest.mark.asyncio
async def test_interrupt_cancels_provider(app):
    service, voice, connection, controller, messages = await setup_voice(app)
    await service.interrupt(voice['session_id'], voice['id'])
    assert connection.cancelled
    assert controller.task.done()


@pytest.mark.asyncio
async def test_input_order_and_chat_isolation(app):
    service, voice, connection, controller, messages = await setup_voice(app)
    with pytest.raises(VoiceError, match='Expected input'):
        await service.send_realtime_audio(voice, 2, b'\0\0')
    assert connection.received == []
    assert connection.config.instructions == 'Only this chat.'
    await service.send_realtime_audio(voice, 1, b'\0\0')
    await service.interrupt(voice['session_id'], voice['id'])


@pytest.mark.asyncio
async def test_auto_falls_back_when_configuration_rejected(app):
    service, voice, connection, controller, messages = await setup_voice(app)
    await service.interrupt(voice['session_id'], voice['id'])
    class Rejected(MockRealtimeAdapter):
        async def connect(self, config): raise VoiceError('configuration', 'Rejected')
    service.gateway.register_realtime('builtin-openai', Rejected())
    service.store.update_settings(voice['session_id'], {'mode': 'auto'})
    fresh = service.store.create(voice['session_id'])
    async def send(value): pass
    result = await service.prepare(fresh, {}, send, send)
    assert result['mode'] == 'modular'
    assert result['fallback'] == 'realtime_unavailable'


@pytest.mark.asyncio
async def test_openai_adapter_over_real_local_websocket():
    received = []
    async def provider(socket):
        await socket.send(json.dumps({'type': 'session.created', 'session': {'id': 'local'}}))
        received.append(json.loads(await socket.recv()))
        await socket.send(json.dumps({'type': 'session.updated', 'session': {'id': 'local'}}))
        for _ in range(3): received.append(json.loads(await socket.recv()))
        for event in [
            {'type': 'conversation.item.input_audio_transcription.completed', 'transcript': 'Hello'},
            {'type': 'response.output_audio.delta', 'delta': 'AAA='},
            {'type': 'response.done', 'response': {'status': 'completed', 'usage': {'total_tokens': 2}}},
        ]: await socket.send(json.dumps(event))
    async with serve(provider, '127.0.0.1', 0) as server:
        port = server.sockets[0].getsockname()[1]
        adapter = OpenAICompatibleRealtimeAdapter({'base_url': f'http://127.0.0.1:{port}/v1'})
        config = RealtimeConfig('test', 'default', 'en', 'pcm16', 'pcm16', 24000, False, False)
        connection = await adapter.connect(config)
        await connection.send_audio(1, b'\0\0')
        await connection.commit()
        events = [event async for event in connection.events()]
        await connection.close()
    assert [event.type for event in events] == ['session_ready', 'transcript_final', 'audio_delta', 'usage', 'completed']
    assert events[0].provider_session_id == 'local'
    assert received[0]['session']['audio']['output']['voice'] == 'alloy'
    assert [item['type'] for item in received[1:]] == ['input_audio_buffer.append', 'input_audio_buffer.commit', 'response.create']
