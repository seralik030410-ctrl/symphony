# FinCtrl 3.0 — план реализации Voice, Vision и ComfyUI

> Перед началом нового чата прочитать полностью:
> `docs/SYMPHONY_2_REBUILD_SPEC.md` и
> `docs/superpowers/specs/2026-09-07-finctrl-3-multimodal-design.md`.

**Цель:** реализовать local-first мультимодальный runtime со сменными API-провайдерами, двумя голосовыми контурами, live vision и встроенной ComfyUI Studio.

**Правило совместимости:** обычный текстовый turn продолжает идти напрямую через существующий Model Gateway. Новые подсистемы опциональны и не участвуют в маршрутизации, пока пользователь явно их не включил.

## Порядок этапов

### Этап 9 — Capability Registry и настройки провайдеров

Создать фундамент, общий для голоса, Vision и генерации.

Основные изменения:

- расширить provider/model capability contracts в `backend/models/base.py`;
- добавить `backend/providers/` с registry, профилями, health checks и secret references;
- не переносить внутрь registry существующую streaming-логику Model Gateway;
- добавить миграции для provider profiles, capability overrides и secret refs;
- добавить API для CRUD профилей и проверки соединения;
- расширить `frontend/src/settings/SettingsPage.tsx` разделом Providers;
- добавить typed API и типы в `frontend/src/api.ts` и `frontend/src/types.ts`;
- добавить маскирование секретов и запрет их возврата в API.

Тесты сначала:

- registry выбирает только включённого провайдера с нужной capability;
- локальный профиль работает без ключа;
- секрет никогда не появляется в response/event/log fixture;
- ошибка health check не ломает остальные профили;
- существующий обычный chat parity остаётся зелёным.

Acceptance:

- можно создать локальный и API-профиль, проверить соединение и назначить capability;
- после рестарта настройки восстанавливаются;
- без дополнительных профилей FinCtrl работает как раньше.

### Этап 10 — Media Asset Store и фоновые jobs

До ComfyUI создать независимую инфраструктуру файлов и долгих заданий.

Основные изменения:

- добавить `backend/media/assets.py`, `jobs.py`, `schemas.py`, `service.py`;
- добавить миграции `media_assets`, `media_jobs`, `media_job_events`, `media_links`;
- хранить blobs в управляемом data-каталоге, SQLite — только metadata/provenance;
- реализовать checksum, thumbnails/posters, trash и permanent cleanup;
- добавить API загрузки, скачивания, очереди, отмены, повтора и удаления;
- публиковать редкие checkpoint events через существующий event store;
- добавить минимальные Queue/Gallery views во frontend.

Тесты сначала:

- дедупликация одинаковых файлов;
- path traversal и недопустимый MIME отклоняются;
- job state transitions валидны и идемпотентны;
- отмена и восстановление после рестарта;
- asset одного session не попадает в scoped query другого.

Acceptance:

- тестовый background job переживает обновление страницы и рестарт backend;
- результат виден в Gallery, удаляется в корзину и очищается окончательно.

### Этап 11 — Модульный голосовой режим

Сначала реализовать наиболее совместимый контур `STT → LLM → TTS`.

Основные изменения:

- добавить `backend/voice/contracts.py`, `gateway.py`, `session.py`, `vad.py`;
- создать STT/TTS adapters с mock, local-compatible и HTTP API-compatible вариантами;
- добавить WebSocket `/api/voice/sessions/{id}/stream`;
- использовать существующий `TurnService` для текстовой части ответа;
- реализовать sentence chunker для раннего TTS;
- связать отмену voice session с cancellation текущего turn;
- добавить `frontend/src/voice/` с capture, playback queue, state machine и VoiceBar;
- добавить Voice settings и выбор устройств;
- сохранять транскрипт, но не raw audio по умолчанию.

Тесты сначала:

- state machine и запрещённые переходы;
- partial/final transcript ordering;
- TTS начинает работу до окончания длинного текста;
- barge-in очищает playback queue и отменяет turn;
- reconnect не дублирует committed user message;
- ошибка TTS оставляет текст ответа доступным.

Acceptance:

- голосовой разговор работает через mock и один реальный локальный STT/TTS профиль;
- пользователь может перебить модель;
- refresh восстанавливает текст и корректное неактивное состояние.

