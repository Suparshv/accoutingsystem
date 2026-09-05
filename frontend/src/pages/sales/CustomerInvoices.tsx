import { useEffect, useState } from "react";
import { useLocation } from "react-router-dom";
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
  CustomerInvoice,
  CustomerInvoiceDetail,
  Page,
  Partner,
  Product,
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

type Mode = { kind: "list" } | { kind: "create" } | { kind: "edit"; invoiceId: number };

export default function CustomerInvoices() {
  // "View Invoice" on the Sales Order page navigates here with the invoice's
  // id in router state, so a specific invoice opens directly instead of
  // landing on the list (mirrors the `from` pattern in RequireAuth/Login).
  const location = useLocation();
  const openInvoiceId = (location.state as { openInvoiceId?: number } | null)
    ?.openInvoiceId;
  const [mode, setMode] = useState<Mode>(
    openInvoiceId ? { kind: "edit", invoiceId: openInvoiceId } : { kind: "list" },
  );
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
  const path = `/customer-invoices?${query.toString()}`;

  const { data, loading, error, refetch } = useApi<Page<CustomerInvoice>>(path, [path]);

  const columns: DataTableColumn<CustomerInvoice>[] = [
    { key: "number", header: "Number" },
    { key: "customer_name", header: "Customer", render: (row) => row.customer_name ?? "—" },
    { key: "invoice_date", header: "Date" },
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
      <CustomerInvoiceForm
        key={mode.kind === "edit" ? mode.invoiceId : "new"}
        invoiceId={mode.kind === "edit" ? mode.invoiceId : null}
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
          <h1 className="text-2xl font-semibold text-text_primary">Customer Invoices</h1>
          <p className="text-sm text-text_secondary">
            Confirming an invoice posts it to the ledger.
          </p>
        </div>
        <Button type="button" onClick={() => setMode({ kind: "create" })}>
          <Plus className="mr-2 h-4 w-4" />
          New Invoice
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
        onRowClick={(row) => setMode({ kind: "edit", invoiceId: row.id })}
        searchValue={searchInput}
        onSearchChange={setSearchInput}
        onRetry={refetch}
        getRowId={(row) => row.id}
        emptyMessage="No invoices yet — create one, or confirm a sales order."
      />
    </div>
  );
}

