export interface NativeDrop {
  token: string;
  name: string;
}

export interface NativeFile {
  filename: string;
  content_base64: string;
}

export function hasDesktopBridge() {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}

export async function desktopInvoke<T>(command: string, args?: Record<string, unknown>): Promise<T> {
  if (!hasDesktopBridge()) throw new Error("Эта настройка доступна только в установленном приложении");
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<T>(command, args);
}

export async function listenNativeDrops(handler: (files: NativeDrop[]) => void | Promise<void>, onError: (message: string) => void) {
  if (!hasDesktopBridge()) return () => undefined;
  const { listen } = await import("@tauri-apps/api/event");
  const unlisten = await listen<NativeDrop[]>("symphony://native-file-drop", event => { void Promise.resolve(handler(event.payload)).catch(error => onError(String(error))); });
  try {
    const unlistenError = await listen<string>("symphony://drop-error", event => onError(event.payload));
    return () => { unlisten(); unlistenError(); };
  } catch (error) { unlisten(); throw error; }
}

/** Stop at async boundaries when the user leaves the receiving chat. */
export async function uploadDroppedBatch<T>(files: NativeDrop[], options: {
  isCurrent: () => boolean;
  consume: (token: string) => Promise<NativeFile>;
  upload: (file: NativeFile) => Promise<T>;
  append: (attachment: T) => void;
}) {
  for (const item of files) {
    if (!options.isCurrent()) return;
    const file = await options.consume(item.token);
    if (!options.isCurrent()) return;
    const attachment = await options.upload(file);
    if (!options.isCurrent()) return;
    options.append(attachment);
  }
}

export async function openExternal(url: string) {
  const parsed = new URL(url);
  if (parsed.protocol !== "https:") throw new Error("Разрешены только HTTPS-ссылки");
  const { openUrl } = await import("@tauri-apps/plugin-opener");
  await openUrl(parsed.href);
}
