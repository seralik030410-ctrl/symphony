# Symphony 2.0

## Техническое задание на локальный ChatGPT + Codex + Claude Code

Архитектурных слоев: 10  
Acceptance-сценариев: 8  
Этапов пересборки: 8

Версия документа: 1.0  
Дата: 29 августа 2026  
Статус: архитектурный план перед полной пересборкой

> Главная цель: пользователь пишет обычную просьбу в одном чате, а приложение само отвечает, читает нужные навыки, работает с файлами, вызывает разрешенные инструменты, выполняет код в sandbox, проверяет результат и показывает понятный журнал действий. Никаких специальных кнопок вроде «обработать документ» и никаких скрытых маршрутов, которые превращают сайт в Excel.

## 1. Решение в одном абзаце

Symphony 2.0 надо строить как единый агентный runtime, а не как набор отдельных генераторов PDF, Excel и ответов. Модель должна быть планировщиком и собеседником. Инструменты должны выполнять реальные действия. Навыки должны объяснять модели проверенные рабочие процессы. Sandbox должен безопасно исполнять код в постоянной рабочей папке текущего чата. Валидаторы должны проверять итог. Интерфейс должен показывать публичный план, вызовы инструментов, файлы, изменения, ошибки и проверки, но не имитировать скрытые мысли модели.

## 2. Как работает Codex-подобный агент

Codex-подобная система состоит не только из модели. Модель является одним компонентом внутри цикла:

1. Приложение принимает запрос пользователя и вложения.
2. Context Engine собирает только данные текущего чата: последние сообщения, краткую память, выбранные файлы, описание доступных инструментов и метаданные навыков.
3. Модель возвращает либо обычный ответ, либо структурированный вызов инструмента.
4. Policy Engine проверяет разрешения и при необходимости просит подтверждение.
5. Tool Runtime выполняет действие: читает файл, применяет patch, запускает команду, ищет в интернете или собирает документ.
6. Результат инструмента возвращается модели как наблюдение.
7. Модель выбирает следующий шаг или формирует итоговый ответ.
8. Если создан файл или код, отдельный валидатор проверяет его.
9. Все события сохраняются, поэтому обновление страницы не прерывает задачу.

Важное ограничение: пользователю можно показывать план, команды, аргументы, stdout, stderr, diff, проверки и краткие объяснения решений. Нельзя выдавать искусственный текст за полный скрытый внутренний монолог модели. Полезная прозрачность строится на реальных действиях, а не на поддельных «рассуждениях».

## 3. Почему прямой чат Ollama иногда работает лучше Symphony

В прямом чате модель получает простой запрос и может сразу написать HTML, CSS или объяснение. Текущая Symphony помещает перед моделью несколько собственных маршрутизаторов и жестких форматов. Каждый дополнительный обязательный JSON, повторный планировщик и генерация кода увеличивают задержку и дают маленькой модели новую возможность ошибиться.

| Текущая проблема | Что происходит | Последствие |
|---|---|---|
| Keyword-маршрутизация | Запрос сначала классифицируется строковыми правилами | Неожиданный запрос попадает не в тот конвейер |
| Формат по умолчанию Excel | `detect_artifact_type` возвращает XLSX, если формат не распознан | Новые типы задач плохо расширяются |
| Несколько agent-loop | Документы и executable skills используют разные циклы | Дублирование, разные правила и непредсказуемое поведение |
| Монолитный Controller | Чат, Excel CRM, research, файлы и артефакты смешаны в одном классе | Трудно тестировать и безопасно менять |
| Модель пишет целый рендерер | Маленькая модель генерирует сотни строк ReportLab/openpyxl | Обрезанный код, неверные колонки, долгие repair-повторы |
| Плоский sandbox output | Контейнер возвращает ограниченный список одиночных файлов | Нельзя нормально собрать многофайловый сайт или репозиторий |
| Нет Node.js в runtime | В контейнере есть в основном Python-библиотеки | Нельзя запустить современную web-сборку и тесты |
| Контекст 65K везде | Каждый простой запрос резервирует большое окно | Медленный prefill и высокий расход памяти |
| Extractive compaction | Старые сообщения просто режутся до коротких отрывков | Теряются решения, требования и незакрытые задачи |
| Навыки перегружают prompt | Длинные инструкции и каталоги могут передаваться целиком | Модель медленнее и хуже различает главное |

Факт из текущей истории заданий: один PDF-запрос выполнялся около 26 минут, сделал несколько длинных генераций Python и завершился ошибкой обращения к несуществующей колонке. Sandbox выполнил ровно тот код, который получила модель. Значит, основной сбой был до и после sandbox: неверный способ поручить маленькой модели задачу и отсутствие надежного специализированного инструмента.

