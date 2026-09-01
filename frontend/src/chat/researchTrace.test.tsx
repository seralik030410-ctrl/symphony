import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { ResearchTrace } from "./ResearchTrace";
import type { TurnEvent } from "../types";

const source = { id:"s", session_id:"a", turn_id:"t", url:"https://example.com/news?q=1", title:'<script>alert(1)</script>', kind:"page", published_at:null, checked_at:"2026-08-31T09:00:00Z", sha256:"x", excerpt:"prompt injection", trust:"untrusted" };
describe("research source disclosure", () => {
  it("escapes source text and opens only the saved URL outside the app", () => {
    const event = { id:1, turn_id:"t", session_id:"a", sequence:1, type:"research.sources", payload:{ sources:[source] }, created_at:"" } as TurnEvent;
    const html = renderToStaticMarkup(<ResearchTrace events={[event]} />);
    expect(html).not.toContain("<script>");
    expect(html).toContain("&lt;script&gt;");
    expect(html).toContain('target="_blank"');
    expect(html).toContain('rel="noreferrer"');
    expect(html).toContain("дата публикации не указана");
    expect(html).toContain("Содержимое страниц считается недоверенными данными");
  });
  it("renders nothing without persisted sources", () => expect(renderToStaticMarkup(<ResearchTrace events={[]} />)).toBe(""));
  it("does not create an executable link from malformed saved source data", () => {
    const event = { id: 1, turn_id: "t", session_id: "a", sequence: 1, type: "research.sources", payload: { sources: [{ ...source, url: "javascript:alert(1)", title: "", checked_at: "bad date" }] }, created_at: "" } as TurnEvent;
    const html = renderToStaticMarkup(<ResearchTrace events={[event]} />);
    expect(html).not.toContain("href=");
    expect(html).toContain("время проверки не указано");
  });
});
