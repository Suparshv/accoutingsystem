import { useState } from "react";
import { MoneyDisplay } from "@/components/shared/MoneyDisplay";
import { useApi } from "@/hooks/useApi";
import { ReportShell } from "@/pages/reports/ReportShell";
import { currentYear } from "@/lib/dates";
import type { ProfitAndLoss as ProfitAndLossData } from "@/types/api";

export default function ProfitAndLoss() {
  const [year, setYear] = useState(currentYear());
  const path = `/reports/profit-and-loss?year=${year}`;
  const { data, loading, error, refetch } = useApi<ProfitAndLossData>(path, [path]);

  return (
    <ReportShell
      title="Profit and Loss"
      description="What was earned and spent over the period."
      year={year}
      onYearChange={setYear}
      loading={loading}
      error={error ? { message: error.message } : null}
      onRetry={refetch}
    >
      {data && (
        <div className="flex max-w-2xl flex-col gap-5">
          <section className="rounded border border-border">
            <h2 className="border-b border-border bg-surface px-4 py-2 text-sm font-semibold text-text_primary">
              Income
            </h2>
            <Row label="Income from Sales" value={data.income.income_from_sales} />
            <Row label="Total Income" value={data.income.total_income} emphasis />
          </section>

          <section className="rounded border border-border">
            <h2 className="border-b border-border bg-surface px-4 py-2 text-sm font-semibold text-text_primary">
              Expenses
            </h2>
            <Row label="Purchase Expense" value={data.expenses.purchase_expense} />
            <Row label="Other Expense" value={data.expenses.other_expense} />
            <Row label="Total Expenses" value={data.expenses.total_expenses} emphasis />
          </section>

          <section className="flex items-center justify-between rounded border border-border bg-surface px-4 py-3 text-sm font-semibold">
            <span className="text-text_primary">Net Income</span>
            <MoneyDisplay value={data.net_income} />
          </section>
        </div>
      )}
    </ReportShell>
  );
}

function Row({
  label,
  value,
  emphasis = false,
}: {
  label: string;
  value: string;
  emphasis?: boolean;
}) {
  return (
    <div
      className={`flex items-center justify-between border-b border-border px-4 py-2 text-sm last:border-b-0 ${
        emphasis ? "bg-surface font-semibold" : ""
      }`}
    >
      <span className="text-text_primary">{label}</span>
      <MoneyDisplay value={value} />
    </div>
  );
}
