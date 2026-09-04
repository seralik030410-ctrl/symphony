# Карта книги FinControl_Master (актуальна на структуру v1/v2, 35 листов)

Это не абстракция — это то, что реально есть в файле. Если структура книги
изменится (новые листы/таблицы/колонки), перечитай её через
`scripts/audit_workbook.py` и/или `openpyxl`, не полагайся на память из этого
файла вслепую при расхождениях.

## Сквозной поток (из листа 00_README, "FINAL SYSTEM MAP")

```
01_Справочники (Master Data)
  → 02_Budget_BOQ_BOM / Договоры / Variations
    → 03_PR → 04_QEF_PO → 05_Поступления → 06_Выдача → 07_Использование
      → 08_Акты / 14_KS6a
        → 11_Авансы / 11A_Техника
          → 09_PAYREQ → 10_Cash_IO / 15_13W_CF
            → 12_Взаиморасчеты (AP) / Receivables (AR)
              → 13_BvA (Budget/Committed/Actual/ETC/EAC/VAC)
                → 19_Reporting (P&L / Cash Flow / Working Capital / Risk)
                  → 17_Dashboard
16_Control (Control Center) читает из всех модулей параллельно.
99_CHANGELOG — история изменений, НЕ источник истины для текущего состояния
  (см. книга правил, принцип "не доверять предыдущему PASS без проверки").
```

Официальная терминология воркфлоу: **PR → QEF → PO → PAYREQ → Payment → Cash**.
Старые термины STF/TDF/OTF встречаются только в 99_CHANGELOG как история миграции
— не использовать как текущие названия.

## Листы и их роль

| # | Лист | Роль | Ключевые таблицы |
|---|---|---|---|
| 1 | `00_README` | Легенда цвета, пошаговая методология, source-of-truth, текущий sign convention, ссылка на выбранный проект (I5) | — |
| 2 | `01_Справочники` | Master Data Hub — ВСЕ справочные ID отсюда | `tblProjects, tblBlocks, tblCounterparties, tblMaterials, tblUOM, tblCostCodes, tblCurrencies, tblEmployees, tblWarehouses, tblCashAccounts, tblStatuses, tblPriority, tblSettings, tblDocumentStatusMatrix` |
| 3 | `02_Budget_BOQ_BOM` | Бюджет / объёмы работ / спецификация материалов | `tblBudget` (легаси), `tblBudgetNew, tblBOQNew, tblBOMNew` |
| 4 | `03_PR` | Purchase Requisition — потребность, НЕ commitment | `tblPR` |
| 5 | `04_QEF_PO` | Оценка предложений → заказ = commitment | `tblTDFPO` (легаси-гибрид), `tblQEF, tblQEFOffers, tblPO` |
| 6 | `05_Поступления` | Приёмка материала (Receipt ≠ Use) | `tblReceipts` |
| 7 | `06_Выдача` | Склад → бригада (Issue ≠ Use) | `tblIssue` |
| 8 | `07_Использование` | Подтверждённый расход (Actual Cost) | `tblUse` |
| 9 | `08_Акты` | Акты подрядчиков → AP / прогресс BOQ | `tblActs` (70 колонок — см. ниже) |
| 10 | `09_PAYREQ` | Запрос на оплату (Requested/Approved/Executed) | `tblPAYREQ` |
| 11 | `10_Cash_IO` | Фактическое движение денег (Direction+Amount) | `tblCash` |
| 12 | `12_Взаиморасчеты` | AP по контрагентам (balance layer) | `tblAP` |
| 13 | `13_BvA` | Budget vs Actual: Budget/Committed/Actual/ETC/EAC/VAC | `tblBvA` |
| 14 | `14_KS6a` | Физический прогресс по BOQ (форма КС-6а) | `tblKS6a` |
| 15 | `15_13W_CF` | 13-недельный прогноз денежных потоков | — |
| 16 | `16_Control` | Control Center — headline Critical/Technical Critical + список проверок | — (обычный лист, не Table) |
| 17 | `17_Dashboard` | Read-only управленческая панель | — |
| 18 | `18_Бетон` | Спец-учёт бетона (Delivery = услуга, не путать с Concrete Qty) | `tblConcrete` |
| 19 | `19_Reporting` | P&L, Cash Flow, Working Capital, риски (агрегирует, не создаёт транзакций) | — |
| 20 | `20_Fixed_Risk` | Реестр рисков | — |
| 21 | `21_Docs_Audit` | Реестр подтверждающих документов | `tblDocs` |
| 22 | `99_CHANGELOG` | История изменений — справочно, не source of truth | — |
| 23 | `Договоры` | Реестр договоров + связка с BOQ | `tblContracts, tblContractBOQ` |
| 24 | `11_Авансы` | Единый реестр авансов (Employee/Contractor/Supplier/Other) | `tblAdvances` |
| 25 | `11A_Техника` | Техника: табели → начисление → AP | `tblEquip` |
| 26 | `Revenue` | Признание выручки | `tblRevenue` |
| 27 | `Equipment_Forecast` | Прогноз затрат на технику | `tblEquipFcst` |
| 28 | `Opening_Balances` | Входящие остатки (легитимный источник для операций до старта системы) | `tblOpening` |
| 29 | `Receivables` | AR — дебиторская задолженность | `tblAR` |
| 30 | `Other_Costs` | Прочие затраты (FUEL/LOG/ADM/FIN/TAX) | `tblOtherCosts` |
| 31 | `Variations` | Изменения (Draft/Approved меняет только approved base) | `tblVariations` |
| 32 | `Schedule` | График работ | `tblSchedule` |
| 33 | `Inventory_Adjustments` | Корректировки склада | `tblAdjust` |
| 34 | `Approvals_Log` | Журнал согласований | `tblApprovals` |
| 35 | `Weekly_Report` | Еженедельный отчёт | — |

