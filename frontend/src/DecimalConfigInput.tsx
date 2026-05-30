import { useState, type InputHTMLAttributes } from "react";
import { parseLocaleNumber } from "./mexcDisplay";

/** Text input that allows typing decimals like 0.0002 without stripping "." mid-edit. */
export function DecimalConfigInput({
  value,
  onChange,
  ...props
}: {
  value: number;
  onChange: (value: number) => void;
} & Omit<InputHTMLAttributes<HTMLInputElement>, "value" | "onChange" | "type" | "inputMode">) {
  const [draft, setDraft] = useState<string | null>(null);
  const display = draft ?? String(value);

  return (
    <input
      {...props}
      type="text"
      inputMode="decimal"
      value={display}
      onFocus={() => setDraft(String(value))}
      onChange={(e) => setDraft(e.target.value)}
      onBlur={() => {
        if (draft !== null) onChange(parseLocaleNumber(draft, value));
        setDraft(null);
      }}
    />
  );
}
