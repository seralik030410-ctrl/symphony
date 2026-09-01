import { useSyncExternalStore } from "react";
import { Monitor } from "@phosphor-icons/react";
import { initializeTheme, parseTheme } from "../theme";
import { CustomSelect } from "../ui/CustomSelect";

export function AppearanceSettings() {
  const theme = initializeTheme();
  const preference = useSyncExternalStore(theme.subscribe, theme.getSnapshot, () => "system");
  return <><h2>Внешний вид</h2><section className="settings-card">
    <div className="settings-row"><div><strong>Тема интерфейса</strong><small>Системная тема следует настройкам устройства. Документы и сайты в preview не перекрашиваются.</small></div>
      <CustomSelect ariaLabel="Тема интерфейса" value={preference} icon={<Monitor size={17} />} options={[
        { value: "system", label: "Системная" }, { value: "light", label: "Светлая" }, { value: "dark", label: "Тёмная" },
      ]} onChange={value => theme.set(parseTheme(value))} />
    </div>
  </section></>;
}
