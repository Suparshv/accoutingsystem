import { useState } from "react";
import { MoneyInput } from "@/components/shared/MoneyInput";
import { MoneyDisplay } from "@/components/shared/MoneyDisplay";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
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
import type { Journal, Page, Payment, PaymentType } from "@/types/api";

// SPEC.md §7.8: one payment form for both directions — the mockup's Bill
// Payment and Invoice Payment screens are this same form with payment_type
// flipped. Used by Customer Invoices, Vendor Bills and the contact portal.
type PaymentDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  paymentType: PaymentType;
  partnerId: number;
  partnerName: string;
  amountDue: string;
  /** Exactly one of these is set — a payment settles one document (§7.8.1). */
  invoiceId?: number;
  billId?: number;
  onPaid: () => void;
};

function today(): string {
  return new Date().toISOString().slice(0, 10);
}

export function PaymentDialog({
  open,
  onOpenChange,
  paymentType,
  partnerId,
  partnerName,
  amountDue,
  invoiceId,
  billId,
  onPaid,
}: PaymentDialogProps) {
  const [amount, setAmount] = useState(amountDue);
  const [journalId, setJournalId] = useState("");
  const [paymentDate, setPaymentDate] = useState(today());
  const [note, setNote] = useState("");
  const [submitting, setSubmitting] = useState(false);

  // "Payment Via" must be a bank or cash journal (§7.8 / 422
  // INVALID_PAYMENT_JOURNAL), so only those two types are offered.
  const { data: bankJournals } = useApi<Page<Journal>>(
    "/journals?page=1&page_size=100&journal_type=bank",
    [],
  );
  const { data: cashJournals } = useApi<Page<Journal>>(
    "/journals?page=1&page_size=100&journal_type=cash",
    [],
  );
  const journals = [...(bankJournals?.items ?? []), ...(cashJournals?.items ?? [])];

  async function handleSubmit() {
    setSubmitting(true);
    try {
      // Create as draft, then confirm — confirming is what posts the journal
      // entry and recomputes the document's payment status (§9 payments).
      const payment = await api.post<Payment>("/payments", {
        payment_type: paymentType,
        partner_id: partnerId,
        journal_id: Number(journalId),
        amount,
        payment_date: paymentDate,
        note: note.trim() || null,
        invoice_id: invoiceId ?? null,
        bill_id: billId ?? null,
      });
      await api.post<Payment>(`/payments/${payment.id}/confirm`);
      toast({ title: "Payment registered" });
      onOpenChange(false);
      onPaid();
    } catch (e) {
      toast({
        variant: "destructive",
        title: "Could not register payment",
        description: normaliseError(e).message,
      });
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {paymentType === "receive" ? "Register Receipt" : "Register Payment"}
          </DialogTitle>
        </DialogHeader>

        <div className="flex flex-col gap-4">
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div>
              <p className="text-text_secondary">Payment Type</p>
              <p className="text-text_primary">
                {paymentType === "receive" ? "Receive" : "Send"}
              </p>
            </div>
            <div>
              <p className="text-text_secondary">Partner</p>
              <p className="text-text_primary">{partnerName}</p>
            </div>
          </div>

          <div>
            <Label htmlFor="payment_amount">Amount</Label>
            <MoneyInput id="payment_amount" value={amount} onChange={setAmount} />
            <p className="mt-1 text-xs text-text_secondary">
              Amount due: <MoneyDisplay value={amountDue} />. Paying less is a partial
              payment; the server rejects more (422 OVERPAYMENT).
            </p>
          </div>

          <div>
            <Label htmlFor="payment_journal">Payment Via</Label>
            <Select value={journalId} onValueChange={setJournalId}>
              <SelectTrigger id="payment_journal">
                <SelectValue placeholder="Select bank or cash journal" />
              </SelectTrigger>
              <SelectContent>
                {journals.map((journal) => (
                  <SelectItem key={journal.id} value={String(journal.id)}>
                    {journal.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div>
            <Label htmlFor="payment_date">Date</Label>
            <Input
              id="payment_date"
              type="date"
              value={paymentDate}
              onChange={(e) => setPaymentDate(e.target.value)}
            />
          </div>

          <div>
            <Label htmlFor="payment_note">Note</Label>
            <Input
              id="payment_note"
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="Optional"
            />
          </div>
        </div>

        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            type="button"
            onClick={handleSubmit}
            disabled={submitting || !journalId || !amount}
          >
            {submitting ? "Registering..." : "Register Payment"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