## 4. Что сохранить, а что переписать

| Решение | Статус | Обоснование |
|---|---|---|
| React-интерфейс и общая визуальная система | Сохранить как основу | Уже есть рабочий каркас, темы и панели |
| FastAPI и Python | Сохранить | Хорошо подходят для локальных моделей и офисных библиотек |
| SQLite | Сохранить, добавить миграции и WAL | Достаточно для локального single-user приложения |
| Адаптеры Ollama/API | Переписать интерфейс, использовать существующий HTTP-код | Нужна единая таблица capabilities и streaming events |
| Парсеры PDF/DOCX/XLSX/PPTX | Переиспользовать после тестов | Это независимые детерминированные компоненты |
| Проверки артефактов | Переиспользовать и расширить | Проверка должна быть отдельной от генерации |
| Docker security flags | Переиспользовать | Основа изоляции уже разумная |
| AgentController | Переписать | Должен исчезнуть монолит и keyword-router |
| Два sandbox/runtime | Заменить одним Tool Runtime | Одинаковая политика и телеметрия для всех действий |
| CRM-специфичные быстрые команды | Вынести в отдельный plugin | Они не должны определять поведение общего ассистента |
| Старый artifact detector | Удалить | Формат выбирает агент или явный инструмент, не fallback XLSX |

## 5. Принципы Symphony 2.0

1. Один чат - одна изолированная сессия и один workspace.
2. Один универсальный agent-loop для локальной и облачной модели.
3. Модель предлагает действие, приложение исполняет и проверяет.
4. Навык не равен инструменту и не дает разрешений.
5. Документы создаются надежными рендерами, кодовые проекты - файловыми и shell-инструментами.
6. Никакого host fallback для непроверенного кода.
7. Любая ошибка инструмента становится наблюдением для ограниченного repair-цикла.
8. В интерфейсе видны только реальные события.
9. Контекст строится по потребности, а не загружается весь целиком.
10. Маленькая модель должна уметь выполнить простой сценарий, но приложение честно сообщает, когда нужна более сильная модель.

## 6. Функциональный охват продукта

### 6.1 Обычный чат

- Ответы на любые общие вопросы, не только о документах.
- Streaming текста без ожидания полного ответа.
- Markdown, кодовые блоки, таблицы и ссылки.
- Редактирование и повтор пользовательского сообщения.
- Stop, Retry, Continue и Fork.
- Выбор локальной или облачной модели для каждого чата.
- Отдельный системный профиль чата: «общий», «код», «документы», «исследование».

### 6.2 Работа с файлами

- Drag and drop файлов, изображений и папок.
- Вложения у конкретного сообщения и постоянные файлы проекта.
- Просмотр текста, таблиц, изображений и metadata до отправки.
- Явная команда «используй этот файл» без автоматического доступа ко всей библиотеке.
- Поддержка PDF, DOCX, XLSX, CSV, PPTX, TXT, Markdown, JSON, изображений и исходного кода.
- Скачивание результата, история версий, diff и восстановление.

### 6.3 Код и сайты

- Создание вложенных каталогов и нескольких файлов.
- `fs.read`, `fs.write`, `fs.apply_patch`, `fs.list`, `search.rg`.
- Запуск shell-команд и тестов в sandbox.
- Поддержка Python и Node.js в базовом runtime.
- Просмотр дерева проекта, кода, diff, терминала и preview сайта.
- Постоянный workspace между шагами одного чата.
- Git status, diff, commit только по явному запросу.
- Локальный preview server с безопасным пробросом localhost-порта.

### 6.4 Документы и артефакты

- PDF: содержание от модели, дизайн-токены от навыка, детерминированный рендер и визуальный QA.
- XLSX: структурная workbook-schema, openpyxl renderer, формулы, стили, ширины, freeze panes, filters и проверки.
- DOCX: структурированный документ, стили, таблицы, headers/footers и render-to-PDF QA.
- PPTX: slide-schema, шаблоны, изображения, таблицы, диаграммы и render QA.
- Для каждого артефакта сохраняются source, recipe, output, validation report и версия.

### 6.5 Vision

- Проверка capability выбранной модели.
- Передача изображения только vision-модели.
- OCR как отдельный локальный инструмент, если vision-модель не нужна.
- Несколько изображений в одном сообщении.
- Preview и удаление вложения до отправки.

### 6.6 Исследование в интернете

- Интернет по умолчанию выключен.
- Модель может вернуть структурированный сигнал `research_needed`.
- Search tool получает только очищенный поисковый запрос, а не весь чат и документы.
- Страницы считаются недоверенными данными.
- Ответ содержит ссылки, даты публикации и дату проверки.
- Если надежного подтверждения нет, приложение сообщает об этом и не додумывает.
- Все сетевые обращения видны в журнале и ограничиваются allowlist.

