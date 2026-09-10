import React, { useState, useEffect, useRef } from "react";
import {
  FileText,
  Table as TableIcon,
  Presentation as PresIcon,
  FilePdf,
  FloppyDisk,
  DownloadSimple,
  ArrowsHorizontal,
  Plus,
  Trash,
  ChartBar,
  ChartLine,
  ChartPie,
  TextB,
  TextItalic,
  TextAlignLeft,
  TextAlignCenter,
  TextAlignRight,
  CurrencyDollar,
  Percent,
  Sparkle,
  Function as FxIcon,
  X,
} from "@phosphor-icons/react";
import { api, type OfficeDocument, type OfficeSheetAnalysis } from "../api";
import "./OfficeStudio.css";

export function getExcelColLetter(index: number): string {
  let temp = index;
  let letter = "";
  while (temp >= 0) {
    letter = String.fromCharCode((temp % 26) + 65) + letter;
    temp = Math.floor(temp / 26) - 1;
  }
  return letter;
}

interface OfficeStudioProps {
  sessionId: string;
  path: string;
  revision: number;
  onClose?: () => void;
  onOpenAnother?: (newPath: string) => void;
}

interface CellStyle {
  bold?: boolean;
  italic?: boolean;
  align?: "left" | "center" | "right";
  numFormat?: string;
}

interface ContextMenuState {
  x: number;
  y: number;
  row: number;
  col: number;
}