### Этап 12 — Native Omni/realtime adapters

Добавить второй голосовой контур без изменения UI-контракта.

Основные изменения:

- расширить voice contracts audio-in/audio-out deltas и provider session lifecycle;
- добавить адаптер OpenAI-compatible realtime там, где протокол совместим;
- предусмотреть отдельные vendor adapters без условных ветвей в VoiceService;
- реализовать capability negotiation по codec, sample rate, VAD и tool support;
- добавить режимы `Auto`, `Omni`, `Modular`;
- нормализовать transcripts и usage в существующие messages/events;
- добавить latency metrics: first transcript, first text, first audio.

Тесты сначала:

- Auto корректно откатывается на Modular;
- sequence numbers защищают от перестановки audio deltas;
- provider disconnect завершает или безопасно восстанавливает сессию;
- barge-in отправляет provider cancel и локально прекращает playback;
- контекст одного голосового чата не попадает в другой.

Acceptance:

- один realtime adapter проходит end-to-end сценарий;
- переключение Omni/Modular не меняет формат истории чата;
- API-провайдер полностью необязателен.

### Этап 13 — Vision 2: камера, экран и multiple images

Развить существующий Stage 6, не переписывая его базовые гарантии.

Основные изменения:

- расширить attachment contracts массивом изображений и frame provenance;
- добавить capture adapters для camera/screen во frontend;
- добавить preview/selection до отправки;
- создать frame sampler и change detector для live vision;
- ввести limits по frames, dimensions, bytes и token estimate;
- расширить capability overrides для API vision models;
- сохранить immutable attachment uses при retry;
- показывать в Context Trace фактически выбранные кадры.

Тесты сначала:

- multiple attachments сохраняют порядок;
- retry использует исходный snapshot вложений;
- неподдерживающая vision-модель не получает изображения;
- live sampler не отправляет одинаковые кадры бесконечно;
- прекращение screen share немедленно останавливает capture.

Acceptance:

- файл, камера и экран работают через один UX;
- пользователь до отправки видит каждый кадр;
- расход кадров/токенов прозрачно отображается.

### Этап 14 — ComfyUI Connector и Quick Generate

Подключить генерацию без нодового редактора, используя Media Job foundation.

Основные изменения:

- добавить `backend/media/providers/comfyui.py`;
- поддержать connection check, queue prompt, progress, history, cancel и output fetch;
- сделать controlled reverse proxy только для разрешённого ComfyUI origin;
- добавить manager для опционального локального ComfyUI process/container;
- создать parameterized workflow templates и binding schema;
- реализовать Quick Generate для image и video;
- добавить карточки прогресса в чат и полную очередь в Media Workspace;
- добавить действия `повторить`, `прикрепить`, `открыть workflow`, `удалить`.

Тесты сначала:

- workflow binding меняет только разрешённые inputs;
- malicious URL/path/output отклоняется;
- websocket progress переживает reconnect через history reconciliation;
- cancel идемпотентен;
- image/video output получает корректный provenance;
- отсутствие ComfyUI не ломает startup и chat.

Acceptance:

- встроенный и внешний ComfyUI проходят одинаковый контракт;
- image/video генерируются из шаблона, прогресс виден после refresh;
- результат появляется в Gallery и может быть отправлен в чат.

### Этап 15 — Встроенная Workflow Studio

Встроить полноценную нодовую систему без отдельного окна.

Основные изменения:

- добавить вкладки Media Workspace: Generate/Workflow/Queue/Gallery;
- встроить ComfyUI web client через same-origin proxy;
- синхронизировать выбранный workflow с FinCtrl job metadata;
- добавить импорт/экспорт JSON, recent workflows и templates;
- реализовать открытие job/output обратно в соответствующем workflow;
- сохранить размеры панели и активную вкладку;
- сделать полноэкранную внутреннюю страницу для узкого экрана;
- добавить понятный fallback при несовместимом custom node UI.

Тесты сначала:

- proxy не позволяет произвольный origin;
- вкладки не теряют состояние при переходе в чат;
- imported workflow не исполняется до явного запуска;
- output открывает правильную версию workflow;
- keyboard/focus navigation не захватывается навсегда iframe/editor.

Acceptance:

- пользователь строит и запускает ноды внутри FinCtrl;
- Quick Generate и Studio используют одну очередь и одну галерею;
- отдельное окно браузера не открывается.

