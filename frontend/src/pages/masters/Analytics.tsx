import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Plus } from "lucide-react";
import { DataTable, type DataTableColumn } from "@/components/shared/DataTable";
import { KanbanGrid } from "@/components/shared/KanbanGrid";
import { ViewSwitcher, type ViewMode } from "@/components/shared/ViewSwitcher";
import { FieldError } from "@/components/shared/FieldError";
import { FormShell } from "@/components/shared/FormShell";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useApi } from "@/hooks/useApi";
import { useDebouncedValue } from "@/hooks/useDebouncedValue";
import { api, normaliseError } from "@/lib/api";
import { applyServerErrors } from "@/lib/form-errors";
import { toast } from "@/hooks/use-toast";
import type { AnalyticAccount, Page } from "@/types/api";

const PAGE_SIZE = 20;

// Mirrors backend/app/schemas/analytic.py.
const analyticSchema = z.object({
  name: z.string().trim().min(1, "Name is required").max(150),
});
type AnalyticFormValues = z.infer<typeof analyticSchema>;

type Mode = { kind: "list" } | { kind: "create" } | { kind: "edit"; analytic: AnalyticAccount };

export default function Analytics() {
  const [mode, setMode] = useState<Mode>({ kind: "list" });
  const [page, setPage] = useState(1);
  const [searchInput, setSearchInput] = useState("");
  const search = useDebouncedValue(searchInput);
  const [viewMode, setViewMode] = useState<ViewMode>("list");

  // A new search term is a new result set, so it starts at page 1 again.
  useEffect(() => {
    setPage(1);
  }, [search]);

  const query = new URLSearchParams({ page: String(page), page_size: String(PAGE_SIZE) });
  if (search) query.set("search", search);
  const path = `/analytic-accounts?${query.toString()}`;

  const { data, loading, error, refetch } = useApi<Page<AnalyticAccount>>(path, [path]);

  const columns: DataTableColumn<AnalyticAccount>[] = [{ key: "name", header: "Name" }];

  async function handleSaved() {
    setMode({ kind: "list" });
    await refetch();
  }

  if (mode.kind !== "list") {
    return (
      <AnalyticForm
        key={mode.kind === "edit" ? mode.analytic.id : "new"}
        analytic={mode.kind === "edit" ? mode.analytic : null}
        onBack={() => setMode({ kind: "list" })}
        onSaved={handleSaved}
      />
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-text_primary">Analytic Accounts</h1>
          <p className="text-sm text-text_secondary">
            Project / cost-centre tags used by budgets.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <ViewSwitcher value={viewMode} onChange={setViewMode} />
          <Button type="button" onClick={() => setMode({ kind: "create" })}>
            <Plus className="mr-2 h-4 w-4" />
            New Analytic Account
          </Button>
        </div>
      </div>

      {viewMode === "list" ? (
        <DataTable
          columns={columns}
          rows={data?.items ?? []}
          loading={loading}
          error={error ? { message: error.message } : null}
          page={page}
          pageSize={PAGE_SIZE}
          total={data?.total ?? 0}
          onPageChange={setPage}
          onRowClick={(row) => setMode({ kind: "edit", analytic: row })}
          searchValue={searchInput}
          onSearchChange={setSearchInput}
          onRetry={refetch}
          getRowId={(row) => row.id}
          emptyMessage="No analytic accounts yet — add your first project or cost centre."
        />
      ) : (
        <KanbanGrid
          items={data?.items ?? []}
          loading={loading}
          error={error ? { message: error.message } : null}
          onRetry={refetch}
          getItemId={(row) => row.id}
          onCardClick={(row) => setMode({ kind: "edit", analytic: row })}
          emptyMessage="No analytic accounts yet."
          renderCard={(row) => <p className="font-medium text-text_primary">{row.name}</p>}
        />
      )}
    </div>
  );
}

function AnalyticForm({
  analytic,
  onBack,
  onSaved,
}: {
  analytic: AnalyticAccount | null;
  onBack: () => void;
  onSaved: () => void;
}) {
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<AnalyticFormValues>({
    resolver: zodResolver(analyticSchema),
    defaultValues: { name: analytic?.name ?? "" },
  });

  async function onSubmit(values: AnalyticFormValues) {
    try {
      if (analytic) {
        await api.put<AnalyticAccount>(`/analytic-accounts/${analytic.id}`, values);
        toast({ title: "Analytic account updated" });
      } else {
        await api.post<AnalyticAccount>("/analytic-accounts", values);
        toast({ title: "Analytic account created" });
      }
      onSaved();
    } catch (e) {
      const apiError = normaliseError(e);
      const handled = applyServerErrors(apiError, setError, { NAME_TAKEN: "name" });
      if (!handled) {
        toast({
          variant: "destructive",
          title: "Could not save analytic account",
          description: apiError.message,
        });
      }
    }
  }

  return (
    <FormShell
      title={analytic ? `Edit ${analytic.name}` : "New Analytic Account"}
      onBack={onBack}
      actions={[
        { label: "Cancel", variant: "outline", onClick: onBack },
        {
          label: isSubmitting ? "Saving..." : "Save",
          onClick: handleSubmit(onSubmit),
          disabled: isSubmitting,
        },
      ]}
    >
      <form onSubmit={handleSubmit(onSubmit)} noValidate className="max-w-sm">
        <Label htmlFor="name" required>Name</Label>
        <Input id="name" {...register("name")} />
        <FieldError message={errors.name?.message} />
      </form>
    </FormShell>
  );
}
