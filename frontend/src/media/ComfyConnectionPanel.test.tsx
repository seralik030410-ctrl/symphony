import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { ComfyConnectionPanel } from "./MediaWorkspace";

describe("ComfyUI connection guidance", () => {
  it("explains the local connection before asking for technical settings", () => {
    const html = renderToStaticMarkup(
      <ComfyConnectionPanel
        origin="http://127.0.0.1:8188"
        allowPrivate={true}
        busy={false}
        onOriginChange={() => {}}
        onAllowPrivateChange={() => {}}
        onConnect={() => {}}
      />,
    );

    expect(html).toContain("Запустите ComfyUI");
    expect(html).toContain("127.0.0.1:8188");
    expect(html).toContain("Проверить и подключить");
    expect(html).toContain("Дополнительные настройки");
  });
});
