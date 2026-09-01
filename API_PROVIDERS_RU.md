# Локальная Ollama и облачные API

Symphony одновременно показывает локальную Ollama и один настроенный удалённый OpenAI-compatible профиль. Выбор сохраняется отдельно для каждого чата: один чат может работать через `qwen3.5:9b` в Ollama, другой — через GLM или Qwen API.

## Быстрая настройка Windows

1. Запустите `CONFIGURE_API.bat`.
2. Выберите Z.AI, Qwen/DashScope или произвольный OpenAI-compatible сервер.
3. Введите модель и API-ключ. Ввод ключа скрыт.
4. Перезапустите Symphony и выберите модель в **Настройки → Общее → Модель**.

Настройки сохраняются в локальном `.env`. Файл исключён из Git и из сборки для друга. Не отправляйте его другим людям. В браузерной Windows-сборке ключ хранится локально в этом файле; нативная desktop-сборка использует системное хранилище ключей.

Подготовленные адреса:

- [Z.AI Chat Completion](https://docs.z.ai/api-reference/llm/chat-completion): `https://api.z.ai/api/paas/v4`
- [Qwen OpenAI compatibility](https://help.aliyun.com/en/model-studio/compatibility-of-openai-with-dashscope), International (Singapore): `https://dashscope-intl.aliyuncs.com/compatible-mode/v1`
- Qwen US (Virginia): `https://dashscope-us.aliyuncs.com/compatible-mode/v1`

Адрес должен заканчиваться непосредственно перед `/chat/completions`: Symphony добавляет этот путь сама. Для Qwen важно выбрать endpoint того же региона, где создан API-ключ.

## Что поддерживается

- потоковый ответ и остановка turn;
- текст рассуждения, если API отдаёт `reasoning_content`/совместимое поле;
- usage/token accounting, если API возвращает usage в stream;
- tool calls OpenAI-формата;
- строгая изоляция истории между чатами независимо от provider.

Совместимость конкретной модели с tools, reasoning, vision и максимальным контекстом определяет провайдер. Неизвестный максимум Symphony консервативно считает равным 16K; его можно явно изменить в настройках возможностей модели.

Сейчас одновременно настраивается один удалённый профиль. Чтобы заменить Z.AI на Qwen API, повторно запустите `CONFIGURE_API.bat` и перезапустите Symphony. Несколько сохранённых удалённых endpoint-профилей одновременно потребуют отдельного расширения хранилища профилей; ключи при этом не должны попадать в SQLite или историю событий.
