import { useState } from "react";
import { MoneyDisplay } from "@/components/shared/MoneyDisplay";
import { useApi } from "@/hooks/useApi";
import { ReportShell } from "@/pages/reports/ReportShell";
import { currentYear } from "@/lib/dates";
import type { BalanceSheet as BalanceSheetData, BalanceSheetRow } from "@/types/api";

export default function BalanceSheet() {
  const [year, setYear] = useState(currentYear());
  const path = `/reports/balance-sheet?year=${year}`;
  const { data, loading, error, refetch } = useApi<BalanceSheetData>(path, [path]);

  return (
    <ReportShell
      title="Balance Sheet"
      description="What the business owns and owes, derived entirely from posted ledger lines."
      year={year}
      onYearChange={setYear}
      loading={loading}
      error={error ? { message: error.message } : null}
      onRetry={refetch}
    >
      {data && (
        <div className="flex flex-col gap-5">
          {/* is_balanced is the live proof of P1 — surface it (SPEC.md §9). */}
          <div
            className={`rounded border px-4 py-3 text-sm ${
              data.is_balanced
                ? "border-success text-success"
                : "border-danger text-danger"
            }`}
          >
            {data.is_balanced
              ? "Balanced — total assets equal total liabilities."
              : "NOT BALANCED — total assets do not equal total liabilities. The ledger is broken."}
          </div>

          <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
            <Column title="Assets" rows={data.assets} total={data.total_assets} />
            <Column
              title="Liabilities"
              rows={data.liabilities}
              total={data.total_liabilities}
            />
          </div>
        </div>
      )}
    </ReportShell>
  );
}

function Column({
  title,
  rows,
  total,
}: {
  title: string;
  rows: BalanceSheetRow[];
  total: string;
}) {
  return (
    <section className="rounded border border-border">
      <h2 className="border-b border-border bg-surface px-4 py-2 text-sm font-semibold text-text_primary">
        {title}
      </h2>
      <dl>
        {rows.length === 0 && (
          <p className="px-4 py-6 text-center text-sm text-text_secondary">
            Nothing posted to these accounts yet.
          </p>
        )}
        {rows.map((row) => (
          <div
            key={`${row.account_type}-${row.label}`}
            className="flex items-center justify-between border-b border-border px-4 py-2 text-sm last:border-b-0"
          >
            <dt className="text-text_primary">{row.label}</dt>
            <dd className="text-right tabular-nums">
              <MoneyDisplay value={row.balance} />
            </dd>
          </div>
        ))}
      </dl>
      <div className="flex items-center justify-between border-t border-border bg-surface px-4 py-2 text-sm font-semibold">
        <span className="text-text_primary">Total {title}</span>
        <MoneyDisplay value={total} />
      </div>
    </section>
  );
}
