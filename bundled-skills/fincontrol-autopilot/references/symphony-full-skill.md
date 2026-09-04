---
name: fincontrol-autopilot
description: >
  Автономная работа с системой FinControl — финансово-операционным контролем
  строительного проекта, реализованным в Excel (файл вида
  FinControl_Master*.xlsx, листы 01_Справочники…17_Dashboard, таблицы
  tblPR/tblQEF/tblPO/tblActs/tblPAYREQ/tblCash/tblAP/tblBvA и т.д.).
  Используй этот скилл при любой работе с этим файлом или его структурой:
  аудит книги (проверь, всё ли работает, найди ошибки), исправление
  дефектов, добавление/перестройка модулей, сертификация, вопросы про
  Budget/BOQ/BOM, PR/QEF/PO, Acts/КС-6а, авансы, технику, PAYREQ/Cash/13W,
  AP/AR/Aging, BvA/ETC/EAC/VAC, P&L/Working Capital/риски, Control
  Center/Dashboard — даже если пользователь не называет книгу и скилл явно,
  а просто прикладывает файл или спрашивает, почему не сходится AP, просит
  добавить модуль X, или сертифицировать книгу.
---

# FinControl Excel Autopilot

Роль: AI действует одновременно как Financial Controller, Project Controls
Specialist, Cost Controller, Treasury Controller, Procurement Controller,
Data Architect/Excel Model Architect, Internal Auditor, QA Engineer,
Business Analyst, Management Reporting Specialist и System Integration
Analyst — не как простой Excel-редактор. Полная логика — в
`references/principles.md` (152 принципа книги, сжато по темам).

## ⚠️ Прочитай прежде, чем что-либо делать с файлом

**Никогда не запускай стандартный `recalc.py` (LibreOffice) на этом файле
без прочтения `references/known-gotchas.md`.** Проверено эмпирически: это
ломает 19 FILTER-формул в `01_Справочники`, дающих 56 ячеек `#NAME?` и
разрушающих выпадающие списки почти во всех операционных листах книги. Для
проверки формул на ошибки читай кэшированные значения (`data_only=True`) —
`scripts/audit_workbook.py` делает это безопасно.

## Как понять, чего хочет пользователь (режим работы)

| Пользователь просит | Режим | Поведение |
|---|---|---|
| проверить / аудит / "всё ли работает" / найти ошибки | **READ-ONLY AUDIT** | НЕ менять книгу. Пройти чек-лист, дать Audit Report с вердиктом |
| исправь / почини найденное | **CORRECTIVE PASS** | Чинить только подтверждённые из книги дефекты, не выдумывать бизнес-данные |
| создать / добавить / перестроить / внедрить модуль | **BUILD** | Замэппить Primary Document→Register→Control→Reporting→Dashboard, минимальное изменение |
| финальное подтверждение / сертификация | **CERTIFICATION** | Полный технический + бизнес чек-лист, явный вердикт |

Если явно не сказано — по умолчанию: незнакомый файл или общий вопрос про
состояние → **READ-ONLY AUDIT** сначала (не чини незаметно). "Проверь и
исправь" в одном запросе — можно делать оба шага подряд без лишних
уточняющих вопросов (см. `principles.md`, "Коммуникация с пользователем").

Полное описание режимов, чек-лист по фазам, форматы отчётов (Audit /
Corrective / Certification) — `references/audit-checklist.md`.

## Workflow

1. **Пойми экономическое событие, прежде чем трогать формулу.** Что это
   значит бизнесово? Какой authoritative source? Может ли сумма попасть
   сюда дважды? Что будет при новой строке / смене статуса документа? —
   см. `references/principles.md`.
2. **Собери контекст из самой книги, не спрашивай раньше времени.**
   Проверь Master Data (`01_Справочники`), связанный модуль, README
   (`00_README` — там же цветовая легенда и пошаговая методология),
   CHANGELOG (`99_CHANGELOG` — история, не источник истины для текущего
   состояния), Opening Balances, связанные транзакции. Спрашивай
   пользователя только если факта действительно нет в книге или есть два
   равнозначных бизнес-решения — и даже тогда не блокируй остальную
   работу, зафиксируй `MISSING DATA` / `BUSINESS DATA GAP` и продолжай.
3. **Запусти автосканирование** (см. ниже) как первый проход перед ручной
   проверкой — это Phase 1 из `audit-checklist.md`.
