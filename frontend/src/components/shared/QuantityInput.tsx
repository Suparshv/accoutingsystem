import { forwardRef, type ChangeEvent } from "react";
import { Input } from "@/components/ui/input";
import { TWO_DECIMAL_MASK } from "@/components/shared/MoneyInput";
import { cn } from "@/lib/utils";

// A line quantity is a NUMERIC(14,2) on the server, and the line total the
// form shows live is quantity x unit_price parsed to exact hundredths
// (lib/money.ts). An unmasked text box let a third decimal, a minus sign or a
// stray letter through — none of which that parser can read, so the line total
// silently fell to 0.00 while the box still showed what had been typed.
//
// Same mask and the same "never a float" contract as MoneyInput; separate
// component only because a quantity is not money and should not read as it.
type QuantityInputProps = {
  value: string;
  onChange: (value: string) => void;
  className?: string;
  disabled?: boolean;
  id?: string;
};

export const QuantityInput = forwardRef<HTMLInputElement, QuantityInputProps>(
  ({ value, onChange, className, disabled, id }, ref) => {
    function handleChange(e: ChangeEvent<HTMLInputElement>) {
      const next = e.target.value;
      if (TWO_DECIMAL_MASK.test(next)) onChange(next);
    }

    return (
      <Input
        ref={ref}
        id={id}
        type="text"
        inputMode="decimal"
        value={value}
        onChange={handleChange}
        placeholder="1"
        disabled={disabled}
        className={cn("w-24 min-w-[5rem] text-right tabular-nums", className)}
      />
    );
  },
);
QuantityInput.displayName = "QuantityInput";