## 7. Целевая архитектура

### 7.1 Слои

| Слой | Ответственность | Технология первой версии |
|---|---|---|
| Desktop/Web UI | Чаты, файлы, действия, настройки, preview | React + TypeScript |
| Local API | Sessions, uploads, events, settings | FastAPI |
| Agent Core | Единый цикл model - tool - observation - final | Python asyncio |
| Model Gateway | Ollama и OpenAI-compatible API | HTTP adapters |
| Context Engine | История, память, retrieval, token budget | Python + SQLite FTS/vector optional |
| Skill Registry | Discovery, metadata, loading, resources | Local filesystem + SQLite index |
| Tool Registry | JSON schemas, permissions, execution | Python contracts |
| Policy Engine | Sandbox profile, approvals, network | Declarative policies |
| Sandbox Runtime | Команды и сгенерированный код | Docker Desktop |
| Artifact Services | PDF, Excel, Word, PowerPoint | Deterministic Python renderers |
| Event Store | Turns, steps, calls, artifacts, recovery | SQLite WAL |

### 7.2 Поток одного запроса

Пользователь -> Session Service -> Context Engine -> Model Gateway -> Agent Core -> Policy Engine -> Tool Registry -> Sandbox или Artifact Service -> Validator -> Event Store -> UI.

Все провайдеры используют один Agent Core. Облачная модель не получает «особые» навыки или доступ к файлам. Доступ всегда принадлежит локальному host-приложению. Host выбирает разрешенные данные, передает их модели и исполняет tool call. Поэтому локальная и облачная модель должны иметь одинаковые инструменты; отличается только место выполнения inference и capabilities модели.

## 8. Единый Agent Core

### 8.1 Состояния turn

`queued -> preparing -> model_running -> awaiting_approval/tool_running -> verifying -> model_running -> completed`

Дополнительные финальные состояния: `failed`, `cancelled`, `interrupted`.

### 8.2 Псевдокод

1. Загрузить сессию и создать immutable turn record.
2. Собрать ContextPack по token budget.
3. Передать модели только инструменты, подходящие к запросу и разрешениям.
4. Получить поток событий: text delta, public note, tool call или final.
5. Валидировать tool name и JSON arguments.
6. Запросить approval, если действие выходит за автоматическую политику.
7. Выполнить инструмент и сохранить ToolResult.
8. Добавить короткий структурированный результат в контекст.
9. Повторить максимум N шагов.
10. Проверить созданные артефакты и сформировать final.

### 8.3 Ограничения цикла

- Максимум 12 tool calls на turn по умолчанию.
- Максимум 2 repair-попытки одного шага.
- Повтор идентичного вызова блокируется.
- Таймаут задается для каждого tool отдельно.
- Cancel реально завершает subprocess/container.
- После перезапуска turn восстанавливается из event log или честно помечается interrupted.
- Модель не может объявить инструмент успешным без ToolResult со статусом success.

## 9. Model Gateway

### 9.1 Единый контракт провайдера

Каждый adapter обязан реализовать:

- `list_models()`
- `get_capabilities(model)`
- `stream_chat(request)`
- `cancel(request_id)`
- `count_tokens(messages)` или честный estimator
- `health()`

### 9.2 Capabilities модели

| Capability | Пример использования |
|---|---|
| text | Обычный чат |
| vision | Изображения |
| native_tools | Нативный function calling |
| json_schema | Надежные структурированные ответы |
| reasoning_stream | Отдельный поддерживаемый канал summary/thinking, если API его предоставляет |
| max_context | Расчет ContextPack |
| max_output | Безопасный предел ответа |

Если модель не поддерживает native tools, Agent Core использует компактный constrained JSON protocol. Если модель регулярно ломает JSON, приложение не должно бесконечно чинить его тем же запросом. Оно делает одну нормализацию, одну repair-попытку, затем возвращает понятную ошибку или предлагает другую модель.

### 9.3 Настройки

- Несколько Ollama-моделей с быстрым переключением.
- Несколько OpenAI-compatible профилей: URL, model, key reference, capabilities override.
- Ключи только в macOS Keychain или системном secret store.
- Контекст и output настраиваются на модель, а не глобально на все чаты.
- Presets: Fast, Balanced, Deep, Vision.
- Отдельный легкий router допустим позже, но первая версия должна работать без второй модели.

## 10. Context Engine

### 10.1 Что входит в ContextPack

1. Короткий system contract.
2. Состояние текущего workspace и разрешения.
3. Схемы только релевантных инструментов.
4. Метаданные доступных навыков в малом бюджете.
5. Полный текст выбранных навыков.
6. Последние сообщения текущего чата.
7. Структурированная память старой части чата.
8. Найденные фрагменты только нужных документов.
9. Резерв для ответа и результатов инструментов.

