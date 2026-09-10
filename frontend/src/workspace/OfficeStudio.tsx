import { useState, useEffect } from "react";
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
} from "@phosphor-icons/react";
import { api, type OfficeDocument } from "../api";
import "./OfficeStudio.css";

interface OfficeStudioProps {
  sessionId: string;
  path: string;
  revision: number;
  onClose?: () => void;
  onOpenAnother?: (newPath: string) => void;
}

export function OfficeStudio({ sessionId, path, revision, onOpenAnother }: OfficeStudioProps) {
  const [doc, setDoc] = useState<OfficeDocument | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [toast, setToast] = useState<string | null>(null);

  // Active sub-navigation (e.g. active sheet or active slide)
  const [activeSheetIndex, setActiveSheetIndex] = useState(0);
  const [activeSlideIndex, setActiveSlideIndex] = useState(0);

  // Active cell in spreadsheet
  const [selectedCell, setSelectedCell] = useState<{ row: number; col: number; ref: string } | null>(null);
  const [formulaValue, setFormulaValue] = useState("");

  // Convert modal
  const [showConvertModal, setShowConvertModal] = useState(false);
  const [targetFormat, setTargetFormat] = useState("docx");
  const [converting, setConverting] = useState(false);

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
    setTimeout(() => setToast(null), 3000);
  };

  // Save handler
  const handleSave = async () => {
    if (!doc) return;
    setSaving(true);
    try {
      if (doc.format === "docx") {
        // Collect paragraph updates
        const paragraph_updates = doc.paragraphs?.map((p) => ({
          index: p.index,
          text: p.text,
        }));
        // Collect table updates
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
          const res = await api.officeSave(sessionId, {
            path,
            format: "xlsx",
            cell_updates,
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

  return (
    <div className="office-studio">
      {/* Top Toolbar */}
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
                if (p.is_heading) return null; // already shown above
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

        {/* 2. XLSX SPREADSHEET VIEW */}
        {doc.format === "xlsx" && (
          <div className="office-spreadsheet-container">
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
                const maxCol = Math.max(activeSheet.max_column, 6);
                return (
                  <table className="office-sheet-grid">
                    <thead>
                      <tr>
                        <th className="corner-header">#</th>
                        {Array.from({ length: maxCol }).map((_, cIdx) => (
                          <th key={cIdx}>{String.fromCharCode(65 + cIdx)}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {activeSheet.rows.map((row, rIdx) => (
                        <tr key={rIdx}>
                          <td className="row-header">{rIdx + 1}</td>
                          {Array.from({ length: maxCol }).map((_, cIdx) => {
                            const val = row[cIdx] !== undefined ? String(row[cIdx]) : "";
                            const colLetter = String.fromCharCode(65 + cIdx);
                            const cellRef = `${colLetter}${rIdx + 1}`;
                            const isSelected = selectedCell?.row === rIdx && selectedCell?.col === cIdx;
                            return (
                              <td
                                key={cIdx}
                                className={`grid-cell ${isSelected ? "selected" : ""}`}
                                onClick={() => {
                                  setSelectedCell({ row: rIdx, col: cIdx, ref: cellRef });
                                  setFormulaValue(val);
                                }}
                              >
                                <input
                                  className="office-cell-inner"
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
              {doc.format === "docx" && (
                <>
                  <option value="md">Markdown (.md)</option>
                </>
              )}
              {doc.format === "xlsx" && (
                <>
                  <option value="csv">Таблица CSV (.csv)</option>
                </>
              )}
              {doc.format === "pdf" && (
                <>
                  <option value="docx">Документ Word (.docx)</option>
                </>
              )}
              {doc.format === "md" && (
                <>
                  <option value="docx">Документ Word (.docx)</option>
                </>
              )}
              {doc.format === "csv" && (
                <>
                  <option value="xlsx">Книга Excel (.xlsx)</option>
                </>
              )}
            </select>

            <div style={{ display: "flex", justifyContent: "flex-end", gap: "8px", marginTop: "12px" }}>
              <button
                className="office-btn"
                onClick={() => setShowConvertModal(false)}
              >
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
