import { CaretDown, Check } from "@phosphor-icons/react";
import {
  type KeyboardEvent,
  type ReactNode,
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
} from "react";

export interface CustomSelectOption {
  value: string;
  label: string;
  description?: string;
  group?: string;
  unavailable?: boolean;
}

interface CustomSelectProps {
  ariaLabel: string;
  value: string;
  options: CustomSelectOption[];
  disabled?: boolean;
  icon?: ReactNode;
  className?: string;
  onChange: (value: string) => void;
}

export function CustomSelect({
  ariaLabel,
  value,
  options,
  disabled = false,
  icon,
  className = "",
  onChange,
}: CustomSelectProps) {
  const listboxId = useId();
  const rootRef = useRef<HTMLDivElement | null>(null);
  const typeaheadRef = useRef("");
  const typeaheadTimer = useRef<number | null>(null);
  const selectedIndex = Math.max(0, options.findIndex((option) => option.value === value));
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(selectedIndex);
  const selected = options[selectedIndex];

  const groups = useMemo(() => {
    const result: Array<{ name?: string; options: Array<CustomSelectOption & { index: number }> }> = [];
    options.forEach((option, index) => {
      const previous = result.at(-1);
      if (!previous || previous.name !== option.group) {
        result.push({ name: option.group, options: [{ ...option, index }] });
      } else {
        previous.options.push({ ...option, index });
      }
    });
    return result;
  }, [options]);

  useEffect(() => {
    function closeOnOutsidePress(event: PointerEvent) {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    }
    document.addEventListener("pointerdown", closeOnOutsidePress);
    return () => document.removeEventListener("pointerdown", closeOnOutsidePress);
  }, []);

  useEffect(() => {
    if (!open) setActiveIndex(selectedIndex);
  }, [open, selectedIndex]);

  useEffect(
    () => () => {
      if (typeaheadTimer.current !== null) window.clearTimeout(typeaheadTimer.current);
    },
    [],
  );

  function choose(index: number) {
    const option = options[index];
    if (!option || option.unavailable) return;
    onChange(option.value);
    setOpen(false);
  }

  function move(step: number) {
    if (!options.length) return;
    let next = activeIndex;
    for (let attempt = 0; attempt < options.length; attempt += 1) {
      next = (next + step + options.length) % options.length;
      if (!options[next]?.unavailable) break;
    }
    setActiveIndex(next);
  }

  function onKeyDown(event: KeyboardEvent<HTMLButtonElement>) {
    if (disabled) return;
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      if (!open) {
        setOpen(true);
        setActiveIndex(selectedIndex);
      } else {
        move(event.key === "ArrowDown" ? 1 : -1);
      }
      return;
    }
    if (event.key === "Home" && open) {
      event.preventDefault();
      setActiveIndex(options.findIndex((option) => !option.unavailable));
      return;
    }
    if (event.key === "End" && open) {
      event.preventDefault();
      let lastAvailable = options.length - 1;
      while (lastAvailable > 0 && options[lastAvailable]?.unavailable) lastAvailable -= 1;
      setActiveIndex(lastAvailable);
      return;
    }
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      if (open) choose(activeIndex);
      else setOpen(true);
      return;
    }
    if (event.key === "Escape" && open) {
      event.preventDefault();
      setOpen(false);
      return;
    }
    if (event.key.length === 1 && !event.altKey && !event.ctrlKey && !event.metaKey) {
      typeaheadRef.current += event.key.toLocaleLowerCase();
      if (typeaheadTimer.current !== null) window.clearTimeout(typeaheadTimer.current);
      typeaheadTimer.current = window.setTimeout(() => {
        typeaheadRef.current = "";
      }, 600);
      const match = options.findIndex(
        (option) =>
          !option.unavailable && option.label.toLocaleLowerCase().startsWith(typeaheadRef.current),
      );
      if (match >= 0) {
        setActiveIndex(match);
        if (!open) setOpen(true);
      }
    }
  }

  return (
    <div
      className={`custom-select ${className}`.trim()}
      data-open={open}
      data-disabled={disabled}
      ref={rootRef}
    >
      <button
        type="button"
        className="custom-select-trigger"
        role="combobox"
        aria-label={ariaLabel}
        aria-expanded={open}
        aria-controls={listboxId}
        aria-haspopup="listbox"
        aria-activedescendant={open ? `${listboxId}-option-${activeIndex}` : undefined}
        disabled={disabled}
        onClick={() => setOpen((current) => !current)}
        onKeyDown={onKeyDown}
      >
        {icon ? <span className="custom-select-icon">{icon}</span> : null}
        <span className="custom-select-value">
          <strong>{selected?.label ?? "Не выбрано"}</strong>
          {selected?.description ? <small>{selected.description}</small> : null}
        </span>
        <CaretDown className="custom-select-caret" size={14} weight="bold" aria-hidden="true" />
      </button>
      {open ? (
        <div className="custom-select-menu" id={listboxId} role="listbox" aria-label={ariaLabel}>
          {groups.map((group, groupIndex) => (
            <div className="custom-select-group" role="group" aria-label={group.name} key={`${group.name ?? "default"}-${groupIndex}`}>
              {group.name ? <span className="custom-select-group-label">{group.name}</span> : null}
              {group.options.map((option) => {
                const selectedOption = option.value === value;
                return (
                  <button
                    type="button"
                    role="option"
                    id={`${listboxId}-option-${option.index}`}
                    aria-selected={selectedOption}
                    aria-disabled={option.unavailable || undefined}
                    className="custom-select-option"
                    data-active={option.index === activeIndex}
                    data-unavailable={option.unavailable}
                    tabIndex={-1}
                    key={option.value}
                    onMouseEnter={() => setActiveIndex(option.index)}
                    onClick={() => choose(option.index)}
                  >
                    <span>
                      <strong>{option.label}</strong>
                      {option.description ? <small>{option.description}</small> : null}
                    </span>
                    {selectedOption ? <Check size={15} weight="bold" aria-hidden="true" /> : null}
                  </button>
                );
              })}
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}