export function OfficeStudio({ sessionId, path, revision, onOpenAnother }: OfficeStudioProps) {
  const [doc, setDoc] = useState<OfficeDocument | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [toast, setToast] = useState<string | null>(null);

  // Active sub-navigation (sheet or slide)
  const [activeSheetIndex, setActiveSheetIndex] = useState(0);
  const [activeSlideIndex, setActiveSlideIndex] = useState(0);

  // Active cell in spreadsheet
  const [selectedCell, setSelectedCell] = useState<{ row: number; col: number; ref: string } | null>(null);
  const [formulaValue, setFormulaValue] = useState("");

  // Column widths & cell styling
  const [colWidths, setColWidths] = useState<Record<number, number>>({});
  const [cellStyles, setCellStyles] = useState<Record<string, CellStyle>>({});

  // Context menu
  const [contextMenu, setContextMenu] = useState<ContextMenuState | null>(null);

  // AI Analysis Modal
  const [showAnalyzeModal, setShowAnalyzeModal] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [analysisData, setAnalysisData] = useState<OfficeSheetAnalysis | null>(null);

  // Chart Modal
  const [showChartModal, setShowChartModal] = useState(false);
  const [chartType, setChartType] = useState<"bar" | "line" | "pie">("bar");
  const [chartColX, setChartColX] = useState<number>(0);
  const [chartColY, setChartColY] = useState<number>(1);
  const [chartTitle, setChartTitle] = useState("");
  const [embeddingChart, setEmbeddingChart] = useState(false);

  // Convert modal
  const [showConvertModal, setShowConvertModal] = useState(false);
  const [targetFormat, setTargetFormat] = useState("docx");
  const [converting, setConverting] = useState(false);

  // Quick function dropdown open
  const [showFxMenu, setShowFxMenu] = useState(false);

  // Table container ref for keyboard focus
  const gridContainerRef = useRef<HTMLDivElement>(null);

  // Close context menu on window click
  useEffect(() => {
    const handleGlobalClick = () => {
      setContextMenu(null);
      setShowFxMenu(false);
    };
    window.addEventListener("click", handleGlobalClick);
    return () => window.removeEventListener("click", handleGlobalClick);
  }, []);

  // Load document inspection on mount or path/revision change
  useEffect(() => {
    let stale = false;
    setLoading(true);
    setError("");
    api.officeInspect(sessionId, path)
      .then((data) => {
        if (!stale) {
          setDoc(data);
          setDirty(false);
          setLoading(false);
          setActiveSheetIndex(0);
          setActiveSlideIndex(0);
          setSelectedCell(null);
          setFormulaValue("");
          // Extract column widths from backend inspection
          const firstSheet = data.sheets?.[0];
          if (firstSheet && (firstSheet as any).column_widths) {
            const widthsObj = (firstSheet as any).column_widths as Record<string, number>;
            const parsed: Record<number, number> = {};
            Object.entries(widthsObj).forEach(([letter, w]) => {
              const code = letter.charCodeAt(0) - 65;
              if (code >= 0) parsed[code] = Math.max(60, Math.round(w * 8));
            });
            setColWidths(parsed);
          }
        }
      })
      .catch((err) => {
        if (!stale) {
          setError(String(err.message || err));
          setLoading(false);
        }
      });
    return () => {
      stale = true;
    };
  }, [sessionId, path, revision]);

  const showToast = (msg: string) => {
    setToast(msg);
    setTimeout(() => setToast(null), 3200);
  };

  // Save handler
  const handleSave = async () => {
    if (!doc) return;
    setSaving(true);
    try {
      if (doc.format === "docx") {
        const paragraph_updates = doc.paragraphs?.map((p) => ({
          index: p.index,
          text: p.text,
        }));
        const table_updates = doc.tables?.map((t) => ({
          table_index: t.index,
          cells: t.rows.flatMap((row, r_idx) =>
            row.map((val, c_idx) => ({
              row: r_idx,
              col: c_idx,
              text: String(val),
            }))
          ),
        }));

        const res = await api.officeSave(sessionId, {
          path,
          format: "docx",
          paragraph_updates,
          table_updates,
        });
        setDoc(res.document);
        setDirty(false);
        showToast("Документ успешно сохранён");
      } else if (doc.format === "xlsx") {
        const activeSheet = doc.sheets?.[activeSheetIndex];
        if (activeSheet) {
          const cell_updates: Array<{ sheet: string; row: number; col: number; value: unknown }> = [];
          activeSheet.rows.forEach((row, rIdx) => {
            row.forEach((val, cIdx) => {
              cell_updates.push({
                sheet: activeSheet.name,
                row: rIdx + 1,
                col: cIdx + 1,
                value: val,
              });
            });
          });

          // Collect style updates
          const style_updates = Object.entries(cellStyles).map(([cellRef, style]) => ({
            sheet: activeSheet.name,
            cell: cellRef,
            bold: style.bold,
            italic: style.italic,
            align: style.align,
            number_format: style.numFormat,
          }));

          const res = await api.officeSave(sessionId, {
            path,
            format: "xlsx",
            cell_updates,
            style_updates: style_updates.length > 0 ? style_updates : undefined,
          });
          setDoc(res.document);
          setDirty(false);
          showToast("Таблица успешно сохранена");
        }
      } else if (doc.format === "pptx") {
        const slide_updates = doc.slides?.map((s) => ({
          index: s.index,
          title: s.title,
          bullets: s.bullets,
          notes: s.notes,
        }));
        const res = await api.officeSave(sessionId, {
          path,
          format: "pptx",
          slide_updates,
        });
        setDoc(res.document);
        setDirty(false);
        showToast("Презентация сохранена");
      }
    } catch (err: unknown) {
      showToast(`Ошибка сохранения: ${String((err as Error).message || err)}`);
    } finally {
      setSaving(false);
    }
  };

  // Convert handler
  const handleConvert = async () => {
    setConverting(true);
    try {
      const res = await api.officeConvert(sessionId, {
        source_path: path,
        target_format: targetFormat,
      });
      setShowConvertModal(false);
      showToast(`Конвертировано в ${res.output_path}`);
      if (onOpenAnother) {
        onOpenAnother(res.output_path);
      }
    } catch (err: unknown) {
      showToast(`Ошибка конвертации: ${String((err as Error).message || err)}`);
    } finally {
      setConverting(false);
    }
  };

  // AI Analysis handler
  const handleRunAnalysis = async () => {
    if (!doc) return;
    setAnalyzing(true);
    setShowAnalyzeModal(true);
    try {
      const sheetName = doc.sheets?.[activeSheetIndex]?.name;
      const res = await api.officeAnalyze(sessionId, path, sheetName, true);
      setAnalysisData(res);
    } catch (err) {
      showToast(`Ошибка анализа: ${String((err as Error).message || err)}`);
    } finally {
      setAnalyzing(false);
    }
  };

  // Embed chart into Excel workbook handler
  const handleEmbedChart = async () => {
    if (!doc || !doc.sheets?.[activeSheetIndex]) return;
    setEmbeddingChart(true);
    try {
      const sheet = doc.sheets[activeSheetIndex];
      const xLetter = getExcelColLetter(chartColX);
      const yLetter = getExcelColLetter(chartColY);
      const rowCount = Math.max(sheet.rows.length, 2);

      const title = chartTitle.trim() || `${sheet.headers?.[chartColY] || "Значения"} по ${sheet.headers?.[chartColX] || "Категориям"}`;

      await api.officeSave(sessionId, {
        path,
        format: "xlsx",
        charts: [
          {
            sheet: sheet.name,
            chart_type: chartType,
            data_range: `${yLetter}1:${yLetter}${rowCount}`,
            categories_range: `${xLetter}2:${xLetter}${rowCount}`,
            title,
            target_cell: "G2",
          },
        ],
      });

      // Reload document to get updated chart metadata
      const updated = await api.officeInspect(sessionId, path);
      setDoc(updated);
      setShowChartModal(false);
      showToast(`График "${title}" успешно встроен в лист ${sheet.name}`);
    } catch (err) {
      showToast(`Ошибка добавления графика: ${String((err as Error).message || err)}`);
    } finally {
      setEmbeddingChart(false);
    }
  };

  // Keyboard navigation on grid
  const handleGridKeyDown = (e: React.KeyboardEvent) => {
    if (!selectedCell || !doc?.sheets?.[activeSheetIndex]) return;
    const sheet = doc.sheets[activeSheetIndex];
    const maxRows = sheet.rows.length;
    const maxCols = Math.max(sheet.max_column, 6);
    const { row, col } = selectedCell;

    if (e.key === "ArrowUp") {
      e.preventDefault();
      const nextRow = Math.max(0, row - 1);
      const ref = `${getExcelColLetter(col)}${nextRow + 1}`;
      setSelectedCell({ row: nextRow, col, ref });
      setFormulaValue(String(sheet.rows[nextRow]?.[col] ?? ""));
    } else if (e.key === "ArrowDown") {
      e.preventDefault();
      const nextRow = Math.min(maxRows - 1, row + 1);
      const ref = `${getExcelColLetter(col)}${nextRow + 1}`;
      setSelectedCell({ row: nextRow, col, ref });
      setFormulaValue(String(sheet.rows[nextRow]?.[col] ?? ""));
    } else if (e.key === "ArrowLeft") {
      e.preventDefault();
      const nextCol = Math.max(0, col - 1);
      const ref = `${getExcelColLetter(nextCol)}${row + 1}`;
      setSelectedCell({ row, col: nextCol, ref });
      setFormulaValue(String(sheet.rows[row]?.[nextCol] ?? ""));
    } else if (e.key === "ArrowRight") {
      e.preventDefault();
      const nextCol = Math.min(maxCols - 1, col + 1);
      const ref = `${getExcelColLetter(nextCol)}${row + 1}`;
      setSelectedCell({ row, col: nextCol, ref });
      setFormulaValue(String(sheet.rows[row]?.[nextCol] ?? ""));
    } else if (e.key === "Tab") {
      e.preventDefault();
      const nextCol = e.shiftKey ? Math.max(0, col - 1) : Math.min(maxCols - 1, col + 1);
      const ref = `${getExcelColLetter(nextCol)}${row + 1}`;
      setSelectedCell({ row, col: nextCol, ref });
      setFormulaValue(String(sheet.rows[row]?.[nextCol] ?? ""));
    } else if (e.key === "Enter") {
      e.preventDefault();
      const nextRow = e.shiftKey ? Math.max(0, row - 1) : Math.min(maxRows - 1, row + 1);
      const ref = `${getExcelColLetter(col)}${nextRow + 1}`;
      setSelectedCell({ row: nextRow, col, ref });
      setFormulaValue(String(sheet.rows[nextRow]?.[col] ?? ""));
    } else if (e.key === "Delete" && document.activeElement?.tagName !== "INPUT") {
      e.preventDefault();
      if (sheet.rows[row]) {
        sheet.rows[row][col] = "";
        setFormulaValue("");
        setDoc({ ...doc });
        setDirty(true);
      }
    }
  };

  // Column resize handle
  const handleMouseDownResize = (e: React.MouseEvent, cIdx: number) => {
    e.preventDefault();
    e.stopPropagation();
    const startX = e.clientX;
    const startWidth = colWidths[cIdx] || 90;

    const handleMouseMove = (moveEvent: MouseEvent) => {
      const delta = moveEvent.clientX - startX;
      const newWidth = Math.max(45, startWidth + delta);
      setColWidths((prev) => ({ ...prev, [cIdx]: newWidth }));
    };

    const handleMouseUp = () => {
      window.removeEventListener("mousemove", handleMouseMove);
      window.removeEventListener("mouseup", handleMouseUp);
    };

    window.addEventListener("mousemove", handleMouseMove);
    window.addEventListener("mouseup", handleMouseUp);
  };

  // Quick Formula Insertion
  const handleInsertFormula = (funcName: "SUM" | "AVERAGE" | "COUNT" | "MIN" | "MAX") => {
    if (!selectedCell || !doc?.sheets?.[activeSheetIndex]) return;
    const sheet = doc.sheets[activeSheetIndex];
    const { row, col, ref } = selectedCell;
    const colLetter = getExcelColLetter(col);
    const startRow = 2; // assuming row 1 is header
    const endRow = Math.max(row, 2);
    const formula = `=${funcName}(${colLetter}${startRow}:${colLetter}${endRow})`;

    sheet.rows[row][col] = formula;
    setFormulaValue(formula);
    setDoc({ ...doc });
    setDirty(true);
    setShowFxMenu(false);
  };

  // Context Menu Actions
  const handleContextMenuAction = (action: string) => {
    if (!contextMenu || !doc?.sheets?.[activeSheetIndex]) return;
    const sheet = doc.sheets[activeSheetIndex];
    const { row, col } = contextMenu;
    const maxCol = Math.max(sheet.max_column, 6);

    if (action === "insert_row_above") {
      sheet.rows.splice(row, 0, new Array(maxCol).fill(""));
    } else if (action === "insert_row_below") {
      sheet.rows.splice(row + 1, 0, new Array(maxCol).fill(""));
    } else if (action === "insert_col_left") {
      sheet.rows.forEach((r) => r.splice(col, 0, ""));
      sheet.max_column = (sheet.max_column || 0) + 1;
    } else if (action === "insert_col_right") {
      sheet.rows.forEach((r) => r.splice(col + 1, 0, ""));
      sheet.max_column = (sheet.max_column || 0) + 1;
    } else if (action === "delete_row") {
      if (sheet.rows.length > 1) {
        sheet.rows.splice(row, 1);
      }
    } else if (action === "delete_col") {
      sheet.rows.forEach((r) => r.splice(col, 1));
      sheet.max_column = Math.max(1, (sheet.max_column || 1) - 1);
    } else if (action === "clear_cell") {
      if (sheet.rows[row]) {
        sheet.rows[row][col] = "";
      }
      if (selectedCell?.row === row && selectedCell?.col === col) {
        setFormulaValue("");
      }
    }

    setContextMenu(null);
    setDoc({ ...doc });
    setDirty(true);
  };

  if (loading) {
    return (
      <div className="office-studio">
        <p className="workspace-notice" role="status">Загрузка документа {path}…</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="office-studio">
        <p className="workspace-notice" role="alert">{error}</p>
      </div>
    );
  }

  if (!doc) return null;

  const rawUrl = api.officeRawUrl(sessionId, path);
  const badgeClass =
    doc.format === "docx"
      ? "badge-docx"
      : doc.format === "xlsx"
      ? "badge-xlsx"
      : doc.format === "pptx"
      ? "badge-pptx"
      : doc.format === "pdf"
      ? "badge-pdf"
      : "badge-generic";

  const FormatIcon =
    doc.format === "docx"
      ? FileText
      : doc.format === "xlsx"
      ? TableIcon
      : doc.format === "pptx"
      ? PresIcon
      : doc.format === "pdf"
      ? FilePdf
      : FileText;

  const currentCellStyle = selectedCell ? cellStyles[selectedCell.ref] || {} : {};

  return (
    <div className="office-studio">
      {/* Top Header Toolbar */}
      <header className="office-toolbar">
        <div className="office-title-group">
          <FormatIcon size={20} />
          <span className={`office-format-badge ${badgeClass}`}>{doc.format}</span>
          <span className="office-filename" title={path}>{doc.file_name}</span>
          <span className="office-meta-pill">{(doc.file_size / 1024).toFixed(1)} КБ</span>
          {doc.total_words !== undefined && (
            <span className="office-meta-pill">{doc.total_words.toLocaleString()} слов</span>
          )}
          {doc.sheet_count !== undefined && (
            <span className="office-meta-pill">{doc.sheet_count} лист(ов)</span>
          )}
          {doc.slide_count !== undefined && (
            <span className="office-meta-pill">{doc.slide_count} слайд(ов)</span>
          )}
          {doc.page_count !== undefined && (
            <span className="office-meta-pill">{doc.page_count} стр.</span>
          )}
        </div>

        <div className="office-actions-group">
          {toast && <span className="office-toast">{toast}</span>}

          <button
            className="office-btn"
            onClick={() => setShowConvertModal(true)}
            title="Конвертировать документ"
          >
            <ArrowsHorizontal size={15} />
            <span>Конвертировать</span>
          </button>

          <a
            className="office-btn"
            href={rawUrl}
            download={doc.file_name}
            title="Скачать оригинал"
          >
            <DownloadSimple size={15} />
            <span>Скачать</span>
          </a>

          {doc.format !== "pdf" && (
            <button
              className="office-btn office-btn-primary"
              disabled={!dirty || saving}
              onClick={handleSave}
              title="Сохранить изменения"
            >
              <FloppyDisk size={15} />
              <span>{saving ? "Сохраняем…" : dirty ? "Сохранить" : "Сохранено"}</span>
            </button>
          )}
        </div>
      </header>

      {/* Main Content Area */}
      <div className="office-content-area">
        {/* 1. DOCX DOCUMENT VIEW */}
        {doc.format === "docx" && (
          <div className="office-paper-scroll">
            <div className="office-paper">
              {doc.headings?.length ? (
                <div style={{ marginBottom: "20px" }}>
                  {doc.headings.map((h, idx) => (
                    <div
                      key={idx}
                      className={`doc-heading-${h.level}`}
                      style={{
                        fontSize: h.level === 0 ? "28px" : h.level === 1 ? "22px" : "18px",
                        fontWeight: 700,
                        margin: "12px 0 6px 0",
                        color: "#1e293b",
                      }}
                      contentEditable
                      suppressContentEditableWarning
                      onBlur={(e) => {
                        const newText = e.currentTarget.textContent || "";
                        if (doc.paragraphs && doc.paragraphs[h.index]) {
                          doc.paragraphs[h.index].text = newText;
                          h.text = newText;
                          setDirty(true);
                        }
                      }}
                    >
                      {h.text}
                    </div>
                  ))}
                </div>
              ) : null}

              {/* Document Paragraphs */}
              {doc.paragraphs?.map((p, idx) => {
                if (p.is_heading) return null;
                return (
                  <p
                    key={idx}
                    className="doc-paragraph"
                    contentEditable
                    suppressContentEditableWarning
                    onBlur={(e) => {
                      p.text = e.currentTarget.textContent || "";
                      setDirty(true);
                    }}
                  >
                    {p.text}
                  </p>
                );
              })}

              {/* Document Tables */}
              {doc.tables?.map((table, tIdx) => (
                <div key={tIdx} className="doc-table-wrapper">
                  <table className="doc-table">
                    <tbody>
                      {table.rows.map((row, rIdx) => (
                        <tr key={rIdx}>
                          {row.map((cellText, cIdx) => (
                            <td key={cIdx}>
                              <input
                                value={cellText}
                                onChange={(e) => {
                                  table.rows[rIdx][cIdx] = e.target.value;
                                  setDoc({ ...doc });
                                  setDirty(true);
                                }}
                              />
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* 2. XLSX SPREADSHEET STUDIO */}
        {doc.format === "xlsx" && (
          <div
            className="office-spreadsheet-container"
            ref={gridContainerRef}
            tabIndex={0}
            onKeyDown={handleGridKeyDown}
          >
            {/* Spreadsheet Formatting & Action Toolbar */}
            <div className="office-spreadsheet-toolbar">
              <div className="office-format-group">
                <button
                  className={`office-format-btn ${currentCellStyle.bold ? "active" : ""}`}
                  title="Жирный шрифт"
                  disabled={!selectedCell}
                  onClick={() => {
                    if (!selectedCell) return;
                    setCellStyles((prev) => ({
                      ...prev,
                      [selectedCell.ref]: {
                        ...prev[selectedCell.ref],
                        bold: !prev[selectedCell.ref]?.bold,
                      },
                    }));
                    setDirty(true);
                  }}
                >
                  <TextB size={15} />
                </button>

                <button
                  className={`office-format-btn ${currentCellStyle.italic ? "active" : ""}`}
                  title="Курсив"
                  disabled={!selectedCell}
                  onClick={() => {
                    if (!selectedCell) return;
                    setCellStyles((prev) => ({
                      ...prev,
                      [selectedCell.ref]: {
                        ...prev[selectedCell.ref],
                        italic: !prev[selectedCell.ref]?.italic,
                      },
                    }));
                    setDirty(true);
                  }}
                >
                  <TextItalic size={15} />
                </button>

                <span className="office-toolbar-divider" />

                <button
                  className={`office-format-btn ${currentCellStyle.align === "left" ? "active" : ""}`}
                  title="По левому краю"
                  disabled={!selectedCell}
                  onClick={() => {
                    if (!selectedCell) return;
                    setCellStyles((prev) => ({
                      ...prev,
                      [selectedCell.ref]: { ...prev[selectedCell.ref], align: "left" },
                    }));
                    setDirty(true);
                  }}
                >
                  <TextAlignLeft size={15} />
                </button>

                <button
                  className={`office-format-btn ${currentCellStyle.align === "center" ? "active" : ""}`}
                  title="По центру"
                  disabled={!selectedCell}
                  onClick={() => {
                    if (!selectedCell) return;
                    setCellStyles((prev) => ({
                      ...prev,
                      [selectedCell.ref]: { ...prev[selectedCell.ref], align: "center" },
                    }));
                    setDirty(true);
                  }}
                >
                  <TextAlignCenter size={15} />
                </button>

                <button
                  className={`office-format-btn ${currentCellStyle.align === "right" ? "active" : ""}`}
                  title="По правому краю"
                  disabled={!selectedCell}
                  onClick={() => {
                    if (!selectedCell) return;
                    setCellStyles((prev) => ({
                      ...prev,
                      [selectedCell.ref]: { ...prev[selectedCell.ref], align: "right" },
                    }));
                    setDirty(true);
                  }}
                >
                  <TextAlignRight size={15} />
                </button>

                <span className="office-toolbar-divider" />

                <button
                  className="office-format-btn"
                  title="Формат валюты ($#,##0.00)"
                  disabled={!selectedCell}
                  onClick={() => {
                    if (!selectedCell) return;
                    setCellStyles((prev) => ({
                      ...prev,
                      [selectedCell.ref]: { ...prev[selectedCell.ref], numFormat: "$#,##0.00" },
                    }));
                    setDirty(true);
                    showToast(`Формат валюты применён к ${selectedCell.ref}`);
                  }}
                >
                  <CurrencyDollar size={15} />
                </button>

                <button
                  className="office-format-btn"
                  title="Процентный формат (0.0%)"
                  disabled={!selectedCell}
                  onClick={() => {
                    if (!selectedCell) return;
                    setCellStyles((prev) => ({
                      ...prev,
                      [selectedCell.ref]: { ...prev[selectedCell.ref], numFormat: "0.0%" },
                    }));
                    setDirty(true);
                    showToast(`Процентный формат применён к ${selectedCell.ref}`);
                  }}
                >
                  <Percent size={15} />
                </button>

                {/* Quick Formula Dropdown */}
                <div style={{ position: "relative" }}>
                  <button
                    className="office-format-btn"
                    title="Вставить формулу"
                    disabled={!selectedCell}
                    onClick={(e) => {
                      e.stopPropagation();
                      setShowFxMenu(!showFxMenu);
                    }}
                  >
                    <FxIcon size={15} />
                    <span style={{ fontSize: "11px", fontWeight: 700 }}>Функция</span>
                  </button>

                  {showFxMenu && (
                    <div className="office-fx-dropdown">
                      <div className="office-fx-item" onClick={() => handleInsertFormula("SUM")}>
                        <span className="fx-symbol">Σ</span> СУММА (=SUM)
                      </div>
                      <div className="office-fx-item" onClick={() => handleInsertFormula("AVERAGE")}>
                        <span className="fx-symbol">x̄</span> СРЗНАЧ (=AVERAGE)
                      </div>
                      <div className="office-fx-item" onClick={() => handleInsertFormula("COUNT")}>
                        <span className="fx-symbol">#</span> СЧЁТ (=COUNT)
                      </div>
                      <div className="office-fx-item" onClick={() => handleInsertFormula("MIN")}>
                        <span className="fx-symbol">▼</span> МИН (=MIN)
                      </div>
                      <div className="office-fx-item" onClick={() => handleInsertFormula("MAX")}>
                        <span className="fx-symbol">▲</span> МАКС (=MAX)
                      </div>
                    </div>
                  )}
                </div>
              </div>

              {/* Data & AI Action Buttons */}
              <div className="office-format-group">
                <button
                  className="office-btn"
                  style={{ fontSize: "11px", padding: "3px 9px" }}
                  onClick={handleRunAnalysis}
                  title="Запустить глубокий анализ данных листа"
                >
                  <Sparkle size={13} color="var(--accent)" />
                  <span>Анализ данных</span>
                </button>

                <button
                  className="office-btn"
                  style={{ fontSize: "11px", padding: "3px 9px" }}
                  onClick={() => setShowChartModal(true)}
                  title="Построить и встроить диаграмму"
                >
                  <ChartBar size={13} />
                  <span>Диаграмма</span>
                </button>
              </div>
            </div>

            {/* Formula Bar */}
            <div className="office-formula-bar">
              <span className="office-cell-address">
                {selectedCell ? selectedCell.ref : "—"}
              </span>
              <span className="office-formula-fx">fx</span>
              <input
                className="office-formula-input"
                value={formulaValue}
                placeholder="Значение или формула (например =SUM(B2:B5))"
                onChange={(e) => {
                  const newVal = e.target.value;
                  setFormulaValue(newVal);
                  if (selectedCell && doc.sheets?.[activeSheetIndex]) {
                    const sheet = doc.sheets[activeSheetIndex];
                    if (sheet.rows[selectedCell.row]) {
                      sheet.rows[selectedCell.row][selectedCell.col] = newVal;
                      setDoc({ ...doc });
                      setDirty(true);
                    }
                  }
                }}
              />
            </div>

            {/* Grid */}
            <div className="office-grid-scroll">
              {(() => {
                const activeSheet = doc.sheets?.[activeSheetIndex];
                if (!activeSheet) return null;
                const maxCol = Math.max(activeSheet.max_column || 0, 6);
                return (
                  <table className="office-sheet-grid">
                    <thead>
                      <tr>
                        <th className="corner-header">#</th>
                        {Array.from({ length: maxCol }).map((_, cIdx) => {
                          const colLetter = getExcelColLetter(cIdx);
                          const w = colWidths[cIdx] || 90;
                          return (
                            <th
                              key={cIdx}
                              style={{ width: `${w}px`, minWidth: `${w}px` }}
                              className="office-col-header"
                            >
                              <span>{colLetter}</span>
                              <div
                                className="col-resize-handle"
                                onMouseDown={(e) => handleMouseDownResize(e, cIdx)}
                              />
                            </th>
                          );
                        })}
                      </tr>
                    </thead>
                    <tbody>
                      {activeSheet.rows.map((row, rIdx) => (
                        <tr key={rIdx}>
                          <td className="row-header">{rIdx + 1}</td>
                          {Array.from({ length: maxCol }).map((_, cIdx) => {
                            const val = row[cIdx] !== undefined ? String(row[cIdx]) : "";
                            const colLetter = getExcelColLetter(cIdx);
                            const cellRef = `${colLetter}${rIdx + 1}`;
                            const isSelected = selectedCell?.row === rIdx && selectedCell?.col === cIdx;
                            const isFormula = val.startsWith("=");
                            const style = cellStyles[cellRef] || {};

                            return (
                              <td
                                key={cIdx}
                                className={`grid-cell ${isSelected ? "selected" : ""}`}
                                onClick={() => {
                                  setSelectedCell({ row: rIdx, col: cIdx, ref: cellRef });
                                  setFormulaValue(val);
                                }}
                                onContextMenu={(e) => {
                                  e.preventDefault();
                                  e.stopPropagation();
                                  setSelectedCell({ row: rIdx, col: cIdx, ref: cellRef });
                                  setFormulaValue(val);
                                  setContextMenu({ x: e.clientX, y: e.clientY, row: rIdx, col: cIdx });
                                }}
                              >
                                {isFormula && (
                                  <span className="office-formula-marker" title={`Формула: ${val}`} />
                                )}
                                <input
                                  className="office-cell-inner"
                                  style={{
                                    fontWeight: style.bold ? 700 : undefined,
                                    fontStyle: style.italic ? "italic" : undefined,
                                    textAlign: style.align || (isNaN(Number(val)) || val === "" ? "left" : "right"),
                                  }}
                                  value={val}
                                  onChange={(e) => {
                                    row[cIdx] = e.target.value;
                                    setFormulaValue(e.target.value);
                                    setDoc({ ...doc });
                                    setDirty(true);
                                  }}
                                />
                              </td>
                            );
                          })}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                );
              })()}
            </div>

            {/* Sheets Tabs Bar */}
            <div className="office-sheets-tabs-bar">
              {doc.sheet_names?.map((name, idx) => (
                <button
                  key={name}
                  className={`office-sheet-tab ${idx === activeSheetIndex ? "active" : ""}`}
                  onClick={() => {
                    setActiveSheetIndex(idx);
                    setSelectedCell(null);
                    setFormulaValue("");
                  }}
                >
                  {name}
                </button>
              ))}
              <button
                className="office-btn"
                style={{ padding: "2px 8px", fontSize: "11px" }}
                onClick={() => {
                  const newSheetName = `Sheet${(doc.sheet_names?.length || 0) + 1}`;
                  doc.sheet_names = [...(doc.sheet_names || []), newSheetName];
                  doc.sheets = [
                    ...(doc.sheets || []),
                    {
                      name: newSheetName,
                      max_row: 5,
                      max_column: 4,
                      formula_count: 0,
                      headers: [],
                      rows: [["", "", "", ""], ["", "", "", ""]],
                    },
                  ];
                  setDoc({ ...doc });
                  setActiveSheetIndex(doc.sheet_names.length - 1);
                  setDirty(true);
                }}
              >
                <Plus size={12} />
                <span>Лист</span>
              </button>
            </div>
          </div>
        )}

        {/* 3. PPTX PRESENTATION VIEW */}
        {doc.format === "pptx" && (
          <div className="office-slides-container">
            {/* Left slide thumbnails */}
            <div className="office-slides-strip">
              {doc.slides?.map((slide, idx) => (
                <div
                  key={idx}
                  className={`office-slide-thumb ${idx === activeSlideIndex ? "active" : ""}`}
                  onClick={() => setActiveSlideIndex(idx)}
                >
                  <div className="office-slide-thumb-num">Слайд {idx + 1}</div>
                  <div className="office-slide-thumb-title">{slide.title || "Без заголовка"}</div>
                </div>
              ))}
              <button
                className="office-btn"
                style={{ justifyContent: "center", marginTop: "8px" }}
                onClick={() => {
                  const newSlide = {
                    index: (doc.slides?.length || 0),
                    title: `Новый слайд ${(doc.slides?.length || 0) + 1}`,
                    paragraphs: [],
                    bullets: ["Ключевой тезис слайда"],
                    shape_count: 2,
                    notes: "",
                  };
                  doc.slides = [...(doc.slides || []), newSlide];
                  doc.slide_count = doc.slides.length;
                  setDoc({ ...doc });
                  setActiveSlideIndex(doc.slides.length - 1);
                  setDirty(true);
                }}
              >
                <Plus size={14} />
                <span>Слайд</span>
              </button>
            </div>

            {/* Right slide canvas */}
            <div className="office-slide-canvas-area">
              {doc.slides && doc.slides[activeSlideIndex] && (
                <>
                  <div className="office-slide-stage">
                    <input
                      className="office-slide-title-input"
                      value={doc.slides[activeSlideIndex].title}
                      placeholder="Заголовок слайда"
                      onChange={(e) => {
                        doc.slides![activeSlideIndex].title = e.target.value;
                        setDoc({ ...doc });
                        setDirty(true);
                      }}
                    />

                    <div className="office-slide-bullets-list">
                      {doc.slides[activeSlideIndex].bullets?.map((bullet, bIdx) => (
                        <div key={bIdx} className="office-bullet-item">
                          <span className="office-bullet-dot">•</span>
                          <input
                            className="office-bullet-input"
                            value={bullet}
                            onChange={(e) => {
                              doc.slides![activeSlideIndex].bullets[bIdx] = e.target.value;
                              setDoc({ ...doc });
                              setDirty(true);
                            }}
                          />
                          <button
                            className="icon-button"
                            style={{ padding: "2px" }}
                            title="Удалить пункт"
                            onClick={() => {
                              doc.slides![activeSlideIndex].bullets.splice(bIdx, 1);
                              setDoc({ ...doc });
                              setDirty(true);
                            }}
                          >
                            <Trash size={14} />
                          </button>
                        </div>
                      ))}

                      <button
                        className="office-btn"
                        style={{ alignSelf: "flex-start", marginTop: "8px" }}
                        onClick={() => {
                          doc.slides![activeSlideIndex].bullets.push("Новый пункт");
                          setDoc({ ...doc });
                          setDirty(true);
                        }}
                      >
                        <Plus size={13} />
                        <span>Добавить пункт</span>
                      </button>
                    </div>
                  </div>

                  {/* Speaker notes */}
                  <div className="office-slide-notes-card">
                    <div className="office-slide-notes-title">Заметки докладчика</div>
                    <textarea
                      className="office-slide-notes-input"
                      value={doc.slides[activeSlideIndex].notes || ""}
                      placeholder="Заметки и тезисы для презентации..."
                      onChange={(e) => {
                        doc.slides![activeSlideIndex].notes = e.target.value;
                        setDoc({ ...doc });
                        setDirty(true);
                      }}
                    />
                  </div>
                </>
              )}
            </div>
          </div>
        )}

        {/* 4. PDF VIEW */}
        {doc.format === "pdf" && (
          <iframe
            className="office-pdf-frame"
            src={rawUrl}
            title={doc.file_name}
          />
        )}

        {/* 5. MARKDOWN / CSV / HTML / PLAIN VIEW */}
        {(doc.format === "md" || doc.format === "csv" || doc.format === "html") && (
          <div className="office-paper-scroll">
            <div className="office-paper">
              <pre style={{ whiteSpace: "pre-wrap", fontFamily: "inherit", fontSize: "14px", lineHeight: 1.6 }}>
                {doc.raw_text}
              </pre>
            </div>
          </div>
        )}
      </div>

      {/* Right-click Context Menu */}
      {contextMenu && (
        <div
          className="office-context-menu"
          style={{ top: contextMenu.y, left: contextMenu.x }}
          onClick={(e) => e.stopPropagation()}
        >
          <div className="office-ctx-item" onClick={() => handleContextMenuAction("insert_row_above")}>
            Вставить строку выше
          </div>
          <div className="office-ctx-item" onClick={() => handleContextMenuAction("insert_row_below")}>
            Вставить строку ниже
          </div>
          <div className="office-ctx-item" onClick={() => handleContextMenuAction("insert_col_left")}>
            Вставить столбец слева
          </div>
          <div className="office-ctx-item" onClick={() => handleContextMenuAction("insert_col_right")}>
            Вставить столбец справа
          </div>
          <div className="office-ctx-divider" />
          <div className="office-ctx-item" onClick={() => handleContextMenuAction("delete_row")}>
            Удалить строку {contextMenu.row + 1}
          </div>
          <div className="office-ctx-item" onClick={() => handleContextMenuAction("delete_col")}>
            Удалить столбец {getExcelColLetter(contextMenu.col)}
          </div>
          <div className="office-ctx-divider" />
          <div className="office-ctx-item" onClick={() => handleContextMenuAction("clear_cell")}>
            Очистить содержимое
          </div>
        </div>
      )}

      {/* AI Analysis Modal */}
      {showAnalyzeModal && (
        <div className="office-dialog-backdrop" onClick={() => setShowAnalyzeModal(false)}>
          <div className="office-dialog office-analysis-modal" onClick={(e) => e.stopPropagation()}>
            <div className="office-dialog-header">
              <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                <Sparkle size={18} color="var(--accent)" />
                <h3 style={{ margin: 0 }}>Аналитика таблицы: {analysisData?.sheet_name || "Лист"}</h3>
              </div>
              <button className="office-icon-btn" onClick={() => setShowAnalyzeModal(false)}>
                <X size={16} />
              </button>
            </div>

            {analyzing ? (
              <p className="workspace-notice">Выполняется профилирование датасета и аудит формул…</p>
            ) : analysisData ? (
              <div className="office-analysis-body">
                {/* Stats Summary Chips */}
                <div className="office-stat-chips-row">
                  <div className="office-stat-card">
                    <div className="stat-num">{analysisData.summary.total_rows}</div>
                    <div className="stat-label">Строк данных</div>
                  </div>
                  <div className="office-stat-card">
                    <div className="stat-num">{analysisData.summary.total_columns}</div>
                    <div className="stat-label">Колонок</div>
                  </div>
                  <div className="office-stat-card">
                    <div className="stat-num">{analysisData.formula_audit.total_formulas}</div>
                    <div className="stat-label">Формул</div>
                  </div>
                  <div className={`office-stat-card ${analysisData.formula_audit.error_count > 0 ? "error" : "success"}`}>
                    <div className="stat-num">{analysisData.formula_audit.error_count}</div>
                    <div className="stat-label">Ошибок формул</div>
                  </div>
                </div>

                {/* Formula Error Alert */}
                {analysisData.formula_audit.error_count > 0 && (
                  <div className="office-formula-error-banner">
                    <strong>Обнаружены ошибки формул:</strong>
                    <div className="error-cells-list">
                      {analysisData.formula_audit.errors.map((err, idx) => (
                        <span key={idx} className="error-pill">
                          Ячейка {err.cell}: <code>{err.error}</code> ({err.formula || "нет формулы"})
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                {/* Columns Profile Table */}
                <div className="office-profile-table-wrapper">
                  <h4>Профиль колонок и числовые метрики</h4>
                  <table className="office-profile-table">
                    <thead>
                      <tr>
                        <th>Колонка</th>
                        <th>Тип</th>
                        <th>Уник.</th>
                        <th>Пропусков</th>
                        <th>Мин</th>
                        <th>Макс</th>
                        <th>Среднее</th>
                        <th>Сумма</th>
                      </tr>
                    </thead>
                    <tbody>
                      {analysisData.columns.map((col, idx) => (
                        <tr key={idx}>
                          <td className="col-name">{col.name}</td>
                          <td>
                            <span className={`col-type-tag ${col.type}`}>
                              {col.type === "numeric" ? "Число" : "Текст"}
                            </span>
                          </td>
                          <td>{col.unique_count}</td>
                          <td>{col.null_count}</td>
                          <td>{col.stats?.min !== undefined ? col.stats.min.toLocaleString() : "—"}</td>
                          <td>{col.stats?.max !== undefined ? col.stats.max.toLocaleString() : "—"}</td>
                          <td>{col.stats?.mean !== undefined ? col.stats.mean.toLocaleString() : "—"}</td>
                          <td>{col.stats?.sum !== undefined ? col.stats.sum.toLocaleString() : "—"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            ) : null}
          </div>
        </div>
      )}

      {/* Chart Generator Modal */}
      {showChartModal && doc.sheets?.[activeSheetIndex] && (
        <div className="office-dialog-backdrop" onClick={() => setShowChartModal(false)}>
          <div className="office-dialog office-chart-modal" onClick={(e) => e.stopPropagation()}>
            <div className="office-dialog-header">
              <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                <ChartBar size={18} color="var(--accent)" />
                <h3 style={{ margin: 0 }}>Построение диаграммы</h3>
              </div>
              <button className="office-icon-btn" onClick={() => setShowChartModal(false)}>
                <X size={16} />
              </button>
            </div>

            {(() => {
              const sheet = doc.sheets[activeSheetIndex];
              const maxCol = Math.max(sheet.max_column || 0, sheet.headers?.length || 1);
              const colOptions = Array.from({ length: maxCol }).map((_, idx) => ({
                idx,
                label: `${getExcelColLetter(idx)}: ${sheet.headers?.[idx] || `Колонка ${getExcelColLetter(idx)}`}`,
              }));

              // Extract preview data
              const chartData = sheet.rows.slice(1).map((r, idx) => ({
                label: String(r[chartColX] ?? `Ряд ${idx + 1}`),
                value: parseFloat(String(r[chartColY] ?? 0)) || 0,
              })).filter((d) => !isNaN(d.value)).slice(0, 15);

              const maxValue = Math.max(...chartData.map((d) => d.value), 1);

              return (
                <div className="office-chart-modal-body">
                  {/* Controls */}
                  <div className="chart-controls-grid">
                    <div>
                      <label className="chart-ctrl-label">Тип диаграммы:</label>
                      <div className="chart-type-selector">
                        <button
                          className={`chart-type-btn ${chartType === "bar" ? "active" : ""}`}
                          onClick={() => setChartType("bar")}
                        >
                          <ChartBar size={14} /> Столбчатая
                        </button>
                        <button
                          className={`chart-type-btn ${chartType === "line" ? "active" : ""}`}
                          onClick={() => setChartType("line")}
                        >
                          <ChartLine size={14} /> Линейная
                        </button>
                        <button
                          className={`chart-type-btn ${chartType === "pie" ? "active" : ""}`}
                          onClick={() => setChartType("pie")}
                        >
                          <ChartPie size={14} /> Круговая
                        </button>
                      </div>
                    </div>

                    <div>
                      <label className="chart-ctrl-label">Ось категорий (X):</label>
                      <select
                        value={chartColX}
                        onChange={(e) => setChartColX(Number(e.target.value))}
                      >
                        {colOptions.map((opt) => (
                          <option key={opt.idx} value={opt.idx}>{opt.label}</option>
                        ))}
                      </select>
                    </div>

                    <div>
                      <label className="chart-ctrl-label">Ось значений (Y):</label>
                      <select
                        value={chartColY}
                        onChange={(e) => setChartColY(Number(e.target.value))}
                      >
                        {colOptions.map((opt) => (
                          <option key={opt.idx} value={opt.idx}>{opt.label}</option>
                        ))}
                      </select>
                    </div>

                    <div>
                      <label className="chart-ctrl-label">Заголовок графика:</label>
                      <input
                        className="office-formula-input"
                        placeholder="Например, Динамика выручки"
                        value={chartTitle}
                        onChange={(e) => setChartTitle(e.target.value)}
                      />
                    </div>
                  </div>

                  {/* SVG Chart Preview */}
                  <div className="chart-preview-stage">
                    <svg viewBox="0 0 540 220" className="office-chart-svg">
                      {/* Grid lines */}
                      <line x1="40" y1="20" x2="520" y2="20" stroke="var(--border)" strokeDasharray="3 3" />
                      <line x1="40" y1="90" x2="520" y2="90" stroke="var(--border)" strokeDasharray="3 3" />
                      <line x1="40" y1="160" x2="520" y2="160" stroke="var(--border)" />

                      {chartType === "bar" && (
                        chartData.map((d, idx) => {
                          const barWidth = Math.max(16, Math.min(40, 440 / (chartData.length * 1.5)));
                          const gap = 440 / chartData.length;
                          const x = 50 + idx * gap;
                          const barHeight = Math.max(4, (d.value / maxValue) * 130);
                          const y = 160 - barHeight;

                          return (
                            <g key={idx}>
                              <rect
                                x={x}
                                y={y}
                                width={barWidth}
                                height={barHeight}
                                fill="var(--accent)"
                                rx="3"
                              />
                              <text
                                x={x + barWidth / 2}
                                y={y - 5}
                                textAnchor="middle"
                                fontSize="10"
                                fill="var(--text)"
                              >
                                {d.value}
                              </text>
                              <text
                                x={x + barWidth / 2}
                                y="175"
                                textAnchor="middle"
                                fontSize="9"
                                fill="var(--muted)"
                              >
                                {d.label.slice(0, 8)}
                              </text>
                            </g>
                          );
                        })
                      )}

                      {chartType === "line" && (
                        <>
                          <polyline
                            fill="none"
                            stroke="var(--accent)"
                            strokeWidth="3"
                            points={chartData.map((d, idx) => {
                              const gap = 440 / (chartData.length || 1);
                              const x = 50 + idx * gap;
                              const y = 160 - Math.max(4, (d.value / maxValue) * 130);
                              return `${x},${y}`;
                            }).join(" ")}
                          />
                          {chartData.map((d, idx) => {
                            const gap = 440 / (chartData.length || 1);
                            const x = 50 + idx * gap;
                            const y = 160 - Math.max(4, (d.value / maxValue) * 130);
                            return (
                              <g key={idx}>
                                <circle cx={x} cy={y} r="4" fill="var(--surface)" stroke="var(--accent)" strokeWidth="2" />
                                <text x={x} y={y - 8} textAnchor="middle" fontSize="10" fill="var(--text)">
                                  {d.value}
                                </text>
                                <text x={x} y="175" textAnchor="middle" fontSize="9" fill="var(--muted)">
                                  {d.label.slice(0, 8)}
                                </text>
                              </g>
                            );
                          })}
                        </>
                      )}

                      {chartType === "pie" && (
                        <g transform="translate(270, 95)">
                          {(() => {
                            const total = chartData.reduce((acc, curr) => acc + curr.value, 0) || 1;
                            let cumulativeAngle = 0;
                            const colors = ["#3b82f6", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6", "#ec4899", "#06b6d4"];

                            return chartData.map((d, idx) => {
                              const sliceAngle = (d.value / total) * 2 * Math.PI;
                              const x1 = 65 * Math.cos(cumulativeAngle);
                              const y1 = 65 * Math.sin(cumulativeAngle);
                              const x2 = 65 * Math.cos(cumulativeAngle + sliceAngle);
                              const y2 = 65 * Math.sin(cumulativeAngle + sliceAngle);
                              const largeArc = sliceAngle > Math.PI ? 1 : 0;
                              const pathData = `M 0 0 L ${x1} ${y1} A 65 65 0 ${largeArc} 1 ${x2} ${y2} Z`;
                              cumulativeAngle += sliceAngle;

                              return (
                                <path
                                  key={idx}
                                  d={pathData}
                                  fill={colors[idx % colors.length]}
                                  stroke="var(--paper)"
                                  strokeWidth="1.5"
                                />
                              );
                            });
                          })()}
                        </g>
                      )}
                    </svg>
                  </div>

                  {/* Actions */}
                  <div style={{ display: "flex", justifyContent: "flex-end", gap: "8px", marginTop: "12px" }}>
                    <button className="office-btn" onClick={() => setShowChartModal(false)}>
                      Отмена
                    </button>
                    <button
                      className="office-btn office-btn-primary"
                      disabled={embeddingChart}
                      onClick={handleEmbedChart}
                    >
                      <Plus size={14} />
                      <span>{embeddingChart ? "Встраиваем…" : "Встроить график в Excel"}</span>
                    </button>
                  </div>
                </div>
              );
            })()}
          </div>
        </div>
      )}

      {/* Convert Dialog Modal */}
      {showConvertModal && (
        <div className="office-dialog-backdrop" onClick={() => setShowConvertModal(false)}>
          <div className="office-dialog" onClick={(e) => e.stopPropagation()}>
            <h3>Конвертировать документ</h3>
            <p style={{ fontSize: "13px", color: "var(--muted)", margin: 0 }}>
              Преобразовать {doc.file_name} в другой рабочий формат:
            </p>
            <select
              value={targetFormat}
              onChange={(e) => setTargetFormat(e.target.value)}
            >
              {doc.format === "docx" && <option value="md">Markdown (.md)</option>}
              {doc.format === "xlsx" && <option value="csv">Таблица CSV (.csv)</option>}
              {doc.format === "pdf" && <option value="docx">Документ Word (.docx)</option>}
              {doc.format === "md" && <option value="docx">Документ Word (.docx)</option>}
              {doc.format === "csv" && <option value="xlsx">Книга Excel (.xlsx)</option>}
            </select>

            <div style={{ display: "flex", justifyContent: "flex-end", gap: "8px", marginTop: "12px" }}>
              <button className="office-btn" onClick={() => setShowConvertModal(false)}>
                Отмена
              </button>
              <button
                className="office-btn office-btn-primary"
                disabled={converting}
                onClick={handleConvert}
              >
                {converting ? "Конвертация…" : "Выполнить"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
