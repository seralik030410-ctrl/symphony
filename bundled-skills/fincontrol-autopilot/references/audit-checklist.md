# Чек-лист полного аудита и форматы отчётов

## Быстрый старт для READ-ONLY AUDIT

1. Запусти `scripts/audit_workbook.py <файл>` — закрывает Phase 1
   (Workbook health: sheets/tables/named ranges/external links/formula
   errors по кэшу/risky functions/duplicate IDs/hardcoded ranges) и даёт
   снимок `16_Control` за секунды, без риска сломать книгу.
2. Дальше проходи Phase 2-16 вручную/точечно по списку ниже — скрипт не
   заменяет экономическую проверку (double counting, source-of-truth,
   traceability), только техническую.
3. Собери результат в Audit Report (формат ниже).

## Фазы полного аудита (§139)

| Phase | Что проверяется |
|---|---|
| 1 | Workbook health (структура, формулы, ссылки, имена) — см. `audit_workbook.py` |
| 2 | Master Data (`01_Справочники`) — полнота, дубли ID, Active-флаги |
| 3 | Budget / BOQ / BOM / Variations — Current Budget только из Approved Variations |
| 4 | PR / QEF / PO — QEF_LIMIT/MIN_QUOTES, commitment только от PO |
| 5 | Materials — Receipt≠Use≠Issue, склад, Need to Buy, Material ETC |
| 6 | Acts / KS6a — BOQ-контроль, historical rate protection, KS6a=Acts cumulative |
| 7 | Advances — источник (Cash/Opening/Approved), Open Advance без MAX(...,0) |
| 8 | Equipment — Timesheet=recognized cost, Owned vs Rented, rate fallback прозрачен |
| 9 | PAYREQ / Payment / Cash / 13W — Requested≠Approved≠Executed, USD/TJS раздельно, Cash Gap |
| 10 | AP / AR / Aging / Reconciliation — AP≠Cost, AR settlement с basis, aging от Remaining |
| 11 | BvA / ETC / EAC / VAC — без задвоения, VAC=Budget−EAC, Remaining Budget≠VAC |
| 12 | P&L / Working Capital / Risks — recognition≠cash, риск не задвоен в ETC |
| 13 | Controls — false positive/negative, headline считает unique issues |
| 14 | Dashboard — source-driven, reliability warning при неполных данных |
| 15 | Scalability — что будет на строке 4/10/100/1000, `$2:$N` фиксированные диапазоны |
| 16 | Final verdict |

## Severity (§110)

- **CRITICAL** — может дать неверную финансовую цифру/платёж/решение.
- **HIGH** — серьёзный control/integrity issue (например новые строки не
  попадают в Controls).
- **MEDIUM** — слабость forecast/usability/completeness.
- **LOW** — presentation/performance/documentation.

Порядок исправлений: Wrong money → Double counting → Broken linkage →
False negative controls → Scalability → Missing data controls →
Performance → Presentation.

## Вердикты (§126)

- **PASS** — нет technical defects и mandatory business data gaps,
  влияющих на reliability.
- **PASS WITH BUSINESS DATA GAPS** — архитектура и техника корректны, но
  есть факт-gaps, которые нельзя выдумать. Допустимый production-ready
  статус при наличии reliability warnings.
- **PASS WITH ISSUES** — есть исправимые технические слабости, но
  основные цифры пока можно использовать с оговорками.
- **FAIL** — есть дефект, способный дать неверный финансовый результат.

## Формат отчёта — AUDIT MODE (§123)

```
## Executive Verdict
PASS / PASS WITH ISSUES / PASS WITH BUSINESS DATA GAPS / FAIL

## Technical Integrity
- Formula Errors: N
- External Links: N
- Circulars: N
- Broken Names / Broken DV: N
- Duplicate IDs: N
- Referential violations: N

## По модулям
Procurement / Materials / Acts / Advances / Equipment / Treasury / AP-AR /
BvA / Reporting / Dashboard — короткий статус каждого.

## Defect Register
| # | Severity | Sheet | Cell/Table | Problem | Financial Impact | Required Fix |

## Business Issues (не дефекты системы)
Отдельный список — реальные проектные проблемы, которые Control корректно
показал.

## Final Conclusion
Можно ли доверять: Actual / Forecast / Cash / AP-AR / Dashboard — по каждому
прямо да/нет/с оговоркой.
```

## Формат отчёта — CORRECTIVE MODE (§124)

```
| Defect | Confirmed | Fix | Before | After | Regression | Status |
```
Если дефект не подтверждён из книги — `Not Changed`, не чинить
предположения.

## Формат отчёта — CERTIFICATION MODE (§125)

```
Formula Errors / External Links / Referential Integrity / Duplicate IDs /
Broken DV / Broken Names / Technical Critical / Business Critical /
Data Gaps / Regression / Scalability / Dashboard reconciliation
```

## Финальный формат ответа после любой существенной задачи (§152)

```
Что проверено — Что найдено — Что изменено — Что намеренно НЕ изменено (и
почему) — Финансовый эффект — Результат regression — Technical Critical —
Business Critical — Business Data Gaps — Итоговый вердикт
```

Не перегружай пользователя low-level логами по ходу работы, но при длинной
сессии сообщай важные промежуточные находки одной фразой (например: "Нашёл
расхождение AR/Cash на 20 000; сначала проверяю Opening Balances, не
исправляю вслепую").
