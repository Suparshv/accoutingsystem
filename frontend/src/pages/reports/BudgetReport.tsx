import { useState } from "react";
import { Cell, Legend, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";
import { DataTable, type DataTableColumn } from "@/components/shared/DataTable";
import { KanbanGrid } from "@/components/shared/KanbanGrid";
import { MoneyDisplay } from "@/components/shared/MoneyDisplay";
import { ViewSwitcher, type ViewMode } from "@/components/shared/ViewSwitcher";
import { useApi } from "@/hooks/useApi";
import { toMinorUnits } from "@/lib/money";
import type { BudgetSummaryRow, Page } from "@/types/api";

// Slice colours come from the chart tokens in index.css: plum for achieved,
// neutral grey for what's left. Deliberately no green (Odoo doesn't use it).
const ACHIEVED_COLOR = "var(--chart-1)";
const REMAINING_COLOR = "var(--chart-5)";

export default function BudgetReport() {
  const [viewMode, setViewMode] = useState<ViewMode>("kanban");
  const path = "/reports/budget-summary";
  const { data, loading, error, refetch } = useApi<Page<BudgetSummaryRow>>(path, [path]);

  const rows = data?.items ?? [];

  const columns: DataTableColumn<BudgetSummaryRow>[] = [
    { key: "budget_name", header: "Budget" },
    {
      key: "committed_amount",
      header: "Committed",
      align: "right",
      render: (row) => <MoneyDisplay value={row.committed_amount} />,
    },
    {
      key: "achieved_amount",
      header: "Achieved",
      align: "right",
      render: (row) => <MoneyDisplay value={row.achieved_amount} />,
    },
    {
      key: "achieved_percent",
      header: "%",
      align: "right",
      render: (row) => `${row.achieved_percent}%`,
    },
  ];

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-text_primary">Budget Report</h1>
          <p className="text-sm text-text_secondary">
            Achieved versus committed per budget, based on confirmed invoices and bills.
          </p>
        </div>
        <ViewSwitcher value={viewMode} onChange={setViewMode} />
      </div>

      {viewMode === "list" ? (
        <DataTable
          columns={columns}
          rows={rows}
          loading={loading}
          error={error ? { message: error.message } : null}
          page={1}
          pageSize={rows.length || 20}
          total={data?.total ?? rows.length}
          onPageChange={() => {}}
          searchValue=""
          onSearchChange={() => {}}
          onRetry={refetch}
          getRowId={(row) => row.budget_id}
          emptyMessage="No confirmed budgets yet — confirm a budget to see its achievement."
        />
      ) : (
        <KanbanGrid
          items={rows}
          loading={loading}
          error={error ? { message: error.message } : null}
          onRetry={refetch}
          getItemId={(row) => row.budget_id}
          emptyMessage="No confirmed budgets yet."
          renderCard={(row) => <BudgetDonut row={row} />}
        />
      )}
    </div>
  );
}

function BudgetDonut({ row }: { row: BudgetSummaryRow }) {
  // Slice sizes only. Amounts are parsed to exact integer paise (never a
  // float) purely to give the chart a proportion — every figure the user
  // actually reads is rendered from the original string via MoneyDisplay.
  const achieved = toMinorUnits(row.achieved_amount);
  const committed = toMinorUnits(row.committed_amount);
  const remaining = Math.max(committed - achieved, 0);

  const slices = [
    { name: "Achieved", value: achieved, color: ACHIEVED_COLOR },
    { name: "Remaining", value: remaining, color: REMAINING_COLOR },
  ];
  const hasData = achieved > 0 || remaining > 0;

  return (
    <div className="flex flex-col gap-3">
      <p className="font-medium text-text_primary">{row.budget_name}</p>

      <div className="h-48">
        {hasData ? (
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie
                data={slices}
                dataKey="value"
                nameKey="name"
                cx="50%"
                cy="45%"
                innerRadius={38}
                outerRadius={62}
                stroke="none"
                // Off so the donut is drawn immediately — it renders correctly
                // on first paint and in Print, instead of animating in.
                isAnimationActive={false}
              >
                {slices.map((slice) => (
                  <Cell key={slice.name} fill={slice.color} />
                ))}
              </Pie>
              <Tooltip
                formatter={(value: number, name: string) => [
                  `₹${(value / 100).toFixed(2)}`,
                  name,
                ]}
              />
              <Legend verticalAlign="bottom" height={24} />
            </PieChart>
          </ResponsiveContainer>
        ) : (
          <p className="flex h-full items-center justify-center text-sm text-text_secondary">
            Nothing committed yet
          </p>
        )}
      </div>

      <dl className="grid grid-cols-3 gap-2 text-xs">
        <div>
          <dt className="text-text_secondary">Committed</dt>
          <dd>
            <MoneyDisplay value={row.committed_amount} />
          </dd>
        </div>
        <div>
          <dt className="text-text_secondary">Achieved</dt>
          <dd>
            <MoneyDisplay value={row.achieved_amount} />
          </dd>
        </div>
        <div>
          <dt className="text-text_secondary">Percent</dt>
          <dd className="tabular-nums text-text_primary">{row.achieved_percent}%</dd>
        </div>
      </dl>
    </div>
  );
}
