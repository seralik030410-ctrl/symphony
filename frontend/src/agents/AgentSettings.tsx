import { useEffect, useState } from "react";
import { api } from "../api";
import type { AgentRole, AgentSettings as Settings, ProviderProfile } from "../types";
import { CustomSelect } from "../ui/CustomSelect";
import "./agents.css";

const roles: Array<{ id: AgentRole; title: string; hint: string }> = [
  { id: "orchestrator", title: "Оркестратор", hint: "Разбивает запрос и управляет другими агентами" },
  { id: "code", title: "Код", hint: "Пишет и изменяет проект" },
  { id: "research", title: "Исследование", hint: "Ищет и сопоставляет источники" },
  { id: "vision", title: "Vision", hint: "Разбирает изображения и кадры" },
  { id: "media", title: "Медиа", hint: "Готовит image/video задачи" },
  { id: "review", title: "Проверка", hint: "Проверяет решения и изменения" },
  { id: "worker", title: "Обычный исполнитель", hint: "Маршрут для задач без специальной роли" },
];

export function AgentSettings() {
  const [settings, setSettings] = useState<Settings | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [providers, setProviders] = useState<ProviderProfile[]>([]);
  const [routesDirty, setRoutesDirty] = useState(false);
  useEffect(() => { void Promise.all([api.agentSettings(), api.listProviderProfiles()]).then(([value, items]) => { setSettings(value); setProviders(items.filter(item => item.enabled)); }).catch(error => setError(String(error))); }, []);
  if (!settings) return <section><header className="settings-content-header"><div><h1>Субагенты</h1><p>{error ?? "Загрузка настроек…"}</p></div></header></section>;
  const save = async (next: Settings) => { setSaving(true); setError(null); try { setSettings(await api.updateAgentSettings(next)); setRoutesDirty(false); } catch (error) { setError(String(error)); } finally { setSaving(false); } };
  const routesInvalid = Object.values(settings.role_routes).some(item => !item?.model.trim());
  const route = (role: AgentRole, providerId: string) => {
    const profile = providers.find(item => item.id === providerId);
    const nextRoutes = { ...settings.role_routes };
    if (!profile) delete nextRoutes[role];
    else nextRoutes[role] = { provider_profile_id: profile.id,
      model: nextRoutes[role]?.provider_profile_id === profile.id ? nextRoutes[role]?.model || profile.default_model : profile.default_model };
    setSettings({ ...settings, role_routes: nextRoutes }); setRoutesDirty(true);
  };
  const limits = settings.effective_limits;
  return <section><header className="settings-content-header"><div><h1>Субагенты</h1><p>Изолированные исполнители с общим контролем ресурсов и разрешений.</p></div></header>
    {error ? <p className="settings-error">{error}</p> : null}<section className="settings-card">
      <div className="settings-row"><div><strong>Оркестрация</strong><small>Обычный чат работает и при выключенной функции.</small></div>
        <button className={settings.enabled ? "primary-button" : "text-button"} disabled={saving || routesInvalid} onClick={() => void save({ ...settings, enabled: !settings.enabled })}>{settings.enabled ? "Включена" : "Выключена"}</button></div>
      <div className="settings-row"><div><strong>Профиль мощности</strong><small>Maximum рассчитан на сервер и модели до 200B.</small></div>
        <CustomSelect ariaLabel="Профиль субагентов" value={settings.profile} disabled={saving || routesInvalid} options={[
          { value: "conservative", label: "Conservative", description: "1 исполнитель · 16 задач" },
          { value: "balanced", label: "Balanced", description: "4 исполнителя · 64 задачи" },
          { value: "maximum", label: "Maximum", description: "32 исполнителя · 512 задач" },
        ]} onChange={profile => void save({ ...settings, profile: profile as Settings["profile"], overrides: {} })} /></div>
      <div className="settings-row"><div><strong>Ленивая выдача инструментов</strong><small>Маленькая модель получает базовый набор и подключает специальные инструменты через поиск по мере необходимости.</small></div>
        <button className={settings.lazy_tools_enabled ? "primary-button" : "text-button"} disabled={saving || routesInvalid} onClick={() => void save({ ...settings, lazy_tools_enabled: !settings.lazy_tools_enabled })}>{settings.lazy_tools_enabled ? "Включена" : "Выключена"}</button></div>
    </section><details className="settings-card agent-routes"><summary><span><strong>Модели по ролям</strong><small>Необязательные маршруты только для субагентов. Основной чат не переключается.</small></span><span>{Object.keys(settings.role_routes).length} настроено</span></summary>
      <div className="agent-route-list">{roles.map(item => { const current = settings.role_routes[item.id]; return <div className="agent-route" key={item.id}><div><strong>{item.title}</strong><small>{item.hint}</small></div><label><span>Провайдер</span><select aria-label={`Провайдер для роли ${item.title}`} value={current?.provider_profile_id ?? ""} disabled={saving} onChange={event => route(item.id, event.target.value)}><option value="">Как в чате</option>{providers.map(profile => <option value={profile.id} key={profile.id}>{profile.title}</option>)}</select></label><label><span>Модель</span><input aria-label={`Модель для роли ${item.title}`} value={current?.model ?? ""} disabled={saving || !current} maxLength={200} placeholder="Наследуется" onChange={event => { setSettings({ ...settings, role_routes: { ...settings.role_routes, [item.id]: { ...current!, model: event.target.value } } }); setRoutesDirty(true); }} /></label></div>; })}</div>
      <footer><button className="settings-primary" disabled={saving || !routesDirty || routesInvalid} onClick={() => void save(settings)}>{saving ? "Сохраняем…" : "Сохранить маршруты"}</button></footer>
    </details><h2>Действующие пределы</h2><section className="settings-card agent-limit-grid">
      <div><small>Одновременно</small><strong>{limits.max_concurrent}</strong></div><div><small>Глубина</small><strong>{limits.max_depth}</strong></div>
      <div><small>Детей за вызов</small><strong>{limits.max_children}</strong></div><div><small>Задач в дереве</small><strong>{limits.max_tasks_per_tree}</strong></div>
      <div><small>Шагов на задачу</small><strong>{limits.max_steps}</strong></div><div><small>Инструментов</small><strong>{limits.max_tool_calls}</strong></div>
    </section></section>;
}
