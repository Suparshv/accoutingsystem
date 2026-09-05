import { useEffect, useState } from "react";
import { DataTable, type DataTableColumn } from "@/components/shared/DataTable";
import { MoneyDisplay } from "@/components/shared/MoneyDisplay";
import { StatusBadge, type Status } from "@/components/shared/StatusBadge";
import { useApi } from "@/hooks/useApi";
import type { Page, Payment, PaymentType } from "@/types/api";

const PAGE_SIZE = 20;

// One page serves both menu items — SPEC.md §7.8: Bill Payment and Invoice
// Payment are the same record with payment_type flipped. Payments are created
// from an invoice or bill via PaymentDialog, so this view is read-only.
type PaymentsProps = {
  paymentType: PaymentType;
  title: string;
  description: string;
};

export default function Payments({ paymentType, title, description }: PaymentsProps) {
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

  // Reset paging when the caller switches between receipts and payments.
  useEffect(() => {
    setPage(1);
  }, [paymentType]);

  const query = new URLSearchParams({
    page: String(page),
    page_size: String(PAGE_SIZE),
    payment_type: paymentType,
  });
  if (search) query.set("search", search);
  const path = `/payments?${query.toString()}`;

  const { data, loading, error, refetch } = useApi<Page<Payment>>(path, [path]);

  const columns: DataTableColumn<Payment>[] = [
    { key: "number", header: "Number" },
    { key: "payment_date", header: "Date" },
    { key: "partner_name", header: "Partner", render: (row) => row.partner_name ?? "—" },
    {
      key: "amount",
      header: "Amount",
      align: "right",
      render: (row) => <MoneyDisplay value={row.amount} />,
    },
    { key: "note", header: "Note", render: (row) => row.note ?? "—" },
    {
      key: "state",
      header: "Status",
      render: (row) => <StatusBadge status={row.state as Status} />,
    },
  ];

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h1 className="text-2xl font-semibold text-text_primary">{title}</h1>
        <p className="text-sm text-text_secondary">{description}</p>
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
        searchValue={searchInput}
        onSearchChange={setSearchInput}
        onRetry={refetch}
        getRowId={(row) => row.id}
        emptyMessage={
          paymentType === "receive"
            ? "No receipts yet — register one from a confirmed customer invoice."
            : "No payments yet — register one from a confirmed vendor bill."
        }
      />
    </div>
  );
}
