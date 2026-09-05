import { useEffect, type ReactNode } from "react";
import { Plus, Trash2 } from "lucide-react";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import { MoneyDisplay } from "@/components/shared/MoneyDisplay";
import { cn } from "@/lib/utils";

export type LineItemColumn<T> = {
  key: string;
  header: string;
  render: (row: T, index: number) => ReactNode;
  align?: "left" | "right";
};

type DocumentVariant<T> = {
  variant?: "document";
  getLineTotal: (row: T) => number;
};

type JournalEntryVariant<T> = {
  variant: "journal_entry";
  getDebit: (row: T) => number;
  getCredit: (row: T) => number;
  // Lets the page (which owns the Post button) disable it until balanced —
  // SPEC.md §13.2 journal_entry_variant.
  onBalanceChange?: (isBalanced: boolean) => void;
};

export type LineItemsTableProps<T> = {
  rows: T[];
  columns: LineItemColumn<T>[];
  onAddRow: () => void;
  onRemoveRow: (index: number) => void;
  addLabel?: string;
} & (DocumentVariant<T> | JournalEntryVariant<T>);

// SPEC.md §13.2 LineItemsTable — reused for PO/Bill/SO/Invoice/Journal Entry/
// Budget lines. Per-row editing (a product select, an account select, a
// MoneyInput, ...) is supplied by the caller via each column's `render`;
// this component only owns row add/remove and the running footer totals.
// "Live line total from the server on blur" is a page-level concern (it
// calls the API), so it lives in the render function a page supplies, not
// here.
export function LineItemsTable<T>(props: LineItemsTableProps<T>) {
  const { rows, columns, onAddRow, onRemoveRow, addLabel = "Add line" } = props;
  const isJournalEntry = props.variant === "journal_entry";

  const totalDebit = isJournalEntry
    ? rows.reduce((sum, row) => sum + props.getDebit(row), 0)
    : 0;
  const totalCredit = isJournalEntry
    ? rows.reduce((sum, row) => sum + props.getCredit(row), 0)
    : 0;
  const difference = totalDebit - totalCredit;
  const documentTotal = !isJournalEntry
    ? rows.reduce((sum, row) => sum + props.getLineTotal(row), 0)
    : 0;

  useEffect(() => {
    if (isJournalEntry) {
      props.onBalanceChange?.(difference === 0);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [difference, isJournalEntry]);

  return (
    <div className="flex flex-col gap-3">
      <div className="overflow-hidden rounded-md border border-border">
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
              <TableHead className="w-10" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((row, index) => (
              <TableRow key={index}>
                {columns.map((col) => (
                  <TableCell
                    key={col.key}
                    className={cn(col.align === "right" && "text-right")}
                  >
                    {col.render(row, index)}
                  </TableCell>
                ))}
                <TableCell>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    aria-label="Remove line"
                    onClick={() => onRemoveRow(index)}
                  >
                    <Trash2 className="h-4 w-4 text-danger" />
                  </Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

      <Button
        type="button"
        variant="outline"
        size="sm"
        onClick={onAddRow}
        className="self-start"
      >
        <Plus className="mr-2 h-4 w-4" />
        {addLabel}
      </Button>

      {isJournalEntry ? (
        <div className="flex flex-col items-end gap-1 border-t border-border pt-3 text-sm">
          <div className="flex gap-6">
            <span className="text-text_secondary">
              Debit: <MoneyDisplay value={totalDebit} />
            </span>
            <span className="text-text_secondary">
              Credit: <MoneyDisplay value={totalCredit} />
            </span>
          </div>
          {difference !== 0 && (
            <span className="font-medium text-danger">
              Difference: <MoneyDisplay value={Math.abs(difference)} />
            </span>
          )}
        </div>
      ) : (
        <div className="flex justify-end border-t border-border pt-3 text-sm font-medium text-text_primary">
          Total:
          <MoneyDisplay value={documentTotal} className="ml-2" />
        </div>
      )}
    </div>
  );
}
