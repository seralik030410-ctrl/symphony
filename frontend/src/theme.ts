export type ThemePreference = "system" | "light" | "dark";
export type ResolvedTheme = Exclude<ThemePreference, "system">;
export const THEME_KEY = "symphony.theme";

export function parseTheme(value: unknown): ThemePreference {
  return value === "light" || value === "dark" ? value : "system";
}

export interface ThemeEnvironment {
  read(): string | null;
  write(value: ThemePreference): void;
  systemDark(): boolean;
  watchSystem(callback: () => void): () => void;
  watchStorage(callback: (value: string | null) => void): () => void;
  apply(theme: ResolvedTheme): void;
}

/** Application preference, not chat state. A blocked storage must not break startup. */
export function createThemeStore(environment: ThemeEnvironment) {
  let preference: ThemePreference = "system";
  try { preference = parseTheme(environment.read()); } catch { /* private webview */ }
  const listeners = new Set<() => void>();
  const apply = () => environment.apply(preference === "system"
    ? environment.systemDark() ? "dark" : "light" : preference);
  const update = (value: ThemePreference) => {
    const changed = preference !== value;
    preference = value;
    apply();
    if (changed) listeners.forEach(listener => listener());
  };
  apply();
  const stopSystem = environment.watchSystem(() => { if (preference === "system") apply(); });
  const stopStorage = environment.watchStorage(value => update(parseTheme(value)));
  return {
    getSnapshot: () => preference,
    subscribe: (listener: () => void) => { listeners.add(listener); return () => { listeners.delete(listener); }; },
    set: (value: ThemePreference) => {
      update(parseTheme(value));
      try { environment.write(preference); } catch { /* preference still works for this window */ }
    },
    dispose: () => { stopSystem(); stopStorage(); listeners.clear(); },
  };
}

let store: ReturnType<typeof createThemeStore> | undefined;
export function initializeTheme() {
  if (store) return store;
  const media = window.matchMedia("(prefers-color-scheme: dark)");
  store = createThemeStore({
    read: () => localStorage.getItem(THEME_KEY),
    write: value => localStorage.setItem(THEME_KEY, value),
    systemDark: () => media.matches,
    watchSystem: callback => {
      media.addEventListener("change", callback);
      return () => media.removeEventListener("change", callback);
    },
    watchStorage: callback => {
      const listener = (event: StorageEvent) => {
        if (event.key === THEME_KEY || event.key === null) callback(event.newValue);
      };
      window.addEventListener("storage", listener);
      return () => window.removeEventListener("storage", listener);
    },
    apply: theme => {
      document.documentElement.dataset.theme = theme;
      document.documentElement.style.colorScheme = theme;
      document.querySelector('meta[name="theme-color"]')?.setAttribute("content", theme === "dark" ? "#14171b" : "#f3f5f7");
    },
  });
  return store;
}
