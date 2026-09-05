import { useState } from "react";
import { MoneyDisplay } from "@/components/shared/MoneyDisplay";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useApi } from "@/hooks/useApi";
import { ReportShell } from "@/pages/reports/ReportShell";
import { currentYear } from "@/lib/dates";
import type { TrialBalance as TrialBalanceData } from "@/types/api";

export default function TrialBalance() {
  const [year, setYear] = useState(currentYear());
  const path = `/reports/trial-balance?year=${year}`;
  const { data, loading, error, refetch } = useApi<TrialBalanceData>(path, [path]);

  return (
    <ReportShell
      title="Trial Balance"
      description="Every account's debit and credit totals. If the grand totals differ, the ledger is broken."
      year={year}
      onYearChange={setYear}
      loading={loading}
      error={error ? { message: error.message } : null}
      onRetry={refetch}
    >
      {data && (
        <div className="flex flex-col gap-4">
          <div
            className={`rounded border px-4 py-3 text-sm ${
              data.is_balanced
                ? "border-success text-success"
                : "border-danger text-danger"
            }`}
          >
            {data.is_balanced
              ? "Balanced — total debits equal total credits across the whole ledger."
              : "NOT BALANCED — total debits do not equal total credits."}
          </div>

          <div className="overflow-hidden rounded border border-border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Code</TableHead>
                  <TableHead>Account</TableHead>
                  <TableHead className="text-right">Debit</TableHead>
                  <TableHead className="text-right">Credit</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.rows.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={4} className="py-8 text-center text-text_secondary">
                      Nothing posted to the ledger yet.
                    </TableCell>
                  </TableRow>
                )}
                {data.rows.map((row) => (
                  <TableRow key={row.account_code}>
                    <TableCell>{row.account_code}</TableCell>
                    <TableCell>{row.account_name}</TableCell>
                    <TableCell className="text-right tabular-nums">
                      <MoneyDisplay value={row.total_debit} />
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      <MoneyDisplay value={row.total_credit} />
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>

          <div className="flex justify-end gap-8 rounded border border-border bg-surface px-4 py-3 text-sm font-semibold">
            <span>
              Total Debit: <MoneyDisplay value={data.grand_total_debit} />
            </span>
            <span>
              Total Credit: <MoneyDisplay value={data.grand_total_credit} />
            </span>
          </div>
        </div>
      )}
    </ReportShell>
  );
}
