import { Cpu } from "@phosphor-icons/react";

import type { ModelProfile, Session } from "../types";
import { CustomSelect } from "../ui/CustomSelect";

interface ModelPickerProps {
  session: Session;
  profiles: ModelProfile[];
  disabled: boolean;
  onChange: (provider: "ollama" | "openai", model: string) => void;
}

export function ModelPicker({ session, profiles, disabled, onChange }: ModelPickerProps) {
  const values = profiles.flatMap((profile) =>
    profile.models.map((model) => ({
      provider: profile.provider,
      model,
      label: model,
      description: profile.available ? profile.title : `${profile.title} · недоступен`,
      group: profile.title,
      unavailable: !profile.available,
    })),
  );
  const currentValue = `${session.provider}:${session.model}`;
  if (!values.some((value) => `${value.provider}:${value.model}` === currentValue)) {
    values.unshift({
      provider: session.provider as "ollama" | "openai",
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
        value: `${value.provider}:${value.model}`,
        label: value.label,
        description: value.description,
        group: value.group,
        unavailable: value.unavailable,
      }))}
      onChange={(nextValue) => {
        const separator = nextValue.indexOf(":");
        onChange(
          nextValue.slice(0, separator) as "ollama" | "openai",
          nextValue.slice(separator + 1),
        );
      }}
    />
  );
}