### 10.2 Правила контекста

- Никаких файлов из другого чата без явного выбора.
- Короткий файл можно передать целиком; большой файл индексируется и извлекается частями.
- Вложения не добавляются во все будущие сообщения автоматически, если пользователь отключил их от проекта.
- Tool output сокращается до структурированного summary, а полный stdout остается в event store.
- Token budget считается до вызова модели.
- При 70-80 процентах заполнения создается новая memory snapshot.
- Контекст 16K используется как быстрый default; 32K для документов; 64K включается только осознанно.

### 10.3 Автоматическое сжатие

Сжатие должно сохранять не первые 700 символов каждого сообщения, а четыре структуры:

- Facts: подтвержденные факты и пути.
- Decisions: принятые решения и ограничения.
- Open tasks: незавершенные действия.
- Artifact index: созданные файлы и версии.

Memory snapshot имеет версию и ссылки на исходные message IDs. Последние 8-12 сообщений сохраняются дословно. Пользователь может открыть память, отредактировать или очистить ее.

## 11. Навыки

### 11.1 Что такое навык

Навык - локальная папка с `SKILL.md`, optional references, templates, assets и scripts. Навык описывает метод работы. Он сам по себе не читает диск, не запускает код, не включает интернет и не меняет разрешения.

### 11.2 Progressive disclosure

1. При старте индексируются только name, description, path и UI metadata.
2. В prompt помещается компактный каталог подходящих навыков.
3. Навык активируется явно пользователем или автоматически по description.
4. Перед действием host читает полный `SKILL.md`.
5. Связанные reference-файлы читаются только когда их требует выбранный workflow.
6. Scripts запускаются только через зарегистрированный инструмент и Policy Engine.

Это соответствует официальной модели Codex: начальный список навыков ограничен, а полный `SKILL.md` загружается после выбора навыка.

### 11.3 Управление навыками в UI

- Install из ZIP, Git URL или папки.
- Enable/disable без удаления.
- Explicit only, Auto или Always.
- Priority используется только как дополнительный сигнал.
- Просмотр и редактирование `SKILL.md`.
- Просмотр references, templates и scripts.
- Проверка manifest и зависимостей.
- Test prompt: пользователь видит, активируется ли навык.
- Export и soft-delete в корзину.

### 11.4 Правильное разделение

- Skill отвечает на вопрос «как выполнить workflow».
- Tool отвечает на вопрос «какое реальное действие разрешено».
- Template отвечает на вопрос «как стабильно выглядит результат».
- Plugin объединяет навыки, инструменты и шаблоны для одной предметной области.

## 12. Инструменты и function calling

### 12.1 Минимальные инструменты MVP

| Группа | Инструменты |
|---|---|
| Files | list, read, write, apply_patch, mkdir, move_to_trash |
| Search | rg, find_files |
| Shell | exec, status, cancel |
| Project | tree, snapshot, diff, restore |
| Git | status, diff, log; commit только по запросу |
| Artifacts | render_pdf, render_xlsx, render_docx, render_pptx, verify |
| Web | search, open_page с отключенным default |
| Vision | inspect_image, OCR |
| UI | start_preview, stop_preview |

### 12.2 Контракт каждого tool

Каждый инструмент обязан иметь стабильные поля:

- name и title;
- точное описание пользовательского результата;
- JSON input schema;
- JSON output schema;
- permissions;
- readOnly/destructive/openWorld annotations;
- timeout и лимиты;
- ошибки с machine code и понятным message;
- audit event;
- cancellation behavior.

Модели нельзя передавать 100 инструментов сразу. Tool Router детерминированно выбирает небольшую группу по текущему состоянию и типам данных. Внутри выбранной группы модель сама выбирает действие.

## 13. Sandbox

### 13.1 Что должен делать sandbox

- Исполнять сгенерированные команды и код, а не доверенные операции базы данных.
- Иметь read-only root filesystem и non-root user.
- Монтировать только workspace текущего чата.
- Иметь persistent project mount и ephemeral `/tmp`.
- Не получать API keys, Keychain и Docker socket.
- По умолчанию работать без сети.
- Ограничивать CPU, RAM, PIDs, output size и время.
- Убивать весь process tree при Stop.

### 13.2 Профили разрешений

| Профиль | Автоматически | Требует подтверждения |
|---|---|---|
| Read only | Чтение файлов проекта, поиск | Любая запись |
| Project edit | Чтение и изменение текущего workspace с snapshot | Удаление, внешние пути, сеть |
| Build | Project edit, запуск тестов и локальной сборки | Установка пакетов, сетевой доступ |
| Research | Чтение + web allowlist | Любой неизвестный домен |
| Full manual | Только после явного выбора | Все опасные действия по отдельным правилам |

