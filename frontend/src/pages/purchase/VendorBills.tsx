import { useEffect, useState } from "react";
import { Plus } from "lucide-react";
import { DataTable, type DataTableColumn } from "@/components/shared/DataTable";
import { FormShell } from "@/components/shared/FormShell";
import { LineItemsTable, type LineItemColumn } from "@/components/shared/LineItemsTable";
import { MoneyDisplay } from "@/components/shared/MoneyDisplay";
import { MoneyInput } from "@/components/shared/MoneyInput";
import { PaymentDialog } from "@/components/shared/PaymentDialog";
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
  Account,
  AnalyticAccount,
  Page,
  Partner,
  Product,
  VendorBill,
  VendorBillDetail,
} from "@/types/api";

const PAGE_SIZE = 20;
const NO_ANALYTIC = "none";

type DraftLine = {
  product_id: string;
  account_id: string;
  analytic_account_id: string;
  quantity: string;
  unit_price: string;
  line_total: string;
};

const BLANK_LINE: DraftLine = {
  product_id: "",
  account_id: "",
  analytic_account_id: NO_ANALYTIC,
  quantity: "1",
  unit_price: "0.00",
  line_total: "0.00",
};

function today(): string {
  return new Date().toISOString().slice(0, 10);
}

type Mode = { kind: "list" } | { kind: "create" } | { kind: "edit"; billId: number };

