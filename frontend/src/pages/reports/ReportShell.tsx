import type { ReactNode } from "react";
import { Printer, RotateCcw } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { yearOptions } from "@/lib/dates";

// Shared frame for the three financial statements: title, year selector,
// Print, and the loading/error/empty handling each of them needs. Page-level
// helper — the reports aren't list views, so DataTable doesn't fit them.
type ReportShellProps = {
  title: string;
  description: string;
  year: number;
  onYearChange: (year: number) => void;
  loading?: boolean;
  error?: { message: string } | null;
  onRetry?: () => void;
  children: ReactNode;
};

export function ReportShell({
  title,
  description,
  year,
  onYearChange,
  loading = false,
  error = null,
  onRetry,
  children,
}: ReportShellProps) {
  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-end justify-between gap-3 print:hidden">
        <div>
          <h1 className="text-2xl font-semibold text-text_primary">{title}</h1>
          <p className="text-sm text-text_secondary">{description}</p>
        </div>
        <div className="flex items-end gap-2">
          <div>
            <label className="mb-1 block text-xs font-medium text-text_secondary">
              Year
            </label>
            <Select value={String(year)} onValueChange={(v) => onYearChange(Number(v))}>
              <SelectTrigger className="w-28">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {yearOptions().map((option) => (
                  <SelectItem key={option} value={String(option)}>
                    {option}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <Button type="button" variant="outline" onClick={() => window.print()}>
            <Printer className="mr-2 h-4 w-4" />
            Print
          </Button>
        </div>
      </div>

      {loading && (
        <div className="space-y-2">
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="h-6 animate-pulse rounded bg-border" />
          ))}
        </div>
      )}

      {!loading && error && (
        <div className="flex flex-col items-center gap-3 rounded border border-border px-4 py-10 text-center">
          <p className="text-sm text-danger">{error.message}</p>
          {onRetry && (
            <Button type="button" variant="outline" size="sm" onClick={onRetry}>
              <RotateCcw className="mr-2 h-4 w-4" />
              Retry
            </Button>
          )}
        </div>
      )}

      {!loading && !error && children}
    </div>
  );
}
