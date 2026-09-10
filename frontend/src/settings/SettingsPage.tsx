import { ArrowLeft, Brain, ChatCircle, Cloud, Gear, Globe, Images, Microphone, Package, ShieldCheck, TreeStructure, Gauge, X } from "@phosphor-icons/react";
import { useState } from "react";
import type { ModelProfile, Session } from "../types";
import { CustomSelect } from "../ui/CustomSelect";
import { AppearanceSettings } from "./AppearanceSettings";
import { ContextSettings } from "./ContextSettings";
import { DesktopSettings } from "./DesktopSettings";
import { DiagnosticsSettings } from "./DiagnosticsSettings";
import { ModelPicker } from "./ModelPicker";
import { ProvidersSettings } from "./ProvidersSettings";
import { ResearchSettings } from "./ResearchSettings";
import { SkillsSettings } from "./SkillsSettings";
import { MediaWorkspace } from "../media/MediaWorkspace";
import { VoiceSettings } from "../voice/VoiceSettings";
import { VisionSettings } from "../vision/VisionSettings";
import { AgentSettings } from "../agents/AgentSettings";
import { PerformanceSettings } from "./PerformanceSettings";
import { api } from "../api";

type Section = "general" | "context" | "research" | "providers" | "skills" | "media" | "voice" | "vision" | "performance" | "agents";

export function SettingsPage({ session, profiles, active, onPolicy, onModel, onClose, onSessionSaved, onProvidersChanged }: {
  session: Session | null; profiles: ModelProfile[]; active: boolean;
  onPolicy: (value: Session["policy_profile"]) => void;
  onModel: (provider: "ollama" | "openai", model: string, profileId: string) => void;
  onClose: () => void; onSessionSaved: (session: Session) => void;
  onProvidersChanged: () => void;
}) {
  const [section, setSection] = useState<Section>("general");
  return <main className="settings-page">
    <aside className="settings-nav">
      <button className="settings-back" onClick={onClose}><ArrowLeft size={18} /> Вернуться в приложение</button><strong>Настройки</strong>
      <nav aria-label="Разделы настроек">
        <button aria-current={section === "general" ? "page" : undefined} onClick={() => setSection("general")}><Gear size={17} /> Общее</button>
        <button aria-current={section === "context" ? "page" : undefined} onClick={() => setSection("context")}><Brain size={17} /> Контекст и память</button>
        <button aria-current={section === "research" ? "page" : undefined} onClick={() => setSection("research")}><Globe size={17} /> Интернет</button>
        <button aria-current={section === "providers" ? "page" : undefined} onClick={() => setSection("providers")}><Cloud size={17} /> Провайдеры</button>
        <button aria-current={section === "skills" ? "page" : undefined} onClick={() => setSection("skills")}><Package size={17} /> Навыки</button>
        <button aria-current={section === "media" ? "page" : undefined} onClick={() => setSection("media")}><Images size={17} /> Медиа</button>
        <button aria-current={section === "voice" ? "page" : undefined} onClick={() => setSection("voice")}><Microphone size={17} /> Голос</button>
        <button aria-current={section === "vision" ? "page" : undefined} onClick={() => setSection("vision")}><Images size={17} /> Vision</button>
        <button aria-current={section === "performance" ? "page" : undefined} onClick={() => setSection("performance")}><Gauge size={17} /> Производительность</button>
        <button aria-current={section === "agents" ? "page" : undefined} onClick={() => setSection("agents")}><TreeStructure size={17} /> Субагенты</button>
      </nav><small>FinCtrl 3.0 · мультимодальный runtime</small>
    </aside>
    <div className="settings-main"><button className="settings-mobile-close icon-button" aria-label="Закрыть настройки" onClick={onClose}><X size={19} /></button>
      {section === "agents" ? <AgentSettings />
        : section === "performance" ? <PerformanceSettings load={api.resourceSettings} save={api.updateResourceSettings} />
        : section === "vision" ? <VisionSettings session={session} active={active} />
        : section === "voice" ? <VoiceSettings session={session} />
        : section === "media" ? <MediaWorkspace session={session} />
        : section === "skills" ? <SkillsSettings />
        : section === "providers" ? <ProvidersSettings onChanged={onProvidersChanged} />
        : section === "context" ? <ContextSettings key={`${session?.id}:${session?.provider}:${session?.model}`} session={session} active={active} onSessionSaved={onSessionSaved} />
        : section === "research" ? <ResearchSettings key={session?.id} session={session} active={active} />
        : <section className="general-settings"><header className="settings-content-header"><div><h1>Общее</h1><p>Настройки текущего локального чата и runtime.</p></div></header>
          <AppearanceSettings /><h2>Текущий чат</h2><section className="settings-card">
            <div className="settings-row"><div><strong>Разрешения</strong><small>Изменения блокируются во время активного turn.</small></div>{session ? <CustomSelect ariaLabel="Разрешения текущего чата" value={session.policy_profile} disabled={active} icon={<ShieldCheck size={17} />} options={[
              { value: "read_only", label: "Только чтение", description: "Записи — с разрешения" }, { value: "project_edit", label: "Правка проекта", description: "Команды — спросить" }, { value: "build", label: "Сборка", description: "Локальные тесты и build" }, { value: "full_manual", label: "Ручной контроль", description: "Подтверждать изменения" },
            ]} onChange={value => onPolicy(value as Session["policy_profile"])} /> : <span>Нет чата</span>}</div>
            <div className="settings-row"><div><strong>Модель</strong><small>Обычный разговор идёт напрямую выбранному provider.</small></div>{session ? <ModelPicker session={session} profiles={profiles} disabled={active} onChange={onModel} /> : <span>Нет чата</span>}</div>
          </section><DesktopSettings />
          <h2>Runtime</h2><section className="settings-card"><div className="settings-row"><div><strong>Локальный адрес</strong><small>Frontend и API используют один порт.</small></div><code>127.0.0.1:8765</code></div><div className="settings-row"><div><strong>Изоляция контекста</strong><small>История, project workspace и вкладки разделены по chat id.</small></div><span><ChatCircle size={17} /> Включена</span></div></section><DiagnosticsSettings />
        </section>}
    </div>
  </main>;
}
