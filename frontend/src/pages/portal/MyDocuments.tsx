import { useState } from "react";
import { DataTable, type DataTableColumn } from "@/components/shared/DataTable";
import { FormShell } from "@/components/shared/FormShell";
import { MoneyDisplay } from "@/components/shared/MoneyDisplay";
import { PaymentDialog } from "@/components/shared/PaymentDialog";
import { StatusBadge, type Status } from "@/components/shared/StatusBadge";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useApi } from "@/hooks/useApi";
import { useAuth } from "@/hooks/useAuth";
import type {
  CustomerInvoiceDetail,
  Page,
  PortalDocument,
  VendorBillDetail,
} from "@/types/api";

// SPEC.md §9 portal: the partner filter is applied in the SERVICE query from
// the verified token, never from a client parameter (§12.3) — this page sends
// no partner id, it just asks for "my" documents.
type MyDocumentsProps = {
  documentType: "invoice" | "bill";
  title: string;
  description: string;
};

// A draft/cancelled document's payment_status is always "not_paid" (zero
// payments can exist against it), and showing that badge reads as "you owe
// this and haven't paid" — misleading for a document that isn't even
// finalized yet, and it leaves the missing Pay button unexplained. Only a
// confirmed document's payment status is meaningful to a customer.
function PaymentCell({ row }: { row: PortalDocument }) {
  if (row.state === "draft") {
    return <span className="text-sm text-text_secondary">Awaiting confirmation</span>;
  }
  if (row.state === "cancelled") {
    return <span className="text-sm text-text_secondary">Cancelled</span>;
  }
  return <StatusBadge status={row.payment_status as Status} />;
}

export default function MyDocuments({
  documentType,
  title,
  description,
}: MyDocumentsProps) {
  const [viewing, setViewing] = useState<PortalDocument | null>(null);

  const path = "/portal/my-documents";
  const { data, loading, error, refetch } = useApi<Page<PortalDocument>>(path, [path]);

  const rows = (data?.items ?? []).filter((doc) => doc.document_type === documentType);

  // Pay used to live in a column on this list; it now lives only on the
  // detail view opened by clicking a row (INSTEAD OF the list, not in
  // addition) — a customer sees what they're actually being charged for
  // (line items, payment history) before committing to pay, and the list
  // stays a plain summary table instead of mixing display with actions.
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
      render: (row) => <PaymentCell row={row} />,
    },
  ];

  if (viewing) {
    return (
      <PortalDocumentDetail
        doc={viewing}
        onBack={() => setViewing(null)}
        onPaid={async () => {
          await refetch();
        }}
      />
    );
  }

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
        onRowClick={(row) => setViewing(row)}
        onRetry={refetch}
        getRowId={(row) => `${row.document_type}-${row.id}`}
        emptyMessage={
          documentType === "invoice"
            ? "You have no invoices yet."
            : "You have no bills yet."
        }
      />
    </div>
  );
}

