import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Plus } from "lucide-react";
import { DataTable, type DataTableColumn } from "@/components/shared/DataTable";
import { FieldError } from "@/components/shared/FieldError";
import { FormShell } from "@/components/shared/FormShell";
import { LineItemsTable, type LineItemColumn } from "@/components/shared/LineItemsTable";
import { MoneyDisplay } from "@/components/shared/MoneyDisplay";
import { MoneyInput } from "@/components/shared/MoneyInput";
import { QuantityInput } from "@/components/shared/QuantityInput";
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
import { useDebouncedValue } from "@/hooks/useDebouncedValue";
import { api, normaliseError } from "@/lib/api";
import { lineTotalOf } from "@/lib/money";
import { toast } from "@/hooks/use-toast";
import { hasErrors, requiredErrors } from "@/lib/validation";
import type {
  AnalyticAccount,
  Page,
  Partner,
  Product,
  PurchaseOrder,
  PurchaseOrderDetail,
} from "@/types/api";

const PAGE_SIZE = 20;
const NO_ANALYTIC = "none";

type DraftLine = {
  product_id: string;
  analytic_account_id: string;
  quantity: string;
  unit_price: string;
};

const BLANK_LINE: DraftLine = {
  product_id: "",
  analytic_account_id: NO_ANALYTIC,
  quantity: "1",
  unit_price: "0.00",
};

function today(): string {
  return new Date().toISOString().slice(0, 10);
}

type Mode = { kind: "list" } | { kind: "create" } | { kind: "edit"; orderId: number };

