import { useEffect, useState } from "react";
import { Controller, useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Plus } from "lucide-react";
import { DataTable, type DataTableColumn } from "@/components/shared/DataTable";
import { FormShell } from "@/components/shared/FormShell";
import { StatusBadge } from "@/components/shared/StatusBadge";
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
import { applyServerErrors } from "@/lib/form-errors";
import { toast } from "@/hooks/use-toast";
import type { Account, AccountGroup, AccountInput, AccountType, Page } from "@/types/api";

const PAGE_SIZE = 20;

// Mirrors backend enums.ACCOUNT_TYPES_BY_GROUP — an Income account filed under
// the Balance Sheet would silently corrupt both reports (SPEC.md §7.4), so the
// type dropdown only ever offers types legal for the chosen group. The server
// and the DB CHECK constraint remain the authority.
const TYPES_BY_GROUP: Record<AccountGroup, AccountType[]> = {
  balance_sheet: ["asset", "liability", "bank", "capital", "cash"],
  profit_and_loss: ["income", "expense", "other_expense"],
};

const GROUP_LABELS: Record<AccountGroup, string> = {
  balance_sheet: "Balance Sheet",
  profit_and_loss: "Profit and Loss",
};

const TYPE_LABELS: Record<AccountType, string> = {
  asset: "Asset",
  liability: "Liability",
  bank: "Bank",
  capital: "Capital",
  cash: "Cash",
  income: "Income",
  expense: "Expense",
  other_expense: "Other Expense",
};

const accountSchema = z
  .object({
    code: z.string().trim().min(1, "Code is required").max(20),
    name: z.string().trim().min(1, "Name is required").max(150),
    account_group: z.enum(["balance_sheet", "profit_and_loss"]),
    account_type: z.enum([
      "asset",
      "liability",
      "bank",
      "capital",
      "cash",
      "income",
      "expense",
      "other_expense",
    ]),
  })
  .refine((data) => TYPES_BY_GROUP[data.account_group].includes(data.account_type), {
    message: "This account type is not valid for the selected group",
    path: ["account_type"],
  });
type AccountFormValues = z.infer<typeof accountSchema>;

type Mode = { kind: "list" } | { kind: "create" } | { kind: "edit"; account: Account };

