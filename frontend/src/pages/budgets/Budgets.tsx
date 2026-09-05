import { useEffect, useState } from "react";
import { Plus } from "lucide-react";
import { DataTable, type DataTableColumn } from "@/components/shared/DataTable";
import { FormShell } from "@/components/shared/FormShell";
import { LineItemsTable, type LineItemColumn } from "@/components/shared/LineItemsTable";
import { MoneyDisplay } from "@/components/shared/MoneyDisplay";
import { MoneyInput } from "@/components/shared/MoneyInput";
import { StatusBadge, type Status } from "@/components/shared/StatusBadge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useApi } from "@/hooks/useApi";
import { api, normaliseError } from "@/lib/api";
import { toast } from "@/hooks/use-toast";
import type {
  AnalyticAccount,
  Budget,
  BudgetDetail,
  BudgetLineType,
  Page,
  Partner,
} from "@/types/api";

const PAGE_SIZE = 20;
const NO_RESPONSIBLE = "none";

type DraftLine = {
  analytic_account_id: string;
  line_type: BudgetLineType;
  committed_amount: string;
  achieved_amount: string | null;
  achieved_percent: string | null;
  amount_to_achieve: string | null;
};

const BLANK_LINE: DraftLine = {
  analytic_account_id: "",
  line_type: "expense",
  committed_amount: "0.00",
  achieved_amount: null,
  achieved_percent: null,
  amount_to_achieve: null,
};

function today(): string {
  return new Date().toISOString().slice(0, 10);
}

type Mode = { kind: "list" } | { kind: "create" } | { kind: "edit"; budgetId: number };