## `tblActs` (08_Акты) — самая широкая таблица, детали по блокам колонок

- **A:U** — базовые поля акта: Document ID, Дата, Project/Contract/Counterparty,
  BOQ Code, Qty Period, Rate, Gross Work, вычеты (Advance Applied, Penalty,
  Refundable Retention, Non-refundable Deduction, Retention Release), Net
  Accrued, Paid, Balance Payable, Tech Accepted, Status, Control.
- **V:BH** — BOQ-контроль и цепочка проверок: Sanad Number, Block/UOM,
  Current/Previous/Cumulative/Remaining BOQ Qty, Claimed vs Accepted vs
  Rejected Qty, BOQ Overrun/Rate/Contract/Validity controls, Advance
  Before/After, Retention Expected/Variance/Balance (cumulative), Penalty
  Reason/Control, Overpayment, Technical/Financial Status, Approved
  By/Evidence.
- **BJ+** (за пределами Table A:BH) — сводные блоки (Act Summary / Contractor
  Summary / BOQ Progress Summary). **Намеренно вынесены за границы таблицы** —
  см. `known-gotchas.md`, не трогать колонки F/G/I/S при добавлении сводок.

## Source-of-Truth Matrix (кто на самом деле владеет цифрой)

| Метрика | Источник |
|---|---|
| Project / Counterparty / Material / Contract / Cost Code и т.д. | `01_Справочники` (Master Data) |
| Current Budget | `tblBudgetNew`, меняется только через `Variations!Status=Approved` |
| Current BOQ | `tblBOQNew` + Approved Variations |
| Current BOM | `tblBOMNew` + Approved Variations |
| PR demand | `tblPR` |
| QEF result / winner | `tblQEF` / `tblQEFOffers` |
| PO Commitment | `tblPO` (Approved/Posted) |
| Material Receipt | `tblReceipts` |
| Warehouse Stock | `06_Выдача` + `Inventory_Adjustments` движения |
| Material Use | `tblUse` |
| Acts / KS6a | `tblActs` → `14_KS6a` (downstream) |
| Advance balance | `tblAdvances` |
| Equipment Accrual | `tblEquip` (Posted Timesheets) |
| PAYREQ | `tblPAYREQ` |
| Cash | `tblCash` (`10_Cash_IO`) |
| AP | `tblAP` (`12_Взаиморасчеты`) |
| AR | `tblAR` (`Receivables`) |
| EAC/VAC | `tblBvA` (`13_BvA`) |
| P&L / Cash Flow / Working Capital | `19_Reporting` (агрегирует сертифицированные источники Stage 5-10, сам не создаёт транзакций) |
| Business Critical / headline controls | `16_Control` |
| Dashboard | только ссылки на Reporting/источники, сам никогда не source of truth |

## Cost Control Source-of-Truth Matrix (по типу Cost Code, из README Stage 10)