export default function PurchaseOrders() {
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
  const path = `/purchase-orders?${query.toString()}`;

  const { data, loading, error, refetch } = useApi<Page<PurchaseOrder>>(path, [path]);

  const columns: DataTableColumn<PurchaseOrder>[] = [
    { key: "number", header: "Number" },
    { key: "vendor_name", header: "Vendor", render: (row) => row.vendor_name ?? "—" },
    { key: "order_date", header: "Date" },
    {
      key: "total_amount",
      header: "Total",
      align: "right",
      render: (row) => <MoneyDisplay value={row.total_amount} />,
    },
    {
      key: "state",
      header: "Status",
      render: (row) => <StatusBadge status={row.state as Status} />,
    },
  ];

  if (mode.kind !== "list") {
    return (
      <PurchaseOrderForm
        key={mode.kind === "edit" ? mode.orderId : "new"}
        orderId={mode.kind === "edit" ? mode.orderId : null}
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
          <h1 className="text-2xl font-semibold text-text_primary">Purchase Orders</h1>
          <p className="text-sm text-text_secondary">
            A commitment to buy — produces no journal entry until it becomes a bill.
          </p>
        </div>
        <Button type="button" onClick={() => setMode({ kind: "create" })}>
          <Plus className="mr-2 h-4 w-4" />
          New Purchase Order
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
        onRowClick={(row) => setMode({ kind: "edit", orderId: row.id })}
        searchValue={searchInput}
        onSearchChange={setSearchInput}
        onRetry={refetch}
        getRowId={(row) => row.id}
        emptyMessage="No purchase orders yet — create your first one."
      />
    </div>
  );
}

function PurchaseOrderForm({
  orderId,
  onBack,
  onSaved,
}: {
  orderId: number | null;
  onBack: () => void;
  onSaved: () => void;
}) {
  const navigate = useNavigate();
  const detailPath = orderId ? `/purchase-orders/${orderId}` : null;
  const {
    data: order,
    loading,
    error,
    refetch,
  } = useApi<PurchaseOrderDetail>(detailPath ?? "/purchase-orders/__none__", [
    detailPath ?? "",
  ]);

  const { data: partners } = useApi<Page<Partner>>("/partners?page=1&page_size=100", []);
  const { data: products } = useApi<Page<Product>>("/products?page=1&page_size=100", []);
  const { data: analytics } = useApi<Page<AnalyticAccount>>(
    "/analytic-accounts?page=1&page_size=100",
    [],
  );

  const [vendorId, setVendorId] = useState("");
  const [orderDate, setOrderDate] = useState(today());
  const [lines, setLines] = useState<DraftLine[]>([{ ...BLANK_LINE }]);
  const [busy, setBusy] = useState(false);
  // Errors stay hidden until the first save attempt, so a blank new order
  // is not red before it has been touched.
  const [showErrors, setShowErrors] = useState(false);

  const errors = requiredErrors({
    vendor_id: [vendorId, "Vendor"],
    order_date: [orderDate, "Order date"],
  });
  if (lines.every((line) => !line.product_id)) {
    errors.lines = "At least one line with a product is required";
  }
  const fieldError = (name: string) => (showErrors ? errors[name] : undefined);

  useEffect(() => {
    if (!order) return;
    setVendorId(String(order.vendor_id));
    setOrderDate(order.order_date);
    setLines(
      order.lines.map((line) => ({
        product_id: String(line.product_id),
        analytic_account_id: line.analytic_account_id
          ? String(line.analytic_account_id)
          : NO_ANALYTIC,
        quantity: line.quantity,
        unit_price: line.unit_price,
      })),
    );
  }, [order]);

  const isDraft = !order || order.state === "draft";

  function updateLine(index: number, patch: Partial<DraftLine>) {
    setLines((prev) => prev.map((line, i) => (i === index ? { ...line, ...patch } : line)));
  }

  // Derived on every render, never stored: this is what makes the line
  // total and the footer total follow a quantity edit, a price edit, an
  // added row and a removed row without anything having to remember to
  // recompute them. The server recomputes it again on save (R6).
  const lineTotal = (row: DraftLine) => lineTotalOf(row.quantity, row.unit_price);

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
              // Purchases prefill from cost price, sales from sales price.
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
        <QuantityInput
          value={row.quantity}
          disabled={!isDraft}
          onChange={(value) => updateLine(index, { quantity: value })}
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
      render: (row) => <MoneyDisplay value={lineTotal(row)} />,
    },
  ];

  function toBody() {
    return {
      vendor_id: Number(vendorId),
      order_date: orderDate,
      lines: lines
        .filter((line) => line.product_id)
        .map((line) => ({
          product_id: Number(line.product_id),
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
        title: "Action failed",
        description: normaliseError(e).message,
      });
    } finally {
      setBusy(false);
    }
  }

  if (orderId && loading) {
    return <p className="text-sm text-text_secondary">Loading purchase order...</p>;
  }

  if (orderId && error) {
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
            disabled: busy,
            onClick: () => {
              setShowErrors(true);
              if (hasErrors(errors)) return;
              run("Purchase order saved", () =>
                order
                  ? api.put(`/purchase-orders/${order.id}`, toBody())
                  : api.post("/purchase-orders", toBody()),
              );
            },
          },
        ]
      : []),
    ...(order && order.state === "draft"
      ? [
          {
            label: "Confirm",
            disabled: busy,
            onClick: () =>
              run("Purchase order confirmed", () =>
                api.post(`/purchase-orders/${order.id}/confirm`),
              ),
          },
        ]
      : []),
    ...(order && order.state === "confirmed"
      ? [
          order.bill_id
            ? {
                label: "View Bill",
                variant: "outline" as const,
                onClick: () =>
                  navigate("/purchase/bills", {
                    state: { openBillId: order.bill_id },
                  }),
              }
            : {
                label: "Create Bill",
                disabled: busy,
                onClick: () =>
                  run("Vendor bill created", () =>
                    api.post(`/purchase-orders/${order.id}/create-bill`),
                  ),
              },
          {
            label: "Cancel Order",
            variant: "outline" as const,
            disabled: busy,
            onClick: () =>
              run("Purchase order cancelled", () =>
                api.post(`/purchase-orders/${order.id}/cancel`),
              ),
          },
        ]
      : []),
  ];

  return (
    <FormShell
      title={order ? order.number : "New Purchase Order"}
      state={order?.state}
      variant="document"
      onBack={onBack}
      actions={actions}
    >
      <div className="flex flex-col gap-6">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div>
            <Label htmlFor="vendor_id" required>
              Vendor
            </Label>
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
            <FieldError message={fieldError("vendor_id")} />
          </div>

          <div>
            <Label htmlFor="order_date" required>
              Order Date
            </Label>
            <Input
              id="order_date"
              type="date"
              value={orderDate}
              disabled={!isDraft}
              onChange={(e) => setOrderDate(e.target.value)}
            />
            <FieldError message={fieldError("order_date")} />
          </div>
        </div>

        <LineItemsTable
          rows={lines}
          columns={columns}
          getLineTotal={lineTotal}
          addLabel="Add line"
          onAddRow={() => setLines((prev) => [...prev, { ...BLANK_LINE }])}
          onRemoveRow={(index) => setLines((prev) => prev.filter((_, i) => i !== index))}
          readOnly={!isDraft}
        />
        <FieldError message={fieldError("lines")} />

        <p className="text-xs text-text_secondary">
          Totals update automatically when you save.
        </p>
      </div>
    </FormShell>
  );
}
