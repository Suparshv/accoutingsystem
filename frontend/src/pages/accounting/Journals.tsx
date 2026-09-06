import { useEffect, useState } from "react";
import { Controller, useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Plus } from "lucide-react";
import { DataTable, type DataTableColumn } from "@/components/shared/DataTable";
import { FieldError } from "@/components/shared/FieldError";
import { FormShell } from "@/components/shared/FormShell";
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
import { useDebouncedValue } from "@/hooks/useDebouncedValue";
import { api, normaliseError } from "@/lib/api";
import { applyServerErrors } from "@/lib/form-errors";
import { toast } from "@/hooks/use-toast";
import type { Account, Journal, JournalType, Page } from "@/types/api";

const PAGE_SIZE = 20;

const JOURNAL_TYPE_LABELS: Record<JournalType, string> = {
  sales: "Sales",
  purchase: "Purchase",
  bank: "Bank",
  cash: "Cash",
};

const journalSchema = z.object({
  name: z.string().trim().min(1, "Name is required").max(100),
  journal_type: z.enum(["sales", "purchase", "bank", "cash"]),
  default_account_id: z.string().min(1, "A default account is required"),
});
type JournalFormValues = z.infer<typeof journalSchema>;

type Mode = { kind: "list" } | { kind: "create" };

export default function Journals() {
  const [mode, setMode] = useState<Mode>({ kind: "list" });
  const [page, setPage] = useState(1);
  const [searchInput, setSearchInput] = useState("");
  const search = useDebouncedValue(searchInput);

  // A new search term is a new result set, so it starts at page 1 again.
  useEffect(() => {
    setPage(1);
  }, [search]);

  const query = new URLSearchParams({ page: String(page), page_size: String(PAGE_SIZE) });
  if (search) query.set("search", search);
  const path = `/journals?${query.toString()}`;

  const { data, loading, error, refetch } = useApi<Page<Journal>>(path, [path]);
  // Accounts feed the "default account" dropdown and resolve the id -> name
  // shown in the list (the journals endpoint returns only default_account_id).
  const { data: accounts } = useApi<Page<Account>>("/accounts?page=1&page_size=100", []);

  const accountLabel = (id: number) => {
    const account = accounts?.items.find((a) => a.id === id);
    return account ? `${account.code} — ${account.name}` : String(id);
  };

  const columns: DataTableColumn<Journal>[] = [
    { key: "name", header: "Name" },
    {
      key: "journal_type",
      header: "Type",
      render: (row) => JOURNAL_TYPE_LABELS[row.journal_type],
    },
    {
      key: "default_account_id",
      header: "Default Account",
      render: (row) => accountLabel(row.default_account_id),
    },
  ];

  if (mode.kind === "create") {
    return (
      <JournalForm
        accounts={accounts?.items ?? []}
        onBack={() => setMode({ kind: "list" })}
        onSaved={async () => {
          setMode({ kind: "list" });
          await refetch();
        }}
      />
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-text_primary">Journals</h1>
          <p className="text-sm text-text_secondary">
            Groups entries by nature and supplies each one's default account.
          </p>
        </div>
        <Button type="button" onClick={() => setMode({ kind: "create" })}>
          <Plus className="mr-2 h-4 w-4" />
          New Journal
        </Button>
      </div>

      {/* Rows are not clickable: the backend exposes GET and POST for journals
          but no PUT, so there is nothing to open an edit form onto yet. */}
      <DataTable
        columns={columns}
        rows={data?.items ?? []}
        loading={loading}
        error={error ? { message: error.message } : null}
        page={page}
        pageSize={PAGE_SIZE}
        total={data?.total ?? 0}
        onPageChange={setPage}
        searchValue={searchInput}
        onSearchChange={setSearchInput}
        onRetry={refetch}
        getRowId={(row) => row.id}
        emptyMessage="No journals yet — add Sales, Purchase, Bank and Cash journals."
      />
    </div>
  );
}

function JournalForm({
  accounts,
  onBack,
  onSaved,
}: {
  accounts: Account[];
  onBack: () => void;
  onSaved: () => void;
}) {
  const {
    register,
    handleSubmit,
    control,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<JournalFormValues>({
    resolver: zodResolver(journalSchema),
    defaultValues: { name: "", journal_type: "sales", default_account_id: "" },
  });

  async function onSubmit(values: JournalFormValues) {
    try {
      await api.post<Journal>("/journals", {
        name: values.name.trim(),
        journal_type: values.journal_type,
        default_account_id: Number(values.default_account_id),
      });
      toast({ title: "Journal created" });
      onSaved();
    } catch (e) {
      const apiError = normaliseError(e);
      if (!applyServerErrors(apiError, setError)) {
        toast({
          variant: "destructive",
          title: "Could not save journal",
          description: apiError.message,
        });
      }
    }
  }

  return (
    <FormShell
      title="New Journal"
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
      <form
        onSubmit={handleSubmit(onSubmit)}
        noValidate
        className="grid grid-cols-1 gap-4 sm:grid-cols-2"
      >
        <div>
          <Label htmlFor="name" required>Name</Label>
          <Input id="name" {...register("name")} />
          <FieldError message={errors.name?.message} />
        </div>

        <div>
          <Label htmlFor="journal_type" required>Type</Label>
          <Controller
            control={control}
            name="journal_type"
            render={({ field }) => (
              <Select value={field.value} onValueChange={field.onChange}>
                <SelectTrigger id="journal_type">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {(Object.keys(JOURNAL_TYPE_LABELS) as JournalType[]).map((type) => (
                    <SelectItem key={type} value={type}>
                      {JOURNAL_TYPE_LABELS[type]}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
          />
          <FieldError message={errors.journal_type?.message} />
        </div>

        <div className="sm:col-span-2">
          <Label htmlFor="default_account_id" required>Default Account</Label>
          <Controller
            control={control}
            name="default_account_id"
            render={({ field }) => (
              <Select value={field.value} onValueChange={field.onChange}>
                <SelectTrigger id="default_account_id">
                  <SelectValue placeholder="Select an account" />
                </SelectTrigger>
                <SelectContent>
                  {accounts.map((account) => (
                    <SelectItem key={account.id} value={String(account.id)}>
                      {account.code} — {account.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
          />
          <FieldError message={errors.default_account_id?.message} />
          <p className="mt-1 text-xs text-text_secondary">
            For Bank and Cash journals this is the account debited on receipt and credited
            on payment.
          </p>
        </div>
      </form>
    </FormShell>
  );
}
