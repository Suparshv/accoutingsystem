import { useState } from "react";
import { DataTable, type DataTableColumn } from "@/components/shared/DataTable";
import { MoneyDisplay } from "@/components/shared/MoneyDisplay";
import { PaymentDialog } from "@/components/shared/PaymentDialog";
import { StatusBadge, type Status } from "@/components/shared/StatusBadge";
import { Button } from "@/components/ui/button";
import { useApi } from "@/hooks/useApi";
import { useAuth } from "@/hooks/useAuth";
import type { Page, PortalDocument } from "@/types/api";

// SPEC.md §9 portal: the partner filter is applied in the SERVICE query from
// the verified token, never from a client parameter (§12.3) — this page sends
// no partner id, it just asks for "my" documents.
type MyDocumentsProps = {
  documentType: "invoice" | "bill";
  title: string;
  description: string;
};

export default function MyDocuments({
  documentType,
  title,
  description,
}: MyDocumentsProps) {
  const { user } = useAuth();
  const [paying, setPaying] = useState<PortalDocument | null>(null);

  const path = "/portal/my-documents";
  const { data, loading, error, refetch } = useApi<Page<PortalDocument>>(path, [path]);

  const rows = (data?.items ?? []).filter((doc) => doc.document_type === documentType);

  const columns: DataTableColumn<PortalDocument>[] = [
    { key: "number", header: "Number" },
    { key: "date", header: "Date" },
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
      key: "pay",
      header: "",
      render: (row) =>
        row.state === "confirmed" && row.payment_status !== "paid" ? (
          <Button
            type="button"
            size="sm"
            onClick={(e) => {
              e.stopPropagation();
              setPaying(row);
            }}
          >
            Pay
          </Button>
        ) : null,
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
        rows={rows}
        loading={loading}
        error={error ? { message: error.message } : null}
        page={1}
        pageSize={rows.length || 20}
        total={rows.length}
        onPageChange={() => {}}
        onRetry={refetch}
        getRowId={(row) => `${row.document_type}-${row.id}`}
        emptyMessage={
          documentType === "invoice"
            ? "You have no invoices yet."
            : "You have no bills yet."
        }
      />

      {paying && user?.partner_id && (
        <PaymentDialog
          open
          onOpenChange={(open) => !open && setPaying(null)}
          paymentType={paying.document_type === "invoice" ? "receive" : "send"}
          partnerId={user.partner_id}
          partnerName={user.name ?? "You"}
          amountDue={paying.amount_due}
          documentDate={paying.date}
          invoiceId={paying.document_type === "invoice" ? paying.id : undefined}
          billId={paying.document_type === "bill" ? paying.id : undefined}
          onPaid={async () => {
            setPaying(null);
            await refetch();
          }}
        />
      )}
    </div>
  );
}