export default function VendorBills() {
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
  const path = `/vendor-bills?${query.toString()}`;

  const { data, loading, error, refetch } = useApi<Page<VendorBill>>(path, [path]);

  const columns: DataTableColumn<VendorBill>[] = [
    { key: "number", header: "Number" },
    { key: "vendor_name", header: "Vendor", render: (row) => row.vendor_name ?? "—" },
    { key: "bill_date", header: "Date" },
    {
      key: "total_amount",
      header: "Total",
      align: "right",
      render: (row) => <MoneyDisplay value={row.total_amount} />,
    },
    {
      key: "amount_due",
      header: "Due",
      align: "right",
      render: (row) => <MoneyDisplay value={row.amount_due} />,
    },
    {
      key: "payment_status",
      header: "Payment",
      render: (row) => <StatusBadge status={row.payment_status as Status} />,
    },
    {
      key: "state",
      header: "Status",
      render: (row) => <StatusBadge status={row.state as Status} />,
    },
  ];

  if (mode.kind !== "list") {
    return (
      <VendorBillForm
        key={mode.kind === "edit" ? mode.billId : "new"}
        billId={mode.kind === "edit" ? mode.billId : null}
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
          <h1 className="text-2xl font-semibold text-text_primary">Vendor Bills</h1>
          <p className="text-sm text-text_secondary">
            Confirming a bill posts its journal entry — both happen together or not at all.
          </p>
        </div>
        <Button type="button" onClick={() => setMode({ kind: "create" })}>
          <Plus className="mr-2 h-4 w-4" />
          New Bill
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
        onRowClick={(row) => setMode({ kind: "edit", billId: row.id })}
        searchValue={searchInput}
        onSearchChange={setSearchInput}
        onRetry={refetch}
        getRowId={(row) => row.id}
        emptyMessage="No vendor bills yet — create one, or confirm a purchase order."
      />
    </div>
  );
}

function VendorBillForm({
  billId,
  onBack,
  onSaved,
}: {
  billId: number | null;
  onBack: () => void;
  onSaved: () => void;
}) {
  const detailPath = billId ? `/vendor-bills/${billId}` : null;
  const {
    data: bill,
    loading,
    error,
    refetch,
  } = useApi<VendorBillDetail>(detailPath ?? "/vendor-bills/__none__", [detailPath ?? ""]);

  const { data: partners } = useApi<Page<Partner>>("/partners?page=1&page_size=100", []);
  const { data: products } = useApi<Page<Product>>("/products?page=1&page_size=100", []);
  const { data: accounts } = useApi<Page<Account>>(
    "/accounts?page=1&page_size=100&account_type=expense",
    [],
  );
  const { data: analytics } = useApi<Page<AnalyticAccount>>(
    "/analytic-accounts?page=1&page_size=100",
    [],
  );

  const [vendorId, setVendorId] = useState("");
  const [billDate, setBillDate] = useState(today());
  const [dueDate, setDueDate] = useState("");
  const [reference, setReference] = useState("");
  const [lines, setLines] = useState<DraftLine[]>([{ ...BLANK_LINE }]);
  const [busy, setBusy] = useState(false);
  const [payOpen, setPayOpen] = useState(false);

  useEffect(() => {
    if (!bill) return;
    setVendorId(String(bill.vendor_id));
    setBillDate(bill.bill_date);
    setDueDate(bill.due_date ?? "");
    setReference(bill.bill_reference ?? "");
    setLines(
      bill.lines.map((line) => ({
        product_id: String(line.product_id),
        account_id: line.account_id ? String(line.account_id) : "",
        analytic_account_id: line.analytic_account_id
          ? String(line.analytic_account_id)
          : NO_ANALYTIC,
        quantity: line.quantity,
        unit_price: line.unit_price,
        line_total: line.line_total,
      })),
    );
  }, [bill]);

  const isDraft = !bill || bill.state === "draft";

  function updateLine(index: number, patch: Partial<DraftLine>) {
    setLines((prev) => prev.map((line, i) => (i === index ? { ...line, ...patch } : line)));
  }

  const columns: LineItemColumn<DraftLine>[] = [
    {
      key: "product_id",
      header: "Product",
      render: (row, index) => (
        <Select
          value={row.product_id}
          disabled={!isDraft}
          onValueChange={(value) => {
            const product = products?.items.find((p) => String(p.id) === value);
            updateLine(index, {
              product_id: value,
              unit_price: product?.cost_price ?? row.unit_price,
            });
          }}
        >
          <SelectTrigger className="min-w-[10rem]">
            <SelectValue placeholder="Select product" />
          </SelectTrigger>
          <SelectContent>
            {(products?.items ?? []).map((product) => (
              <SelectItem key={product.id} value={String(product.id)}>
                {product.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      ),
    },
    {
      key: "account_id",
      header: "Account",
      render: (row, index) => (
        <Select
          value={row.account_id}
          disabled={!isDraft}
          onValueChange={(value) => updateLine(index, { account_id: value })}
        >
          <SelectTrigger className="min-w-[10rem]">
            <SelectValue placeholder="Purchase Expense A/c" />
          </SelectTrigger>
          <SelectContent>
            {(accounts?.items ?? []).map((account) => (
              <SelectItem key={account.id} value={String(account.id)}>
                {account.code} — {account.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      ),
    },
    {
      key: "analytic_account_id",
      header: "Analytic",
      render: (row, index) => (
        <Select
          value={row.analytic_account_id}
          disabled={!isDraft}
          onValueChange={(value) => updateLine(index, { analytic_account_id: value })}
        >
          <SelectTrigger className="min-w-[9rem]">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={NO_ANALYTIC}>None</SelectItem>
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
      key: "quantity",
      header: "Qty",
      align: "right",
      render: (row, index) => (
        <Input
          value={row.quantity}
          disabled={!isDraft}
          inputMode="decimal"
          className="w-20 text-right tabular-nums"
          onChange={(e) => updateLine(index, { quantity: e.target.value })}
        />
      ),
    },
    {
      key: "unit_price",
      header: "Unit Price",
      align: "right",
      render: (row, index) => (
        <MoneyInput
          value={row.unit_price}
          disabled={!isDraft}
          onChange={(value) => updateLine(index, { unit_price: value })}
        />
      ),
    },
    {
      key: "line_total",
      header: "Line Total",
      align: "right",
      render: (row) => <MoneyDisplay value={row.line_total} />,
    },
  ];

  function toBody() {
    return {
      vendor_id: Number(vendorId),
      bill_date: billDate,
      due_date: dueDate || null,
      bill_reference: reference.trim() || null,
      lines: lines
        .filter((line) => line.product_id)
        .map((line) => ({
          product_id: Number(line.product_id),
          account_id: line.account_id ? Number(line.account_id) : null,
          analytic_account_id:
            line.analytic_account_id === NO_ANALYTIC
              ? null
              : Number(line.analytic_account_id),
          quantity: line.quantity,
          unit_price: line.unit_price,
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

  if (billId && loading) {
    return <p className="text-sm text-text_secondary">Loading bill...</p>;
  }

  if (billId && error) {
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

  const canPay = bill && bill.state === "confirmed" && bill.payment_status !== "paid";

  const actions = [
    { label: "Back", variant: "outline" as const, onClick: onBack },
    ...(isDraft
      ? [
          {
            label: "Save",
            variant: "outline" as const,
            disabled: busy || !vendorId,
            onClick: () =>
              run("Bill saved", () =>
                bill
                  ? api.put(`/vendor-bills/${bill.id}`, toBody())
                  : api.post("/vendor-bills", toBody()),
              ),
          },
        ]
      : []),
    ...(bill && bill.state === "draft"
      ? [
          {
            label: "Confirm",
            disabled: busy,
            onClick: () =>
              run("Bill confirmed and journal entry posted", () =>
                api.post(`/vendor-bills/${bill.id}/confirm`),
              ),
          },
        ]
      : []),
    ...(canPay
      ? [{ label: "Register Payment", disabled: busy, onClick: () => setPayOpen(true) }]
      : []),
    ...(bill && bill.state !== "cancelled"
      ? [
          {
            label: "Cancel Bill",
            variant: "outline" as const,
            disabled: busy,
            onClick: () =>
              run("Bill cancelled", () => api.post(`/vendor-bills/${bill.id}/cancel`)),
          },
        ]
      : []),
  ];

  return (
    <FormShell
      title={bill ? bill.number : "New Vendor Bill"}
      state={bill?.state}
      onBack={onBack}
      actions={actions}
    >
      <div className="flex flex-col gap-6">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <div>
            <Label htmlFor="vendor_id">Vendor</Label>
            <Select value={vendorId} onValueChange={setVendorId} disabled={!isDraft}>
              <SelectTrigger id="vendor_id">
                <SelectValue placeholder="Select vendor" />
              </SelectTrigger>
              <SelectContent>
                {(partners?.items ?? []).map((partner) => (
                  <SelectItem key={partner.id} value={String(partner.id)}>
                    {partner.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div>
            <Label htmlFor="bill_date">Bill Date</Label>
            <Input
              id="bill_date"
              type="date"
              value={billDate}
              disabled={!isDraft}
              onChange={(e) => setBillDate(e.target.value)}
            />
          </div>

          <div>
            <Label htmlFor="due_date">Due Date</Label>
            <Input
              id="due_date"
              type="date"
              value={dueDate}
              disabled={!isDraft}
              onChange={(e) => setDueDate(e.target.value)}
            />
          </div>

          <div>
            <Label htmlFor="bill_reference">Bill Reference</Label>
            <Input
              id="bill_reference"
              value={reference}
              disabled={!isDraft}
              onChange={(e) => setReference(e.target.value)}
              placeholder="Vendor's own number"
            />
          </div>
        </div>

        {bill && (
          <dl className="grid grid-cols-2 gap-4 rounded border border-border bg-surface p-4 text-sm sm:grid-cols-4">
            <div>
              <dt className="text-text_secondary">Total</dt>
              <dd>
                <MoneyDisplay value={bill.total_amount} />
              </dd>
            </div>
            <div>
              <dt className="text-text_secondary">Paid</dt>
              <dd>
                <MoneyDisplay value={bill.amount_paid} />
              </dd>
            </div>
            <div>
              <dt className="text-text_secondary">Due</dt>
              <dd>
                <MoneyDisplay value={bill.amount_due} />
              </dd>
            </div>
            <div>
              <dt className="text-text_secondary">Payment</dt>
              <dd>
                <StatusBadge status={bill.payment_status as Status} />
              </dd>
            </div>
          </dl>
        )}

        <LineItemsTable
          rows={lines}
          columns={columns}
          getLineTotal={(row) => row.line_total}
          addLabel="Add line"
          onAddRow={() => setLines((prev) => [...prev, { ...BLANK_LINE }])}
          onRemoveRow={(index) => setLines((prev) => prev.filter((_, i) => i !== index))}
        />

        <p className="text-xs text-text_secondary">
          Line totals and the bill total are computed server-side on save (AGENTS.md R6).
          Confirming posts the journal entry atomically with the state change.
        </p>
      </div>

      {bill && (
        <PaymentDialog
          open={payOpen}
          onOpenChange={setPayOpen}
          paymentType="send"
          partnerId={bill.vendor_id}
          partnerName={bill.vendor_name ?? "Vendor"}
          amountDue={bill.amount_due}
          billId={bill.id}
          onPaid={onSaved}
        />
      )}
    </FormShell>
  );
}
