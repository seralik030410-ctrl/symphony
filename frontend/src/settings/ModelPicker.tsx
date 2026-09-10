import { Cpu } from "@phosphor-icons/react";

import type { ModelProfile, Session } from "../types";
import { CustomSelect } from "../ui/CustomSelect";

interface ModelPickerProps {
  session: Session;
  profiles: ModelProfile[];
  disabled: boolean;
  onChange: (provider: "ollama" | "openai", model: string, profileId: string) => void;
}

export function ModelPicker({ session, profiles, disabled, onChange }: ModelPickerProps) {
  const values = profiles.flatMap((profile) =>
    profile.models.map((model) => ({
      provider: profile.provider,
      profileId: profile.profile_id,
      model,
      label: model,
      description: profile.available ? profile.title : `${profile.title} · недоступен`,
      group: profile.title,
      unavailable: !profile.available || !profile.enabled,
    })),
  );
  const currentProfile = session.provider_profile_id ?? (session.provider === "ollama" ? "builtin-ollama" : "builtin-openai");
  const currentValue = `${currentProfile}:${session.model}`;
  if (!values.some((value) => `${value.profileId}:${value.model}` === currentValue)) {
    values.unshift({
      provider: session.provider as "ollama" | "openai",
      profileId: currentProfile,
      model: session.model,
      label: session.model,
      description: `${session.provider} · текущий профиль`,
      group: session.provider,
      unavailable: false,
    });
  }
  return (
    <CustomSelect
      className="model-picker"
      ariaLabel="Выберите модель"
      value={currentValue}
      disabled={disabled}
      icon={<Cpu size={17} weight="fill" aria-hidden="true" />}
      options={values.map((value) => ({
        value: `${value.profileId}:${value.model}`,
        label: value.label,
        description: value.description,
        group: value.group,
        unavailable: value.unavailable,
      }))}
      onChange={(nextValue) => {
        const separator = nextValue.indexOf(":");
        const profileId = nextValue.slice(0, separator);
        const model = nextValue.slice(separator + 1);
        const item = values.find(value => value.profileId === profileId && value.model === model);
        if (item) onChange(item.provider, item.model, item.profileId);
      }}
    />
  );
}