### 13.3 Runtime image

Первая версия образа должна включать Python 3.12, Node.js LTS, git, ripgrep, curl без свободной сети, pytest, офисные библиотеки, Poppler и базовые web build tools. Установка пакетов во время каждого turn запрещена по умолчанию. Для проекта можно создать отдельный dependency setup step с сетью и lockfile, после чего agent phase снова работает offline.

### 13.4 Почему новый sandbox сможет создать сайт

Старый runtime возвращает несколько плоских файлов. Новый runtime работает с настоящим деревом проекта:

- `/workspace/src`
- `/workspace/public`
- `/workspace/package.json`
- `/workspace/tests`

Модель создает файлы через patch-инструмент, запускает `npm test` или `npm run build`, читает ошибку, исправляет код и запускает preview. Результат остается в workspace чата и не упаковывается после каждого шага в base64.

## 14. Документный pipeline

Модель не должна каждый раз программировать ReportLab или openpyxl. Для документов действует схема «содержание -> структура -> renderer -> validator».

### 14.1 PDF

1. Извлечь доказательства из выбранных источников.
2. Сформировать ReportSpec: разделы, таблицы, charts, callouts и citations.
3. Выбрать DesignPreset или применить design skill.
4. Trusted renderer создает PDF.
5. PDF открывается, проверяется и рендерится в PNG.
6. Геометрический validator и optional vision reviewer проверяют страницы.
7. При дефекте исправляется spec или renderer input, а не случайный Python.

### 14.2 Excel

1. Модель формирует WorkbookSpec с sheets, columns, rows, formulas и formats.
2. Pydantic валидирует schema.
3. Renderer пишет XLSX.
4. Validator проверяет структуру, formula references, типы и опасные ссылки.
5. Для сложных вычислений создается отдельный calculation report.

### 14.3 Шаблоны

Нужно начать с небольшого набора качественных шаблонов: Editorial Report, Financial Report, Research Report, Clean Workbook, Dashboard Workbook, Business Document и Presentation. Навык может выбрать шаблон и изменить design tokens. Это быстрее и надежнее, чем заставлять 9B-модель каждый раз изобретать дизайн.

## 15. Интерфейс

### 15.1 Основной экран

- Слева: проекты и чаты.
- Центр: сообщения, tool cards, diff и артефакты.
- Справа: Files, Skills, Context, Tasks.
- Снизу: универсальный composer с drag and drop.
- Сверху: модель, режим Local/API, контекст, безопасность и status.

### 15.2 Карточка выполнения

Карточка показывает:

- текущий публичный этап;
- реальное имя инструмента;
- входные аргументы после redaction;
- разрешения;
- время;
- stdout/stderr;
- созданные файлы;
- diff;
- результат проверки;
- кнопки Stop, Retry и Approve.

Карточка не должна показывать фразы вроде «я глубоко думаю» как доказательство работы. Статусы появляются только из event store: модель вызвана, файл прочитан, команда запущена, тест прошел.

### 15.3 Настройки

- Theme: System, Light, Dark.
- Motion: Full, Reduced, Off.
- Model profiles и API keys.
- Context preset и max output.
- Sandbox profile.
- Internet toggle и allowlist.
- Skill manager.
- Storage usage и очистка.
- Export/import проекта.

### 15.4 macOS

Сначала приложение остается локальным web-приложением FastAPI + React, потому что так проще отладить agent core. После стабильного MVP оно упаковывается в Tauri shell для macOS. Интерфейс должен соблюдать привычные macOS spacing, системную тему, reduced motion, клавиатурные shortcuts, drag and drop и безопасное хранение ключей в Keychain.

## 16. Сессии, проекты и хранение

Каждый chat имеет собственные:

- messages;
- memory snapshots;
- attachments;
- workspace tree;
- tool calls;
- approvals;
- artifacts;
- model and context settings.

Новый чат начинается пустым. Между чатами нет файлов, темы, стран, памяти или активного проекта, пока пользователь явно не выберет «продолжить проект» или не прикрепит ресурс.

Файлы рекомендуется хранить так:

`workspace/projects/<project_id>/chats/<chat_id>/attachments`  
`workspace/projects/<project_id>/chats/<chat_id>/worktree`  
`workspace/projects/<project_id>/chats/<chat_id>/artifacts`  
`workspace/projects/<project_id>/chats/<chat_id>/events`

SQLite хранит metadata и события, а крупные файлы остаются на диске по content hash. Удаление идет через локальную корзину. Любое редактирование сначала создает snapshot или git diff.

## 17. API и события

### 17.1 Минимальные endpoint

