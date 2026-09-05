import type { ReactNode } from "react";
import { RotateCcw, Search } from "lucide-react";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export type DataTableColumn<T> = {
  key: string;
  header: string;
  render?: (row: T) => ReactNode;
  align?: "left" | "right";
};

// SPEC.md §13.2 DataTable block. `getRowId` and `onRetry` aren't in the
// spec's literal prop list but are required to implement two of the listed
// features (stable row identity, and the error state's retry action).
export type DataTableProps<T> = {
  columns: DataTableColumn<T>[];
  rows: T[];
  loading?: boolean;
  error?: { message: string } | null;
  page: number;
  pageSize: number;
  total: number;
  onPageChange: (page: number) => void;
  onRowClick?: (row: T) => void;
  searchValue: string;
  onSearchChange: (value: string) => void;
  emptyMessage?: string;
  onRetry?: () => void;
  getRowId: (row: T) => string | number;
};

function cellValue<T>(col: DataTableColumn<T>, row: T): ReactNode {
  if (col.render) return col.render(row);
  return String((row as Record<string, unknown>)[col.key] ?? "");
}

export function DataTable<T>({
  columns,
  rows,
  loading = false,
  error = null,
  page,
  pageSize,
  total,
  onPageChange,
  onRowClick,
  searchValue,
  onSearchChange,
  emptyMessage = "No records yet.",
  onRetry,
  getRowId,
}: DataTableProps<T>) {
  const totalPages = Math.max(1, Math.ceil(total / Math.max(pageSize, 1)));
  const showRows = !loading && !error && rows.length > 0;
  const showEmpty = !loading && !error && rows.length === 0;

  return (
    <div className="flex flex-col gap-3">
      <div className="relative w-full max-w-xs">
        <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-text_secondary" />
        <Input
          value={searchValue}
          onChange={(e) => onSearchChange(e.target.value)}
          placeholder="Search..."
          className="pl-8"
        />
      </div>

      <div className="overflow-hidden rounded-md border border-border">
        {loading && (
          <div className="divide-y divide-border">
            {Array.from({ length: Math.min(pageSize || 5, 5) }).map((_, i) => (
              <div key={i} className="flex gap-4 px-4 py-3">
                {columns.map((col) => (
                  <div
                    key={col.key}
                    className="h-4 flex-1 animate-pulse rounded bg-border"
                  />
                ))}
              </div>
            ))}
          </div>
        )}

        {!loading && error && (
          <div className="flex flex-col items-center gap-3 px-4 py-10 text-center">
            <p className="text-sm text-danger">{error.message}</p>
            {onRetry && (
              <Button type="button" variant="outline" size="sm" onClick={onRetry}>
                <RotateCcw className="mr-2 h-4 w-4" />
                Retry
              </Button>
            )}
          </div>
        )}

        {showEmpty && (
          <div className="px-4 py-10 text-center text-sm text-text_secondary">
            {emptyMessage}
          </div>
        )}

        {showRows && (
          <>
            {/* Desktop / tablet: a real table. */}
            <div className="hidden md:block">
              <Table>
                <TableHeader>
                  <TableRow>
                    {columns.map((col) => (
                      <TableHead
                        key={col.key}
                        className={cn(col.align === "right" && "text-right")}
                      >
                        {col.header}
                      </TableHead>
                    ))}
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {rows.map((row) => (
                    <TableRow
                      key={getRowId(row)}
                      onClick={() => onRowClick?.(row)}
                      className={cn(onRowClick && "cursor-pointer")}
                    >
                      {columns.map((col) => (
                        <TableCell
                          key={col.key}
                          className={cn(
                            col.align === "right" && "text-right tabular-nums",
                          )}
                        >
                          {cellValue(col, row)}
                        </TableCell>
                      ))}
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>

            {/* Mobile: stacked cards, never a horizontal scrollbar (SPEC.md §13.1).
                Label above value (not side-by-side) so a long value — an email,
                a name — wraps instead of overflowing the viewport edge. */}
            <div className="divide-y divide-border md:hidden">
              {rows.map((row) => (
                <div
                  key={getRowId(row)}
                  onClick={() => onRowClick?.(row)}
                  className={cn("space-y-2 px-4 py-3", onRowClick && "cursor-pointer")}
                >
                  {columns.map((col) => (
                    <div key={col.key} className="flex flex-col gap-0.5 text-sm">
                      <span className="text-xs text-text_secondary">{col.header}</span>
                      <span
                        className={cn(
                          "break-words text-text_primary",
                          col.align === "right" && "tabular-nums",
                        )}
                      >
                        {cellValue(col, row)}
                      </span>
                    </div>
                  ))}
                </div>
              ))}
            </div>
          </>
        )}
      </div>

      {showRows && (
        <div className="flex items-center justify-between text-sm text-text_secondary">
          <span>
            Page {page} of {totalPages} &middot; {total} total
          </span>
          <div className="flex gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={page <= 1}
              onClick={() => onPageChange(page - 1)}
            >
              Previous
            </Button>
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={page >= totalPages}
              onClick={() => onPageChange(page + 1)}
            >
              Next
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
