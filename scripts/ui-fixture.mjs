// Isolated browser QA: real built frontend, deterministic in-memory API, no user DB/model.
// Run `npm run build` in frontend, then `node scripts/ui-fixture.mjs`.
import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { resolve, extname, sep } from 'node:path';

const dist = fileURLToPath(new URL('../frontend/dist/', import.meta.url));
const sessions = new Map();
const events = new Map();
let nextId = 0;
const now = () => new Date().toISOString();
function session(title) {
  const item = { id: `qa-session-${++nextId}`, title, provider: 'ollama', model: 'ui-fixture',
    policy_profile: 'build', context_window: 32768, max_output: 2048, system_prompt: '',
    created_at: now(), updated_at: now(), messages: [], turns: [] };
  sessions.set(item.id, item);
  return item;
}
function event(turn, type, payload = {}) {
  const list = events.get(turn.id);
  const item = { id: ++nextId, session_id: turn.session_id, turn_id: turn.id,
    sequence: list.length + 1, type, payload, created_at: now() };
  list.push(item);
  turn.last_event_sequence = item.sequence;
  return item;
}
function turn(session, content) {
  const id = `qa-turn-${++nextId}`;
  const message = (role, content) => ({ id: `${id}-${role}`, session_id: session.id,
    turn_id: id, role, content, status: role === 'user' ? 'complete' : 'streaming',
    created_at: now(), updated_at: now() });
  const user_message = message('user', content);
  const assistant_message = message('assistant', '');
  const turn = { id, session_id: session.id, user_message_id: user_message.id,
    assistant_message_id: assistant_message.id, status: 'model_running',
    provider: 'ollama', model: 'ui-fixture', request_id: id, error: null,
    cancel_requested: false, created_at: now(), started_at: now(), finished_at: null,
    last_event_sequence: 0 };
  session.messages.push(user_message, assistant_message);
  session.turns.push(turn);
  events.set(id, []);
  event(turn, 'turn.started');
  event(turn, 'context.built', { estimated_tokens: 950, context_window: 32768, message_count: session.messages.length });
  event(turn, 'model.started', { provider: 'ollama', model: 'ui-fixture' });
  return { turn, user_message, assistant_message };
}
const reasoning = 'Проверка интерфейса: это тестовый поток, а не рассуждение реальной модели. Проверяем раскрытие деталей, прокрутку и восстановление истории.\n';
const paragraph = 'История остаётся доступной: можно вернуться к предыдущим сообщениям, раскрыть детали ответа и продолжить чтение. Поле ввода закреплено внизу, а новые фрагменты не мешают читать старые сообщения.\n\n';
function finish(result) {
  result.assistant_message.status = 'complete';
  result.turn.status = 'completed';
  result.turn.finished_at = now();
  event(result.turn, 'model.usage', { input_tokens: 1234, output_tokens: 456, reasoning_tokens: 89, context_window: 32768 });
  event(result.turn, 'model.completed', { input_tokens: 1234, output_tokens: 456 });
  event(result.turn, 'turn.completed');
}
const history = session('QA · длинный чат');
for (let index = 1; index <= 6; index++) {
  const result = turn(history, `Проверка истории ${index}: как устроена прокрутка?`);
  event(result.turn, 'model.reasoning_delta', { delta: reasoning });
  result.assistant_message.content = `### Ответ ${index}\n\n${paragraph.repeat(3)}`;
  event(result.turn, 'model.delta', { delta: result.assistant_message.content });
  finish(result);
}
session('QA · пустой чат');

createServer(async (req, res) => {
  const url = new URL(req.url, 'http://127.0.0.1');
  const parts = url.pathname.split('/').filter(Boolean);
  const json = (value, status = 200) => {
    res.writeHead(status, { 'Content-Type': 'application/json; charset=utf-8' });
    res.end(JSON.stringify(value));
  };
  try {
    let body = '';
    for await (const chunk of req) body += chunk;
    const input = body ? JSON.parse(body) : {};
    if (url.pathname === '/api/models') return json([{ provider: 'ollama', title: 'UI fixture',
      base_url: '', default_model: 'ui-fixture', models: ['ui-fixture'], available: true,
      health_message: 'Test only', capabilities: {} }]);
    if (url.pathname === '/api/sessions') {
      if (req.method === 'POST') return json(session(input.title));
      return json([...sessions.values()].map(s => ({ ...s, messages: undefined, turns: undefined,
        last_message_preview: s.messages.at(-1)?.content.slice(0, 90) ?? '',
        active_turn: s.turns.some(t => t.status === 'model_running') })));
    }
    if (parts[1] === 'sessions') {
      const selected = sessions.get(parts[2]);
      if (!selected) return json({ detail: 'Unknown QA session' }, 404);
      if (parts[3] === 'turns' && req.method === 'POST') {
        if (input.content === '/error') return json({ detail: 'Тестовая ошибка отправки' }, 503);
        const result = turn(selected, input.content);
        json(result);
        let step = 0;
        const timer = setInterval(() => {
          if (result.turn.status !== 'model_running') return clearInterval(timer);
          if (step < 12) event(result.turn, 'model.reasoning_delta', { delta: reasoning.slice(step * 14, (step + 1) * 14) });
          else if (step < 42) {
            const delta = paragraph;
            result.assistant_message.content += delta;
            event(result.turn, 'model.delta', { delta });
          } else { finish(result); clearInterval(timer); }
          step++;
        }, 400);
        return;
      }
      if (req.method === 'PATCH') Object.assign(selected, input);
      return json(selected);
    }
    if (parts[1] === 'turns') {
      const selected = [...sessions.values()].flatMap(s => s.turns).find(t => t.id === parts[2]);
      if (!selected) return json({ detail: 'Unknown QA turn' }, 404);
      if (parts[3] === 'cancel') {
        selected.status = 'cancelled';
        selected.finished_at = now();
        sessions.get(selected.session_id).messages.find(m => m.id === selected.assistant_message_id).status = 'cancelled';
        event(selected, 'turn.cancelled');
        return json(selected);
      }
      let after = Number(url.searchParams.get('after') ?? 0);
      if (url.searchParams.get('stream') !== 'true') return json(events.get(selected.id).filter(e => e.sequence > after));
      res.writeHead(200, { 'Content-Type': 'text/event-stream', 'Cache-Control': 'no-cache', Connection: 'keep-alive' });
      const flush = () => {
        for (const item of events.get(selected.id).filter(e => e.sequence > after)) {
          res.write(`id: ${item.sequence}\nevent: ${item.type}\ndata: ${JSON.stringify(item)}\n\n`);
          after = item.sequence;
        }
      };
      flush();
      const timer = setInterval(flush, 100);
      res.on('close', () => clearInterval(timer));
      return;
    }
    const path = resolve(dist, `.${url.pathname === '/' ? '/index.html' : url.pathname}`);
    if (!path.startsWith(dist.endsWith(sep) ? dist : dist + sep)) return json({ detail: 'Not found' }, 404);
    const file = await readFile(path);
    res.writeHead(200, { 'Content-Type': { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript', '.css': 'text/css' }[extname(path)] ?? 'application/octet-stream', 'Cache-Control': 'no-store' });
    res.end(file);
  } catch (error) { json({ detail: String(error) }, 500); }
}).listen(8766, '127.0.0.1', () => console.log('UI fixture only: http://127.0.0.1:8766'));