- `POST /sessions`
- `GET /sessions/:id`
- `POST /sessions/:id/turns`
- `POST /turns/:id/cancel`
- `GET /turns/:id/events`
- `POST /sessions/:id/files`
- `GET /sessions/:id/tree`
- `GET /sessions/:id/artifacts`
- `GET /models`
- `GET /skills`
- `POST /skills/install`
- `PATCH /skills/:id`
- `GET /tools`
- `POST /approvals/:id/decision`

### 17.2 Event stream

WebSocket или SSE передает типизированные события:

- turn.started;
- context.built;
- model.started/delta/completed;
- skill.selected/read;
- tool.requested/approved/started/output/completed/failed;
- file.changed;
- artifact.created/verified;
- turn.completed/failed/cancelled.

UI строится из event stream и после refresh восстанавливает тот же экран из сохраненных событий.

## 18. Безопасность

- По умолчанию сеть выключена.
- Секреты не попадают в prompt, stdout и sandbox.
- Все пути canonicalized и проверяются относительно workspace root.
- Symlink escape, path traversal и Windows ADS блокируются.
- Загруженные документы и web-страницы всегда имеют trust=untrusted.
- Prompt injection внутри файла не меняет system policy.
- Удаление, публикация, внешняя запись, package install и неизвестная сеть требуют approval.
- Tool result имеет size limits и redaction.
- История действий доступна пользователю.
- Никакой автоматически сгенерированный код не исполняется на host.

Sandbox и approvals должны быть двумя разными слоями. Sandbox технически ограничивает действие. Approval определяет, когда агент обязан остановиться и спросить пользователя.

## 19. Нефункциональные требования

| ID | Требование |
|---|---|
| NFR-01 | Первый токен обычного локального ответа появляется без документного pipeline |
| NFR-02 | UI остается responsive во время длительной задачи |
| NFR-03 | Refresh не отменяет turn и не теряет события |
| NFR-04 | Отмена завершает model request и process tree |
| NFR-05 | Один чат не видит контекст другого чата |
| NFR-06 | Все tool calls имеют schema, status, duration и audit ID |
| NFR-07 | Ошибка инструмента не создает файл-заглушку |
| NFR-08 | Один и тот же сценарий работает через Ollama и API adapter |
| NFR-09 | Простая задача не требует контекста 65K |
| NFR-10 | Установка навыка не дает ему разрешения автоматически |
| NFR-11 | Базовый web-проект собирается в sandbox |
| NFR-12 | PDF/XLSX открываются и проходят форматную проверку до публикации |

## 20. Функциональные acceptance-сценарии

### Сценарий A: обычный вопрос

Запрос: «Почему небо голубое?»  
Ожидание: прямой streaming-ответ. Никаких document tools, Excel и sandbox.

### Сценарий B: простой сайт

Запрос: «Создай небольшой сайт-визитку в этой папке».  
Ожидание: агент создает дерево файлов, показывает diff, запускает build, исправляет ошибку при наличии, открывает preview и сообщает путь. Никакого XLSX fallback.

### Сценарий C: PDF по Excel

Запрос с вложением: «Сделай красивый финансовый отчет PDF».  
Ожидание: файл индексируется, модель формирует ReportSpec, renderer создает PDF, страницы рендерятся, validator проходит, пользователь получает preview и download.

### Сценарий D: Excel

Запрос: «Собери смету из этих данных».  
Ожидание: WorkbookSpec проходит JSON-schema, renderer создает книгу, числа остаются числами, формулы формулами, есть стили, freeze panes и validation report.

### Сценарий E: навык

Пользователь устанавливает навык и выбирает Auto.  
Ожидание: в следующий подходящий запрос видны события skill.selected и skill.read. Скрипт навыка не запускается без tool call и разрешений.

### Сценарий F: новый чат

После разговора о Японии пользователь создает новый чат.  
Ожидание: новый чат не знает о Японии и не видит старые файлы.

### Сценарий G: интернет

Запрос требует актуальной проверки.  
Ожидание: агент запрашивает research tool, источники имеют URL и даты. При выключенном интернете агент честно сообщает ограничение.

### Сценарий H: refresh

Пользователь обновляет страницу во время build.  
Ожидание: turn продолжает выполняться, UI восстанавливает события и актуальный статус.

## 21. Тестирование и evals

### 21.1 Unit

- Provider adapters;
- Context budget;
- Skill matching/loading;
- Tool schema validation;
- Path security;
- Permission decisions;
- Artifact renderers;
- Memory snapshots.

### 21.2 Integration

- Ollama text streaming;
- native tool и JSON fallback;
- persistent sandbox workspace;
- Stop process tree;
- file upload -> retrieval -> answer;
- PDF/XLSX end-to-end;
- API/local parity.