### Этап 16 — Resource Coordinator и production polish

Объединить подсистемы в устойчивый desktop runtime.

Основные изменения:

- добавить GPU/resource coordinator и профили Conservative/Balanced/Maximum;
- приоритизировать voice/chat над media jobs;
- добавить dependency setup для STT/TTS/ComfyUI и понятную диагностику;
- расширить Windows/macOS launchers опциональными сервисами;
- добавить device/provider diagnostics без утечки секретов;
- провести accessibility, responsive и degraded-mode проход;
- обновить README, user guide, architecture spec и IMPLEMENTATION_LOG;
- добавить миграционный/backup сценарий для media data directory.

Тесты сначала:

- media queue не блокирует voice control path;
- нехватка runtime/модели отображается как actionable state;
- каждый дополнительный сервис может быть выключен;
- clean install запускает текстовый чат до установки media dependencies;
- полный restart восстанавливает sessions, jobs и outputs.

Acceptance:

- установщик/launcher предлагает, но не навязывает тяжёлые зависимости;
- FinCtrl стабильно работает в text-only, voice-only, vision и full-media конфигурациях;
- документация содержит проверенные команды Windows/macOS/Docker.

### Этап 17 — Agent Kernel и система субагентов

Добавить нативную оркестрацию FinCtrl, используя Hermes Agent как архитектурный
ориентир, но не как обязательную runtime-зависимость.

Основные изменения:

- хранить долговечное дерево agent tasks, события, бюджеты и структурированные результаты в SQLite;
- добавить `agent.delegate` для одной задачи и параллельных групп с изолированным контекстом;
- добавить `agent.execute_batch` для ограниченных механических операций без раздувания model context;
- наследовать provider/model по умолчанию, разрешая явную маршрутизацию на другие включённые профили;
- ограничивать права ребёнка пересечением session policy, delegation allowlist и аннотаций инструмента;
- реализовать каскадную отмену, восстановление после рестарта и evidence-preserving result envelope;
- добавить настраиваемые профили Conservative/Balanced/Maximum/Custom для глубины, fan-out,
  параллелизма, шагов, tool calls, токенов и времени;
- добавить API дерева задач и компактный Agent Task Tree под родительским turn;
- проектные instruction-файлы считать недоверенным контекстом, который не может расширять права;
- автоматическое обучение памяти/skills выполнять только через staged proposal и подтверждение.

Server defaults для Maximum допускают модели до 200B: 32 одновременных исполнителя,
глубина 8 и до 512 задач в дереве. Фактический запуск ограничивает Resource Coordinator,
а realtime voice и активный chat всегда имеют более высокий приоритет.

Acceptance:

- родитель делегирует независимые задачи и получает результаты в исходном порядке;
- дети не видят историю родителя или соседей, кроме переданного context envelope;
- ребёнок не может повысить права или обойти approval;
- дерево и результаты восстанавливаются после перезапуска;
- отмена родителя каскадно останавливает незавершённых потомков;
- обычный чат работает при полностью выключенной оркестрации.

### Этап 18 — Agent Control и долговечная фоновая работа

Расширить Agent Kernel управлением уже работающих субагентов без увеличения их полномочий.

Основные изменения:

- добавить долговечный mailbox команд `steer`/`stop` с последовательностями и состояниями доставки;
- разрешить `agent.delegate(background=true)` возвращать управление чату сразу после запуска задач;
- хранить идемпотентные completion receipts для фоновых результатов и показывать их после refresh;
- добавить `agent.control` и HTTP API для просмотра, направления и остановки одного worker или его ветки;
- хранить фазу и время последней активности, помечая длительное молчание как advisory `stalled`;
- использовать пороги 300/600/1800 секунд для Conservative/Balanced/Maximum;
- сохранять незавершённые steering-команды как rejected при гонке с завершением задачи;
- не останавливать медленные модели автоматически только по отсутствию событий;
- не переносить Hermes auto-approve, автоматическую активацию памяти/skills и process handoff.

Acceptance после отложенного тестового прохода:

- пользователь направляет активного субагента, и команда попадает в следующий model iteration;
- stop-one не отменяет соседей, stop-subtree отменяет только выбранную ветку;
- фоновые задачи не блокируют обычный чат, а их завершение переживает перезапуск интерфейса;
- зависшая задача видна, но не уничтожается без дедлайна или явной отмены;
- ни одна control-команда не меняет provider, модель, allowlist, policy или resource limits.

