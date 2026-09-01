import { describe, expect, it, vi } from "vitest";
import { uploadDroppedBatch } from "./desktop";

const files = [{ token: "a", name: "a.txt" }, { token: "b", name: "b.txt" }];
const native = { filename: "a.txt", content_base64: "YQ==" };

describe("native drop batching", () => {
  it("continues after adding the first attachment changes UI state", async () => {
    const attachments: string[] = [];
    const consume = vi.fn(async (token: string) => ({ ...native, filename: token }));
    await uploadDroppedBatch(files, {
      isCurrent: () => true, consume,
      upload: async file => file.filename,
      append: item => attachments.push(item),
    });
    expect(attachments).toEqual(["a", "b"]);
    expect(consume).toHaveBeenCalledTimes(2);
  });

  it("does not upload after switching chats during native file read", async () => {
    let current = true;
    const upload = vi.fn(); const append = vi.fn();
    await uploadDroppedBatch(files, {
      isCurrent: () => current,
      consume: async () => { current = false; return native; },
      upload, append,
    });
    expect(upload).not.toHaveBeenCalled();
    expect(append).not.toHaveBeenCalled();
  });

  it("does not append an old chat's result or consume the next file", async () => {
    let current = true;
    const consume = vi.fn(async () => native); const append = vi.fn();
    await uploadDroppedBatch(files, {
      isCurrent: () => current, consume,
      upload: async () => { current = false; return "old-chat-attachment"; }, append,
    });
    expect(consume).toHaveBeenCalledTimes(1);
    expect(append).not.toHaveBeenCalled();
  });

  it("reports failures and does not silently continue", async () => {
    const consume = vi.fn(async () => { throw new Error("File expired"); });
    await expect(uploadDroppedBatch(files, { isCurrent: () => true, consume, upload: vi.fn(), append: vi.fn() })).rejects.toThrow("File expired");
    expect(consume).toHaveBeenCalledTimes(1);
  });
});