### 21.3 Security

- path traversal;
- symlink escape;
- prompt injection in PDF;
- secret exfiltration;
- network deny;
- fork bomb/PID limit;
- output bomb;
- destructive approval.

### 21.4 Model eval set

Нужно сохранить 30-50 реальных запросов пользователя: обычный чат, сайт, анализ фото, PDF, Excel, исправление кода, поиск и работа с навыком. Каждый релиз прогоняет одинаковый набор на 0.8B, 9B и сильной API-модели. Оценивать надо отдельно routing, tool selection, task completion, latency, artifact validity и factuality.

## 22. Этапы пересборки

### Этап 0. Зафиксировать старую версию

- Сделать отдельную ветку или копию `legacy`.
- Не переносить код вслепую.
- Сохранить реальные failed/success traces как eval fixtures.
- Создать новый каталог приложения с чистыми границами модулей.

Критерий готовности: старое приложение можно запустить для сравнения, новая разработка не меняет его данные.

### Этап 1. Chat parity с Ollama

- Sessions и turns.
- Streaming text.
- Local/API model profiles.
- Полная изоляция чатов.
- Event store и refresh recovery.
- Без tools, документов и специальных маршрутов.

Критерий готовности: Symphony отвечает на обычные запросы не хуже прямого чата Ollama.

### Этап 2. Единый tool-loop

- Tool Registry.
- Structured calls.
- Public action trace.
- Stop, timeout, retry.
- File read/write/patch/search.

Критерий готовности: модель создает и редактирует несколько текстовых файлов в workspace.

### Этап 3. Persistent sandbox для кода

- Python + Node.js image.
- Persistent project mount.
- Shell tool, tests, build и preview.
- Policy profiles и approvals.

Критерий готовности: запрос «создай простой сайт» завершает build и показывает preview.

### Этап 4. Skills 2.0

- Metadata index.
- Progressive disclosure.
- Explicit/Auto/Off.
- Editor, install, remove, test prompt.
- Resource reader и controlled script calls.

Критерий готовности: trace доказывает, какой навык выбран, что прочитано и какой tool вызван.

### Этап 5. Документы

- ReportSpec/WorkbookSpec/DocumentSpec/SlideSpec.
- Trusted renderers.
- Artifact versions и validators.
- Preview страниц и таблиц.

Критерий готовности: PDF и XLSX создаются без model-written renderer code.

### Этап 6. Context, retrieval и vision

- File index.
- Chunk retrieval.
- Structured memory snapshots.
- Vision capability routing и OCR.

Критерий готовности: большие файлы не загружаются полностью в каждый prompt, фото работает только на совместимой модели.

### Этап 7. Research и упаковка macOS

- Search/open tools и citations.
- Network allowlist.
- Tauri shell, Keychain и native drag and drop.
- Installer, update и diagnostics bundle.

Критерий готовности: приложение устанавливается на MacBook, работает local-first и объясняет все отсутствующие зависимости.

## 23. Что не делать в первой версии

- Не запускать несколько агентов параллельно на одной 8 ГБ GPU.
- Не делать marketplace и сложную plugin economy до стабильного tool-loop.
- Не добавлять 20 document templates сразу.
- Не давать sandbox свободную сеть.
- Не делать собственный векторный database server, пока достаточно SQLite index.
- Не требовать 65K контекста для обычного чата.
- Не пытаться показывать скрытую chain-of-thought.
- Не встраивать CRM-логику в универсальный orchestrator.
- Не заставлять модель генерировать renderer с нуля.

## 24. Минимальная версия, которая уже полезна

Первый реально полезный релиз должен уметь только следующее:

1. Надежный обычный чат через Ollama и API.
2. Изолированные сессии и streaming.
3. Постоянный workspace чата.
4. Чтение, запись, patch и поиск файлов.
5. Shell в Docker с Python и Node.
6. Создание простого сайта с build и preview.
7. Установка и чтение навыков.
8. Честный action trace.
9. Stop, retry и восстановление после refresh.

После прохождения этих девяти пунктов добавляются PDF, Excel, vision и research. Такой порядок доказывает, что сердце приложения работает, прежде чем вокруг него появятся тяжелые функции.

## 25. Рекомендации по моделям

- 0.8B использовать только для теста UI, простых ответов или классификации. Не использовать как основного кодового агента.
- 7-9B quantized модель может выполнять короткие tool workflows при хорошем контракте и небольшом контексте.
- Для сложного кода и документов использовать более сильную локальную модель, если она помещается в VRAM, либо API profile.
- На одной GPU orchestrator и workers лучше запускать последовательно. Параллельные агенты конкурируют за VRAM и часто работают медленнее.
- Качество проверять eval-набором, а не названием модели.