### Этап 19 — Ленивые инструменты и маршрутизация ролей

Сократить контекст инструментов для небольших моделей-оркестраторов и разрешить назначать
специализированные модели только делегированным ролям.

Основные изменения:

- добавить read-only `tool.search`, который ищет только в реестре уже подключённых инструментов;
- на первом model step показывать компактное ядро, а найденные схемы добавлять со следующего шага;
- ограничить поиск allowlist текущего субагента и не считать активацию новым разрешением;
- добавить роли worker/orchestrator/code/research/vision/media/review в долговечные agent tasks;
- хранить необязательные маршруты `{provider_profile_id, model}` по ролям;
- разрешать маршрут в порядке explicit task → role route → current chat;
- отклонять новые задачи с удалённым или выключенным provider вместо скрытого fallback;
- сохранить модель основного чата неизменной и показывать роль в дереве задач;
- добавить компактные настройки lazy tools и моделей по ролям.

Acceptance после отложенного тестового прохода:

- схема найденного инструмента появляется только на следующем model step;
- ребёнок не находит инструмент вне своего allowlist;
- настройка роли переживает restart и применяется к новой задаче;
- explicit provider/model задачи имеет приоритет над ролью;
- выключенный provider даёт явную ошибку и не переключается молча;
- при выключенных lazy tools сохраняется прежняя полная выдача схем.

### Этап 20 — Поиск истории, восстановление базы и heartbeat

Добавить локальную навигацию по истории и наблюдение за фоновой работой без расширения
полномочий оркестратора.

Основные изменения:

- индексировать только текст user/assistant через SQLite FTS5 и поддерживать индекс триггерами;
- искать по ограниченным экранированным токенам, исключая удалённые чаты;
- использовать результаты только для открытия чата, никогда не добавляя их в model context автоматически;
- проверять SQLite до миграций и создавать валидированные online-backup копии;
- хранить пять последних копий, сохранять повреждённый primary/WAL/SHM и восстанавливать только валидную копию;
- завершать запуск явной ошибкой, если целой резервной копии нет;
- создавать долговечный heartbeat-watch для каждой новой фоновой задачи;
- записывать только stalled/resumed/terminal изменения и показывать подтверждаемые уведомления;
- продлевать уже выданную ресурсную аренду внутри исполнителя, не меняя agent activity;
- не разрешать heartbeat запускать модели, инструменты, команды, skills, сеть или расписания.

Acceptance после отложенного тестового прохода:

- существующая и новая история находится после перезапуска, а trash не попадает в результаты;
- streaming-обновления не создают дубликаты FTS и удаление сообщения очищает индекс;
- повреждённая база не перезаписывается без валидной копии и все исходные sidecar-файлы сохраняются;
- фоновые задачи дают ровно одно meaningful-событие на переход состояния;
- heartbeat не маскирует stall обновлением `last_activity_at` и не создаёт новую работу;
- resource lease живёт, пока исполнитель владеет запросом, и освобождается прежними terminal-путями.

## Обязательная проверка после каждого этапа

1. Сначала запустить новые узкие тесты и увидеть ожидаемое падение.
2. Реализовать минимальный проходящий вертикальный срез.
3. Запустить весь backend suite.
4. Запустить frontend tests и production build.
5. Выполнить ручной acceptance-сценарий на реальном runtime, если он установлен.
6. Обновить `IMPLEMENTATION_LOG.md` фактическими результатами, ограничениями и командами.
7. Не объявлять этап готовым при наличии незавершённого cancellation/recovery сценария.

## Рекомендуемый первый вертикальный срез нового чата

Начать только с Этапа 9. До изменения кода:

- проверить чистоту worktree;
- прочитать текущие model/settings contracts;
- написать тесты capability registry и secret redaction;
- добавить одну миграцию и один mock provider;
- провести старый обычный chat acceptance;
- зафиксировать результат в `IMPLEMENTATION_LOG.md`.

Не начинать одновременно Voice и ComfyUI: сначала общий provider contract, затем media jobs и модульный голос. Такой порядок уменьшает число несовместимых протоколов и повторных миграций.