export default function ChartOfAccounts() {
  const [mode, setMode] = useState<Mode>({ kind: "list" });
  const [page, setPage] = useState(1);
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");
  const [includeArchived, setIncludeArchived] = useState(false);

  useEffect(() => {
    const timer = setTimeout(() => {
      setSearch(searchInput);
      setPage(1);
    }, 400);
    return () => clearTimeout(timer);
  }, [searchInput]);

  const query = new URLSearchParams({
    page: String(page),
    page_size: String(PAGE_SIZE),
    include_archived: String(includeArchived),
  });
  if (search) query.set("search", search);
  const path = `/accounts?${query.toString()}`;

  const { data, loading, error, refetch } = useApi<Page<Account>>(path, [path]);

  const columns: DataTableColumn<Account>[] = [
    { key: "code", header: "Code" },
    { key: "name", header: "Name" },
    {
      key: "account_group",
      header: "Group",
      render: (row) => GROUP_LABELS[row.account_group],
    },
    {
      key: "account_type",
      header: "Type",
      render: (row) => TYPE_LABELS[row.account_type],
    },
    {
      key: "is_archived",
      header: "Status",
      render: (row) => (row.is_archived ? <StatusBadge status="cancelled" /> : null),
    },
  ];

  async function handleSaved() {
    setMode({ kind: "list" });
    await refetch();
  }

  if (mode.kind !== "list") {
    return (
      <AccountForm
        key={mode.kind === "edit" ? mode.account.id : "new"}
        account={mode.kind === "edit" ? mode.account : null}
        onBack={() => setMode({ kind: "list" })}
        onSaved={handleSaved}
      />
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-text_primary">Chart of Accounts</h1>
          <p className="text-sm text-text_secondary">
            Every ledger account. Accounts are archived, never deleted — posted entries
            reference them.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            type="button"
            variant="outline"
            onClick={() => {
              setIncludeArchived((prev) => !prev);
              setPage(1);
            }}
          >
            {includeArchived ? "Hide archived" : "Show archived"}
          </Button>
          <Button type="button" onClick={() => setMode({ kind: "create" })}>
            <Plus className="mr-2 h-4 w-4" />
            New Account
          </Button>
        </div>
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
        onRowClick={(row) => setMode({ kind: "edit", account: row })}
        searchValue={searchInput}
        onSearchChange={setSearchInput}
        onRetry={refetch}
        getRowId={(row) => row.id}
        emptyMessage="No accounts yet — seed the chart of accounts or add one."
      />
    </div>
  );
}

function AccountForm({
  account,
  onBack,
  onSaved,
}: {
  account: Account | null;
  onBack: () => void;
  onSaved: () => void;
}) {
  const {
    register,
    handleSubmit,
    control,
    watch,
    setValue,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<AccountFormValues>({
    resolver: zodResolver(accountSchema),
    defaultValues: {
      code: account?.code ?? "",
      name: account?.name ?? "",
      account_group: account?.account_group ?? "balance_sheet",
      account_type: account?.account_type ?? "asset",
    },
  });

  const selectedGroup = watch("account_group");
  const [archiving, setArchiving] = useState(false);

  async function onSubmit(values: AccountFormValues) {
    try {
      const body: AccountInput = values;
      if (account) {
        await api.put<Account>(`/accounts/${account.id}`, body);
        toast({ title: "Account updated" });
      } else {
        await api.post<Account>("/accounts", body);
        toast({ title: "Account created" });
      }
      onSaved();
    } catch (e) {
      const apiError = normaliseError(e);
      if (!applyServerErrors(apiError, setError)) {
        toast({
          variant: "destructive",
          title: "Could not save account",
          description: apiError.message,
        });
      }
    }
  }

  async function handleArchive() {
    if (!account) return;
    setArchiving(true);
    try {
      await api.post<Account>(`/accounts/${account.id}/archive`);
      toast({ title: "Account archived" });
      onSaved();
    } catch (e) {
      toast({
        variant: "destructive",
        title: "Could not archive account",
        description: normaliseError(e).message,
      });
    } finally {
      setArchiving(false);
    }
  }

  const actions = [
    { label: "Cancel", variant: "outline" as const, onClick: onBack },
    ...(account && !account.is_archived
      ? [
          {
            label: archiving ? "Archiving..." : "Archive",
            variant: "outline" as const,
            onClick: handleArchive,
            disabled: archiving,
          },
        ]
      : []),
    {
      label: isSubmitting ? "Saving..." : "Save",
      onClick: handleSubmit(onSubmit),
      disabled: isSubmitting,
    },
  ];

  return (
    <FormShell
      title={account ? `Edit ${account.name}` : "New Account"}
      onBack={onBack}
      actions={actions}
    >
      <form
        onSubmit={handleSubmit(onSubmit)}
        noValidate
        className="grid grid-cols-1 gap-4 sm:grid-cols-2"
      >
        <div>
          <Label htmlFor="code">Code</Label>
          <Input id="code" {...register("code")} />
          {errors.code && <p className="mt-1 text-xs text-danger">{errors.code.message}</p>}
        </div>

        <div>
          <Label htmlFor="name">Name</Label>
          <Input id="name" {...register("name")} />
          {errors.name && <p className="mt-1 text-xs text-danger">{errors.name.message}</p>}
        </div>

        <div>
          <Label htmlFor="account_group">Group</Label>
          <Controller
            control={control}
            name="account_group"
            render={({ field }) => (
              <Select
                value={field.value}
                onValueChange={(value) => {
                  const group = value as AccountGroup;
                  field.onChange(group);
                  // Keep type consistent with the newly chosen group.
                  if (!TYPES_BY_GROUP[group].includes(watch("account_type"))) {
                    setValue("account_type", TYPES_BY_GROUP[group][0]);
                  }
                }}
              >
                <SelectTrigger id="account_group">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="balance_sheet">Balance Sheet</SelectItem>
                  <SelectItem value="profit_and_loss">Profit and Loss</SelectItem>
                </SelectContent>
              </Select>
            )}
          />
        </div>

        <div>
          <Label htmlFor="account_type">Type</Label>
          <Controller
            control={control}
            name="account_type"
            render={({ field }) => (
              <Select value={field.value} onValueChange={field.onChange}>
                <SelectTrigger id="account_type">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {TYPES_BY_GROUP[selectedGroup].map((type) => (
                    <SelectItem key={type} value={type}>
                      {TYPE_LABELS[type]}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
          />
          {errors.account_type && (
            <p className="mt-1 text-xs text-danger">{errors.account_type.message}</p>
          )}
        </div>
      </form>
    </FormShell>
  );
}