function CustomerInvoiceForm({
  invoiceId,
  onBack,
  onSaved,
}: {
  invoiceId: number | null;
  onBack: () => void;
  onSaved: () => void;
}) {
  const detailPath = invoiceId ? `/customer-invoices/${invoiceId}` : null;
  const {
    data: invoice,
    loading,
    error,
    refetch,
  } = useApi<CustomerInvoiceDetail>(detailPath ?? "/customer-invoices/__none__", [
    detailPath ?? "",
  ]);

  const { data: partners } = useApi<Page<Partner>>("/partners?page=1&page_size=100", []);
  const { data: products } = useApi<Page<Product>>("/products?page=1&page_size=100", []);
  const { data: accounts } = useApi<Page<Account>>(
    "/accounts?page=1&page_size=100&account_type=income",
    [],
  );
  const { data: analytics } = useApi<Page<AnalyticAccount>>(
    "/analytic-accounts?page=1&page_size=100",
    [],
  );

  const [customerId, setCustomerId] = useState("");
  const [invoiceDate, setInvoiceDate] = useState(today());
  const [dueDate, setDueDate] = useState("");
  const [reference, setReference] = useState("");
  const [lines, setLines] = useState<DraftLine[]>([{ ...BLANK_LINE }]);
  const [busy, setBusy] = useState(false);
  const [payOpen, setPayOpen] = useState(false);

  useEffect(() => {
    if (!invoice) return;
    setCustomerId(String(invoice.customer_id));
    setInvoiceDate(invoice.invoice_date);
    setDueDate(invoice.due_date ?? "");
    setReference(invoice.invoice_reference ?? "");
    setLines(
      invoice.lines.map((line) => ({
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
  }, [invoice]);

  const isDraft = !invoice || invoice.state === "draft";

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
              unit_price: product?.sales_price ?? row.unit_price,
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
            <SelectValue placeholder="Sales Income A/c" />
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
      customer_id: Number(customerId),
      invoice_date: invoiceDate,
      due_date: dueDate || null,
      invoice_reference: reference.trim() || null,
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

  if (invoiceId && loading) {
    return <p className="text-sm text-text_secondary">Loading invoice...</p>;
  }

  if (invoiceId && error) {
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

  const canPay =
    invoice && invoice.state === "confirmed" && invoice.payment_status !== "paid";

  const actions = [
    { label: "Back", variant: "outline" as const, onClick: onBack },
    ...(isDraft
      ? [
          {
            label: "Save",
            variant: "outline" as const,
            disabled: busy || !customerId,
            onClick: () =>
              run("Invoice saved", () =>
                invoice
                  ? api.put(`/customer-invoices/${invoice.id}`, toBody())
                  : api.post("/customer-invoices", toBody()),
              ),
          },
        ]
      : []),
    ...(invoice && invoice.state === "draft"
      ? [
          {
            label: "Confirm",
            disabled: busy,
            onClick: () =>
              run("Invoice confirmed and journal entry posted", () =>
                api.post(`/customer-invoices/${invoice.id}/confirm`),
              ),
          },
        ]
      : []),
    ...(canPay
      ? [{ label: "Register Payment", disabled: busy, onClick: () => setPayOpen(true) }]
      : []),
    ...(invoice && invoice.state !== "cancelled"
      ? [
          {
            label: "Cancel Invoice",
            variant: "outline" as const,
            disabled: busy,
            onClick: () =>
              run("Invoice cancelled", () =>
                api.post(`/customer-invoices/${invoice.id}/cancel`),
              ),
          },
        ]
      : []),
  ];

  return (
    <FormShell
      title={invoice ? invoice.number : "New Invoice"}
      state={invoice?.state}
      variant="document"
      onBack={onBack}
      actions={actions}
    >
      <div className="flex flex-col gap-6">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <div>
            <Label htmlFor="customer_id">Customer</Label>
            <Select value={customerId} onValueChange={setCustomerId} disabled={!isDraft}>
              <SelectTrigger id="customer_id">
                <SelectValue placeholder="Select customer" />
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
            <Label htmlFor="invoice_date">Invoice Date</Label>
            <Input
              id="invoice_date"
              type="date"
              value={invoiceDate}
              disabled={!isDraft}
              onChange={(e) => setInvoiceDate(e.target.value)}
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
            <Label htmlFor="invoice_reference">Reference</Label>
            <Input
              id="invoice_reference"
              value={reference}
              disabled={!isDraft}
              onChange={(e) => setReference(e.target.value)}
              placeholder="Optional"
            />
          </div>
        </div>

        {invoice && (
          <dl className="grid grid-cols-2 gap-4 rounded border border-border bg-surface p-4 text-sm sm:grid-cols-4">
            <div>
              <dt className="text-text_secondary">Total</dt>
              <dd>
                <MoneyDisplay value={invoice.total_amount} />
              </dd>
            </div>
            <div>
              <dt className="text-text_secondary">Paid</dt>
              <dd>
                <MoneyDisplay value={invoice.amount_paid} />
              </dd>
            </div>
            <div>
              <dt className="text-text_secondary">Due</dt>
              <dd>
                <MoneyDisplay value={invoice.amount_due} />
              </dd>
            </div>
            <div>
              <dt className="text-text_secondary">Payment</dt>
              <dd>
                <StatusBadge status={invoice.payment_status as Status} />
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
          Totals update automatically when you save. Confirming records the invoice in
          the ledger.
        </p>
      </div>

      {invoice && (
        <PaymentDialog
          open={payOpen}
          onOpenChange={setPayOpen}
          paymentType="receive"
          partnerId={invoice.customer_id}
          partnerName={invoice.customer_name ?? "Customer"}
          amountDue={invoice.amount_due}
          invoiceId={invoice.id}
          onPaid={onSaved}
        />
      )}
    </FormShell>
  );
}