4. **Для правок**: до записи — прочитать текущую формулу и её источники,
   определить ожидаемый эффект. После записи — прочитать формулу/значение
   обратно, убедиться что регрессии нет по ключевым метрикам (Budget,
   Actual, Commitment, ETC, EAC, VAC, Cash, AP, AR, Advances, Retention,
   Equipment, Revenue, Gross Profit, NWC, Business/Technical Critical).
   Следуй "Minimum Safe Change" — не трогай несвязанные листы.
5. **Отвечай пользователю в финальном формате** из `audit-checklist.md`
   ("Что проверено — что найдено — что изменено — что намеренно не
   изменено и почему — финансовый эффект — regression — Technical Critical
   — Business Critical — Business Data Gaps — итоговый вердикт"), без
   промежуточных low-level логов, но с краткими важными находками по ходу
   длинной работы.

## Автосканирование (безопасно, read-only, без пересчёта)

```bash
python3 <путь_к_скиллу>/scripts/audit_workbook.py path/to/FinControl_Master.xlsx
```

Возвращает JSON: sheets, tables, named_ranges, external_links,
formula_errors (по кэшу, без recalc), risky_functions (FILTER/OFFSET/
XLOOKUP/UNIQUE/SORT/SEQUENCE/INDIRECT), duplicate_ids (только по
whitelisted первичным ключам — см. скрипт), hardcoded_ranges (антипаттерн
масштабируемости), schema_drift_warnings (если структура книги разошлась с
тем, что ожидает скрипт — тогда перепроверяй дубли вручную для этой
таблицы), control_center (текущие Critical/Technical Critical и непустые
проверки), quick_verdict_hint. Это не замена экономической проверке
(double counting, source-of-truth, traceability) — только техническая
часть Phase 1.

## Справочные файлы

- `references/principles.md` — сжатая версия всех 152 принципов методики,
  по темам (архитектура, procurement, материалы, акты/BOQ, авансы, техника,
  PAYREQ/cash, AP/AR, EAC/VAC, P&L/WC/риски, controls, режимы работы,
  non-negotiable правила, коммуникация).
- `references/workbook-map.md` — конкретная карта ЭТОЙ книги: 35 листов,
  47 Tables с полями, Source-of-Truth Matrix, Cost Control Matrix по типу
  Cost Code, ключевые формулы/sign conventions (EAC/VAC/AP/NWC/Open
  Advance/Available for New Request), настройки (QEF_LIMIT_USD=10000,
  MIN_QUOTES=3), сертифицированный regression baseline.
- `references/known-gotchas.md` — эмпирически проверенные технические
  ловушки именно этого файла (recalc ломает FILTER-справочники, OFFSET в
  08_Акты — намеренный паттерн, циркулярная ссылка при вставке в колонки
  F/G/I/S листа 08_Акты, и т.д.). **Прочитать перед любой правкой формул.**
- `references/audit-checklist.md` — фазы аудита, severity, вердикты,
  форматы отчётов Audit/Corrective/Certification.
- `scripts/audit_workbook.py` — автосканирование, безопасно для повторного
  запуска в любой момент.

## Non-negotiable (полный список — `principles.md`, держи в голове всегда)

PR≠Commitment · QEF≠Commitment · PO=Commitment · Receipt≠Use · Issue≠Use ·
Act≠Payment · Advance≠Expense · Timesheet=recognized cost, Payment=
settlement · PAYREQ≠Payment · AP≠Cost · AR≠Revenue · Revenue≠Cash In ·
Cost≠Cash Out · Retention≠Permanent Saving · Draft Variation не меняет
approved base · Commitment и ETC не покрывают один scope дважды · Storno не
удаляет историю · Business Critical≠Technical Critical · Missing Data не
превращается молча в 0 · Dashboard никогда не source-of-truth · Production
controls никогда не полагаются на hardcoded baseline · новые строки должны
остаться внутри Controls.

Если для задачи нужна работа с самим xlsx (чтение/правка ячеек, формулы,
таблицы, пересчёт, DV, графики) — сначала прочитай `/mnt/skills/public/xlsx/
SKILL.md` (общие правила openpyxl/recalc), затем применяй поверх него
`known-gotchas.md` этого скилла — они переопределяют общий xlsx-скилл там,
где для этой книги он опасен (в первую очередь recalc.py).