Правильная архитектура не превратит 0.8B в сильную модель. Но она перестанет мешать модели, сократит prompt, даст надежные инструменты и не будет требовать от нее каждый раз писать целую офисную библиотеку.

## 26. Стартовая структура нового репозитория

| Путь | Назначение |
|---|---|
| `backend/api` | HTTP endpoints и event streaming |
| `backend/agent` | loop, events, context и memory |
| `backend/models` | base adapter, Ollama и OpenAI-compatible API |
| `backend/skills` | registry, loader и skill policy |
| `backend/tools` | contracts, files, shell, web и artifacts |
| `backend/sandbox` | runtime и permission profiles |
| `backend/artifacts` | PDF, XLSX, DOCX, PPTX и verify |
| `backend/storage` | database, events и workspaces |
| `frontend/src/chat` | сообщения и composer |
| `frontend/src/activity` | tool cards, approvals и progress |
| `frontend/src/files` | дерево, preview и diff |
| `frontend/src/skills` | установка, настройка и редактор |
| `frontend/src/settings` | модели, контекст, сеть и theme |
| `frontend/src/preview` | сайты и артефакты |
| `runtime-image` | Docker image с Python и Node.js |
| `skills` | repo-scoped skills |
| `tests/evals` | реальные пользовательские сценарии |
| `tests/integration` | end-to-end проверки runtime |
| `tests/security` | path, network, secrets и destructive actions |

## 27. Definition of Done для Symphony 2.0 Core

Core считается готовым, когда:

- обычный чат не проходит через document router;
- «создай сайт» создает многофайловый проект и проходит build;
- локальная и API-модель используют один tool registry;
- новый чат имеет нулевой контекст предыдущего;
- каждый skill читается по progressive disclosure;
- sandbox имеет persistent workspace и не видит secrets;
- UI показывает реальные tool calls и diff;
- refresh не теряет turn;
- PDF/XLSX создаются trusted renderers;
- все acceptance-сценарии A-H проходят автоматически или имеют воспроизводимый ручной чек-лист.

## 28. Запрос для начала новой разработки

В новом чате можно использовать такой стартовый запрос:

> Создаем Symphony 2.0 с нуля по документу `docs/SYMPHONY_2_REBUILD_SPEC.md`. Старый код используем только как источник проверенных парсеров, валидаторов и UI-компонентов. Начни с Этапа 0 и Этапа 1: создай чистую структуру, независимые sessions/turns, единый Model Gateway для Ollama и OpenAI-compatible API, streaming events и строгую изоляцию чатов. Не добавляй document router, skills или sandbox до прохождения acceptance-сценария обычного чата. После каждого этапа обновляй implementation log и запускай тесты.

## 29. Источники и опорные материалы

Официальная документация OpenAI использована как архитектурный ориентир, а не как требование копировать закрытые внутренние компоненты:

- Codex best practices: https://learn.chatgpt.com/guides/best-practices
- Agent approvals and security: https://learn.chatgpt.com/docs/agent-approvals-security
- Sandbox: https://learn.chatgpt.com/docs/sandboxing
- Build skills: https://learn.chatgpt.com/docs/build-skills
- Define tools: https://developers.openai.com/plugins/plan/tools
- Codex app-server: https://learn.chatgpt.com/docs/app-server

Файлы текущего проекта, использованные для аудита:

- `app/agent/controller.py`
- `app/agent/document_tools.py`
- `app/agent/tool_loop.py`
- `app/agent/memory.py`
- `app/llm/provider.py`
- `app/runtime/container.py`
- `app/skills/artifact_generator.py`
- `app/config.py`
- `IMPLEMENTATION_LOG.md`

## Заключение

Symphony 2.0 не должна быть копией интерфейса ChatGPT, под которой спрятаны отдельные генераторы. Она должна быть простым и честным агентным host-приложением: одна модель, один цикл, понятные инструменты, управляемые навыки, безопасный sandbox, постоянный workspace, проверенные рендереры и событийный журнал. Сначала надо доказать обычный чат и создание сайта. После этого документы, vision, research и multi-agent добавятся как независимые возможности, а не как новые исключения в монолитном маршрутизаторе.

### Первая контрольная точка

| Проверка | Обязательный результат |
|---|---|
| Обычный чат | Ответ не проходит через document pipeline |
| Новый чат | Не содержит старой темы и файлов |
| Создание сайта | Несколько файлов, успешный build и preview |
| Наблюдаемость | Видны реальные model/tool/verify events |
| Безопасность | Код работает только в sandbox текущего workspace |
| Производительность | Default context 16K, без лишних model calls |

Если эти шесть проверок не проходят, нельзя переходить к PDF, Excel, vision и нескольким агентам. Они только замаскируют неисправное ядро новыми функциями.