| Cost Code type | Actual | Committed | ETC |
|---|---|---|---|
| `COST-MAT` (материалы) | `07_Использование` (Qty Used × Cost) | Open PO − Received | Remaining Need (BOM) − Committed |
| `COST-SUB` (субподряд) | `08_Акты` (Net) | Contract Current Value − Recognized | 0, если Contract покрывает весь BOQ |
| `COST-EQP` (техника) | `11A_Техника` (Posted Timesheets) | остаток внешнего Contract | `Equipment_Forecast` (Approved) |
| `COST-FIX` | `20_Fixed_Risk` | — | — |
| прочие (FUEL/LOG/ADM/FIN/TAX) | `Other_Costs` (Actual/Forecast статусы) | — | — |

## Ключевые формулы и sign conventions этой книги

- **EAC** = Actual/Accrued + Open Committed + Uncommitted ETC (объединённая
  Actual/Accrued-колонка `13_BvA!E`, отдельного accrual-layer для большинства
  cost type нет — не считать дважды).
- **VAC** = Current Budget − EAC. VAC>0 → ожидаемая экономия/headroom (НЕ
  фактические свободные деньги); VAC=0 → forecast at budget; VAC<0 →
  ожидаемый перерасход.
- **Current Budget** = Original Budget + только Approved Variations. Draft/
  Rejected/Cancelled не влияют.
- Алгебраическая проверка EAC при признании commitment: если
  `Committed = Contract − Recognized`, то `EAC = Recognized + Committed + ETC
  = Contract + ETC` не зависит от Recognized — т.е. EAC не должен скакать
  просто от факта признания акта/timesheet при неизменном scope/цене.
- **Current Payable AP** = текущий признанный остаток перед контрагентом.
  **Retention Payable** уже вычтен из Current Payable AP — прибавляется
  отдельно, без задвоения.
  **Total Creditor Exposure** = Current Payable AP (включая mapped Equipment
  AP) + Retention Payable.
- **NWC** = (AR + Advances Paid + Inventory) − (AP + Retention Payable +
  Customer Advances).
- **Open Advance** (11_Авансы) = Issued − Confirmed − Returned − Applied, БЕЗ
  MAX(...,0) — отрицательный остаток — это блокирующий контроль, не 0.
- **Available for New Request (PAYREQ)** = Basis Amount − *другие* открытые
  Approved PAYREQ по этому же Basis (не вычитать сам себя — иначе ложный блок
  на уже оплаченном PAYREQ).
- Convention для сверки с контрагентом: положительный External Balance = мы
  должны контрагенту (совпадает с Internal Net = AP−AR).
- Aging (AP/AR/Advances) считается от **Remaining Balance**, не от original
  суммы; закрытые документы не остаются в overdue aging.

## Настройки (`tblSettings`, 01_Справочники)

Ключевые константы (проверяй актуальное значение в самой книге — эти взяты из
книги правил как ожидаемые):
- `QEF_LIMIT_USD` = 10000.00 (строго `>`, не `>=`: 10000.00 не требует QEF,
  10000.01 требует)
- `MIN_QUOTES` = 3 (минимум валидных предложений, если QEF обязателен)
- `MIN_CASH_BUFFER_USD` — минимальный буфер для 15_13W_CF / Cash Gap

## Текущее сертифицированное состояние (regression baseline, НЕ константа)

Эти цифры — снимок последнего certified pass (см. также §127 в
`principles.md`). Используй их только для сравнения "не сломалось ли что-то
после моих правок", **никогда не зашивай их в production-формулы**
(принцип "no hardcoded certification baselines"). Актуальное состояние всегда
бери из самой книги (`13_BvA`, `16_Control`, `17_Dashboard`).

```
Total Current Budget USD ≈ 806,000
Committed ≈ 346,387
Actual/Accrued ≈ 204,198
ETC ≈ 279,780
EAC ≈ 830,365
VAC ≈ -24,365 (ожидаемый перерасход по проекту в целом)
Revenue ≈ 200,000
Cash USD ≈ 90,980
AR (после cash-derived correction) ≈ 100,000
Current Payable AP ≈ 161,633 (включая mapped Equipment AP ≈ 320)
Retention Payable ≈ 1,380
Total Creditor Exposure ≈ 163,013
NWC ≈ -19,092
Open Advances ≈ 4,500
Technical Critical = 0
Business Critical (headline, 16_Control!B2) = 4
```

На момент подготовки этого скилла аудит-скрипт (`scripts/audit_workbook.py`)
подтверждал: 0 formula errors (по кэшированным значениям), 0 duplicate IDs, 0
external links, 47 Excel Tables, 16 named ranges — технический слой чист;
открытые Business Critical позиции (~15-18 непустых строк в 16_Control) — это
реальные проектные вопросы (forecast overrun, cash gap недели, missing
equipment contract и т.д.), а не дефект системы.
