import { forwardRef, type ChangeEvent } from "react";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

// SPEC.md §13.5 — value is a string end to end, never a JS number, so a
// money field can never be silently coerced into a float. type="number"
// is never used on a money input.
const MONEY_MASK = /^\d*\.?\d{0,2}$/;

type MoneyInputProps = {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  className?: string;
  disabled?: boolean;
  name?: string;
  id?: string;
};

export const MoneyInput = forwardRef<HTMLInputElement, MoneyInputProps>(
  ({ value, onChange, placeholder = "0.00", className, disabled, name, id }, ref) => {
    function handleChange(e: ChangeEvent<HTMLInputElement>) {
      const next = e.target.value;
      if (MONEY_MASK.test(next)) {
        onChange(next);
      }
    }

    return (
      <Input
        ref={ref}
        id={id}
        name={name}
        type="text"
        inputMode="decimal"
        value={value}
        onChange={handleChange}
        placeholder={placeholder}
        disabled={disabled}
        className={cn("text-right tabular-nums", className)}
      />
    );
  },
);
MoneyInput.displayName = "MoneyInput";