export default function Budgets() {
  const [mode, setMode] = useState<Mode>({ kind: "list" });
  const [page, setPage] = useState(1);
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");

  useEffect(() => {
    const timer = setTimeout(() => {
      setSearch(searchInput);
      setPage(1);
    }, 400);
    return () => clearTimeout(timer);
  }, [searchInput]);

  const query = new URLSearchParams({ page: String(page), page_size: String(PAGE_SIZE) });
  if (search) query.set("search", search);
  const path = `/budgets?${query.toString()}`;

  const { data, loading, error, refetch } = useApi<Page<Budget>>(path, [path]);

  const columns: DataTableColumn<Budget>[] = [
    { key: "name", header: "Name" },
    { key: "start_date", header: "Start" },
    { key: "end_date", header: "End" },
    {
      key: "responsible_name",
      header: "Responsible",
      render: (row) => row.responsible_name ?? "—",
    },
    {
      key: "state",
      header: "Status",
      render: (row) => <StatusBadge status={row.state as Status} />,
    },
  ];

  if (mode.kind !== "list") {
    return (
      <BudgetForm
        key={mode.kind === "edit" ? mode.budgetId : "new"}
        budgetId={mode.kind === "edit" ? mode.budgetId : null}
        onBack={() => setMode({ kind: "list" })}
        onSaved={async () => {
          setMode({ kind: "list" });
          await refetch();
        }}
        onOpenBudget={(id) => setMode({ kind: "edit", budgetId: id })}
      />
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-text_primary">Analytic Budgets</h1>
          <p className="text-sm text-text_secondary">
            Committed amounts per analytic account, measured against confirmed invoices
            and bills.
          </p>
        </div>
        <Button type="button" onClick={() => setMode({ kind: "create" })}>
          <Plus className="mr-2 h-4 w-4" />
          New Budget
        </Button>
      </div>

      <DataTable
        columns={columns}
        rows={data?.items ?? []}
        loading={loading}
        error={error ? { message: error.message } : null}
        page={page}
        pageSize={PAGE_SIZE}
        total={data?.total ?? 0}
        onPageChange={setPage}
        onRowClick={(row) => setMode({ kind: "edit", budgetId: row.id })}
        searchValue={searchInput}
        onSearchChange={setSearchInput}
        onRetry={refetch}
        getRowId={(row) => row.id}
        emptyMessage="No budgets yet — create one against an analytic account."
      />
    </div>
  );
}

function BudgetForm({
  budgetId,
  onBack,
  onSaved,
  onOpenBudget,
}: {
  budgetId: number | null;
  onBack: () => void;
  onSaved: () => void;
  onOpenBudget: (id: number) => void;
}) {
  const detailPath = budgetId ? `/budgets/${budgetId}` : null;
  const {
    data: budget,
    loading,
    error,
    refetch,
  } = useApi<BudgetDetail>(detailPath ?? "/budgets/__none__", [detailPath ?? ""]);

  const { data: analytics } = useApi<Page<AnalyticAccount>>(
    "/analytic-accounts?page=1&page_size=100",
    [],
  );
  const { data: partners } = useApi<Page<Partner>>("/partners?page=1&page_size=100", []);

  const [name, setName] = useState("");
  const [startDate, setStartDate] = useState(today());
  const [endDate, setEndDate] = useState(today());
  const [responsibleId, setResponsibleId] = useState(NO_RESPONSIBLE);
  const [lines, setLines] = useState<DraftLine[]>([{ ...BLANK_LINE }]);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!budget) return;
    setName(budget.name);
    setStartDate(budget.start_date);
    setEndDate(budget.end_date);
    setResponsibleId(
      budget.responsible_id ? String(budget.responsible_id) : NO_RESPONSIBLE,
    );
    setLines(
      budget.lines.map((line) => ({
        analytic_account_id: String(line.analytic_account_id),
        line_type: line.line_type,
        committed_amount: line.committed_amount,
        achieved_amount: line.achieved_amount ?? null,
        achieved_percent: line.achieved_percent ?? null,
        amount_to_achieve: line.amount_to_achieve ?? null,
      })),
    );
  }, [budget]);

  // Only a draft budget is editable — PUT returns 409 otherwise (§9 budgets).
  const isDraft = !budget || budget.state === "draft";
  // Achieved figures are returned only once confirmed or revised (§7.9).
  const showsAchievement =
    budget && (budget.state === "confirmed" || budget.state === "revised");

  function updateLine(index: number, patch: Partial<DraftLine>) {
    setLines((prev) => prev.map((line, i) => (i === index ? { ...line, ...patch } : line)));
  }

  const columns: LineItemColumn<DraftLine>[] = [
    {
      key: "analytic_account_id",
      header: "Analytic Account",
      render: (row, index) => (
        <Select
          value={row.analytic_account_id}
          disabled={!isDraft}
          onValueChange={(value) => updateLine(index, { analytic_account_id: value })}
        >
          <SelectTrigger className="min-w-[11rem]">
            <SelectValue placeholder="Select analytic" />
          </SelectTrigger>
          <SelectContent>
            {(analytics?.items ?? []).map((analytic) => (
              <SelectItem key={analytic.id} value={String(analytic.id)}>
                {analytic.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      ),
    },
    {
      key: "line_type",
      header: "Type",
      render: (row, index) => (
        <Select
          value={row.line_type}
          disabled={!isDraft}
          onValueChange={(value) =>
            updateLine(index, { line_type: value as BudgetLineType })
          }
        >
          <SelectTrigger className="min-w-[8rem]">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="income">Income</SelectItem>
            <SelectItem value="expense">Expense</SelectItem>
          </SelectContent>
        </Select>
      ),
    },
    {
      key: "committed_amount",
      header: "Committed",
      align: "right",
      render: (row, index) => (
        <MoneyInput
          value={row.committed_amount}
          disabled={!isDraft}
          onChange={(value) => updateLine(index, { committed_amount: value })}
        />
      ),
    },
    ...(showsAchievement
      ? [
          {
            key: "achieved_amount",
            header: "Achieved",
            align: "right" as const,
            render: (row: DraftLine) =>
              row.achieved_amount ? <MoneyDisplay value={row.achieved_amount} /> : "—",
          },
          {
            key: "achieved_percent",
            header: "%",
            align: "right" as const,
            render: (row: DraftLine) =>
              row.achieved_percent ? `${row.achieved_percent}%` : "—",
          },
          {
            key: "amount_to_achieve",
            header: "To Achieve",
            align: "right" as const,
            render: (row: DraftLine) =>
              row.amount_to_achieve ? <MoneyDisplay value={row.amount_to_achieve} /> : "—",
          },
        ]
      : []),
  ];

  function toBody() {
    return {
      name: name.trim(),
      start_date: startDate,
      end_date: endDate,
      responsible_id:
        responsibleId === NO_RESPONSIBLE ? null : Number(responsibleId),
      lines: lines
        .filter((line) => line.analytic_account_id)
        .map((line) => ({
          analytic_account_id: Number(line.analytic_account_id),
          line_type: line.line_type,
          committed_amount: line.committed_amount,
        })),
    };
  }

  async function run(label: string, fn: () => Promise<unknown>) {
    setBusy(true);
    try {
      await fn();
      toast({ title: label });
      onSaved();
    } catch (e) {
      toast({
        variant: "destructive",
        title: `Could not ${label.toLowerCase()}`,
        description: normaliseError(e).message,
      });
    } finally {
      setBusy(false);
    }
  }

  if (budgetId && loading) {
    return <p className="text-sm text-text_secondary">Loading budget...</p>;
  }

  if (budgetId && error) {
    return (
      <div className="flex flex-col items-start gap-3">
        <p className="text-sm text-danger">{error.message}</p>
        <div className="flex gap-2">
          <Button type="button" variant="outline" onClick={refetch}>
            Retry
          </Button>
          <Button type="button" variant="ghost" onClick={onBack}>
            Back
          </Button>
        </div>
      </div>
    );
  }

  const actions = [
    { label: "Back", variant: "outline" as const, onClick: onBack },
    ...(isDraft
      ? [
          {
            label: "Save",
            variant: "outline" as const,
            disabled: busy || !name.trim(),
            onClick: () =>
              run("Budget saved", () =>
                budget
                  ? api.put(`/budgets/${budget.id}`, toBody())
                  : api.post("/budgets", toBody()),
              ),
          },
        ]
      : []),
    ...(budget && budget.state === "draft"
      ? [
          {
            label: "Confirm",
            disabled: busy,
            onClick: () =>
              run("Budget confirmed", () => api.post(`/budgets/${budget.id}/confirm`)),
          },
        ]
      : []),
    ...(budget && budget.state === "confirmed"
      ? [
          {
            label: "Revise",
            disabled: busy,
            onClick: async () => {
              setBusy(true);
              try {
                // Revising creates a linked draft copy and leaves the original
                // untouched (§10.7) — open the new revision straight away.
                const revision = await api.post<Budget>(`/budgets/${budget.id}/revise`);
                toast({ title: "Revision created" });
                onOpenBudget(revision.id);
              } catch (e) {
                toast({
                  variant: "destructive",
                  title: "Could not revise budget",
                  description: normaliseError(e).message,
                });
              } finally {
                setBusy(false);
              }
            },
          },
        ]
      : []),
    ...(budget && budget.state !== "cancelled"
      ? [
          {
            label: "Cancel Budget",
            variant: "outline" as const,
            disabled: busy,
            onClick: () =>
              run("Budget cancelled", () => api.post(`/budgets/${budget.id}/cancel`)),
          },
        ]
      : []),
  ];

  return (
    <FormShell
      title={budget ? budget.name : "New Budget"}
      state={budget?.state}
      variant="budget"
      onBack={onBack}
      actions={actions}
    >
      <div className="flex flex-col gap-6">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <div>
            <Label htmlFor="budget_name">Name</Label>
            <Input
              id="budget_name"
              value={name}
              disabled={!isDraft}
              onChange={(e) => setName(e.target.value)}
            />
          </div>

          <div>
            <Label htmlFor="start_date">Start Date</Label>
            <Input
              id="start_date"
              type="date"
              value={startDate}
              disabled={!isDraft}
              onChange={(e) => setStartDate(e.target.value)}
            />
          </div>

          <div>
            <Label htmlFor="end_date">End Date</Label>
            <Input
              id="end_date"
              type="date"
              value={endDate}
              disabled={!isDraft}
              onChange={(e) => setEndDate(e.target.value)}
            />
          </div>

          <div>
            <Label htmlFor="responsible_id">Responsible</Label>
            <Select
              value={responsibleId}
              onValueChange={setResponsibleId}
              disabled={!isDraft}
            >
              <SelectTrigger id="responsible_id">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={NO_RESPONSIBLE}>Unassigned</SelectItem>
                {(partners?.items ?? []).map((partner) => (
                  <SelectItem key={partner.id} value={String(partner.id)}>
                    {partner.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>

        {budget?.revision_of_id && (
          <p className="text-sm text-text_secondary">
            Revision of{" "}
            <button
              type="button"
              className="text-accent underline"
              onClick={() => onOpenBudget(budget.revision_of_id!)}
            >
              budget #{budget.revision_of_id}
            </button>
          </p>
        )}
        {budget?.revised_with_id && (
          <p className="text-sm text-text_secondary">
            Revised with{" "}
            <button
              type="button"
              className="text-accent underline"
              onClick={() => onOpenBudget(budget.revised_with_id!)}
            >
              budget #{budget.revised_with_id}
            </button>
          </p>
        )}

        <LineItemsTable
          rows={lines}
          columns={columns}
          getLineTotal={(row) => row.committed_amount}
          addLabel="Add budget line"
          onAddRow={() => setLines((prev) => [...prev, { ...BLANK_LINE }])}
          onRemoveRow={(index) => setLines((prev) => prev.filter((_, i) => i !== index))}
        />

        {!showsAchievement && budget && (
          <p className="text-xs text-text_secondary">
            Achieved amounts appear once the budget is confirmed.
          </p>
        )}
      </div>
    </FormShell>
  );
}