// Read-only detail view for one invoice or bill, opened by clicking a My
// Invoices/My Bills row. Deliberately its own component rather than reusing
// CustomerInvoices.tsx's / VendorBills.tsx's form components: those build
// their own Save/Confirm/Cancel/Create-Invoice actions internally based on
// state, and reusing them here would mean either leaking those
// accountant-only actions to a contact or bolting a role check onto a
// shared, non-portal component. This component only ever renders "Back"
// and, when applicable, "Pay" — nothing it doesn't explicitly build.
//
// Fetches through GET /customer-invoices/{id} or GET /vendor-bills/{id} —
// the SAME endpoints the accountant UI uses, which already carry the
// server-side ownership check for the contact role (a contact requesting a
// document that isn't theirs gets 403, never the data — §12.2). No new
// endpoint, no client-trusted partner filter (R6).
function PortalDocumentDetail({
  doc,
  onBack,
  onPaid,
}: {
  doc: PortalDocument;
  onBack: () => void;
  onPaid: () => void;
}) {
  const { user } = useAuth();
  const [payOpen, setPayOpen] = useState(false);
  const detailPath =
    doc.document_type === "invoice"
      ? `/customer-invoices/${doc.id}`
      : `/vendor-bills/${doc.id}`;

  const {
    data,
    loading,
    error,
    refetch,
  } = useApi<CustomerInvoiceDetail | VendorBillDetail>(detailPath, [detailPath]);

  if (loading) {
    return <p className="text-sm text-text_secondary">Loading...</p>;
  }

  if (error) {
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

  if (!data) return null;

  const documentDate =
    doc.document_type === "invoice"
      ? (data as CustomerInvoiceDetail).invoice_date
      : (data as VendorBillDetail).bill_date;
  // A vendor bill means Urban Furniture owes the vendor — money flows FROM
  // Urban Furniture TO them. A contact viewing their own bill (as a vendor)
  // is owed money, not paying it, so Pay never applies to bills — only to
  // a contact's own customer invoices, where they're the one who owes.
  const canPay =
    doc.document_type === "invoice" &&
    data.state === "confirmed" &&
    data.payment_status !== "paid";

  return (
    <FormShell
      title={data.number}
      state={data.state}
      variant="document"
      onBack={onBack}
      actions={[
        { label: "Back", variant: "outline", onClick: onBack },
        ...(canPay ? [{ label: "Pay", onClick: () => setPayOpen(true) }] : []),
      ]}
    >
      <div className="flex flex-col gap-6">
        <dl className="grid grid-cols-2 gap-4 rounded border border-border bg-surface p-4 text-sm sm:grid-cols-4">
          <div>
            <dt className="text-text_secondary">Total</dt>
            <dd>
              <MoneyDisplay value={data.total_amount} />
            </dd>
          </div>
          <div>
            <dt className="text-text_secondary">Paid</dt>
            <dd>
              <MoneyDisplay value={data.amount_paid} />
            </dd>
          </div>
          <div>
            <dt className="text-text_secondary">Due</dt>
            <dd>
              <MoneyDisplay value={data.amount_due} />
            </dd>
          </div>
          <div>
            <dt className="text-text_secondary">Payment</dt>
            <dd>
              <PaymentCell row={doc} />
            </dd>
          </div>
        </dl>

        <div className="overflow-hidden rounded border border-border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Product / Service</TableHead>
                <TableHead className="text-right">Qty</TableHead>
                <TableHead className="text-right">Unit Price</TableHead>
                <TableHead className="text-right">Line Total</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.lines.map((line, index) => (
                <TableRow key={line.id ?? index}>
                  <TableCell>{line.product_name ?? `#${line.product_id}`}</TableCell>
                  <TableCell className="text-right tabular-nums">
                    {line.quantity}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    <MoneyDisplay value={line.unit_price} />
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    <MoneyDisplay value={line.line_total} />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
        {/* The analytic tag (e.g. "Showroom Expansion") is an internal
            project/cost-centre classification the business uses for its own
            budget tracking — it has no meaning to the customer being billed,
            so it's left out of this table on purpose, unlike the accountant-
            facing invoice/bill line tables which do show it. */}

        {data.payments.length > 0 && (
          <div className="overflow-hidden rounded border border-border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Payment Date</TableHead>
                  <TableHead className="text-right">Amount</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.payments.map((payment, index) => (
                  <TableRow key={index}>
                    <TableCell>{payment.date}</TableCell>
                    <TableCell className="text-right tabular-nums">
                      <MoneyDisplay value={payment.amount} />
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </div>

      {canPay && user?.partner_id && (
        <PaymentDialog
          open={payOpen}
          onOpenChange={setPayOpen}
          paymentType="receive"
          partnerId={user.partner_id}
          partnerName={user.name ?? "You"}
          amountDue={data.amount_due}
          documentDate={documentDate}
          invoiceId={doc.id}
          billId={undefined}
          onPaid={async () => {
            setPayOpen(false);
            await refetch();
            await onPaid();
          }}
        />
      )}
    </FormShell>
  );
}
