import { useEffect, useState } from "react";
import { Controller, useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Plus } from "lucide-react";
import { DataTable, type DataTableColumn } from "@/components/shared/DataTable";
import { KanbanGrid } from "@/components/shared/KanbanGrid";
import { ViewSwitcher, type ViewMode } from "@/components/shared/ViewSwitcher";
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
import { api, normaliseError } from "@/lib/api";
import { applyServerErrors } from "@/lib/form-errors";
import { toast } from "@/hooks/use-toast";
import type { Page, Partner, PartnerInput, PartnerType } from "@/types/api";

const PAGE_SIZE = 20;

const TYPE_LABELS: Record<PartnerType, string> = {
  customer: "Customer",
  vendor: "Vendor",
  both: "Both",
};

// Mirrors backend/app/schemas/partner.py's PartnerCreate/PartnerUpdate
// (SPEC.md §13.5 — same limits, same messages).
const partnerSchema = z.object({
  name: z.string().trim().min(1, "Name is required").max(200),
  email: z
    .string()
    .trim()
    .email("Enter a valid email address")
    .optional()
    .or(z.literal("")),
  phone: z.string().trim().max(20).optional().or(z.literal("")),
  partner_type: z.enum(["customer", "vendor", "both"]),
  street: z.string().trim().optional().or(z.literal("")),
  city: z.string().trim().optional().or(z.literal("")),
  state: z.string().trim().optional().or(z.literal("")),
  country: z.string().trim().optional().or(z.literal("")),
  pincode: z.string().trim().max(10).optional().or(z.literal("")),
});
type PartnerFormValues = z.infer<typeof partnerSchema>;

function blank(value: string | undefined): string | null {
  return value && value.trim() !== "" ? value.trim() : null;
}

function toPartnerInput(values: PartnerFormValues): PartnerInput {
  return {
    name: values.name.trim(),
    email: blank(values.email),
    phone: blank(values.phone),
    partner_type: values.partner_type,
    street: blank(values.street),
    city: blank(values.city),
    state: blank(values.state),
    country: blank(values.country),
    pincode: blank(values.pincode),
  };
}

function toFormValues(partner: Partner | null): PartnerFormValues {
  if (!partner) {
    return {
      name: "",
      email: "",
      phone: "",
      partner_type: "customer",
      street: "",
      city: "",
      state: "",
      country: "",
      pincode: "",
    };
  }
  return {
    name: partner.name,
    email: partner.email ?? "",
    phone: partner.phone ?? "",
    partner_type: partner.partner_type,
    street: partner.street ?? "",
    city: partner.city ?? "",
    state: partner.state ?? "",
    country: partner.country ?? "",
    pincode: partner.pincode ?? "",
  };
}

type Mode = { kind: "list" } | { kind: "create" } | { kind: "edit"; partner: Partner };

export default function Contacts() {
  const [mode, setMode] = useState<Mode>({ kind: "list" });
  const [page, setPage] = useState(1);
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");
  const [viewMode, setViewMode] = useState<ViewMode>("list");

  // Debounce the search box so every keystroke doesn't fire a request.
  useEffect(() => {
    const timer = setTimeout(() => {
      setSearch(searchInput);
      setPage(1);
    }, 400);
    return () => clearTimeout(timer);
  }, [searchInput]);

  const query = new URLSearchParams({ page: String(page), page_size: String(PAGE_SIZE) });
  if (search) query.set("search", search);
  const path = `/partners?${query.toString()}`;

  const { data, loading, error, refetch } = useApi<Page<Partner>>(path, [path]);

  const columns: DataTableColumn<Partner>[] = [
    { key: "name", header: "Name" },
    { key: "email", header: "Email", render: (row) => row.email ?? "—" },
    { key: "phone", header: "Phone", render: (row) => row.phone ?? "—" },
    { key: "partner_type", header: "Type", render: (row) => TYPE_LABELS[row.partner_type] },
  ];

  async function handleSaved() {
    setMode({ kind: "list" });
    await refetch();
  }

  if (mode.kind !== "list") {
    return (
      <ContactForm
        key={mode.kind === "edit" ? mode.partner.id : "new"}
        partner={mode.kind === "edit" ? mode.partner : null}
        onBack={() => setMode({ kind: "list" })}
        onSaved={handleSaved}
      />
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-text_primary">Contacts</h1>
          <p className="text-sm text-text_secondary">Customers and vendors.</p>
        </div>
        <div className="flex items-center gap-2">
          <ViewSwitcher value={viewMode} onChange={setViewMode} />
          <Button type="button" onClick={() => setMode({ kind: "create" })}>
            <Plus className="mr-2 h-4 w-4" />
            New Contact
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
          onRowClick={(row) => setMode({ kind: "edit", partner: row })}
          searchValue={searchInput}
          onSearchChange={setSearchInput}
          onRetry={refetch}
          getRowId={(row) => row.id}
          emptyMessage="No contacts yet — add your first customer or vendor."
        />
      ) : (
        <KanbanGrid
          items={data?.items ?? []}
          loading={loading}
          error={error ? { message: error.message } : null}
          onRetry={refetch}
          getItemId={(row) => row.id}
          onCardClick={(row) => setMode({ kind: "edit", partner: row })}
          emptyMessage="No contacts yet."
          renderCard={(row) => (
            <div className="flex flex-col gap-1">
              <p className="font-medium text-text_primary">{row.name}</p>
              <p className="text-sm text-text_secondary">{row.email ?? "No email"}</p>
              <p className="text-xs uppercase tracking-wide text-text_secondary">
                {TYPE_LABELS[row.partner_type]}
              </p>
            </div>
          )}
        />
      )}
    </div>
  );
}

function ContactForm({
  partner,
  onBack,
  onSaved,
}: {
  partner: Partner | null;
  onBack: () => void;
  onSaved: () => void;
}) {
  const {
    register,
    handleSubmit,
    control,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<PartnerFormValues>({
    resolver: zodResolver(partnerSchema),
    defaultValues: toFormValues(partner),
  });

  async function onSubmit(values: PartnerFormValues) {
    try {
      const body = toPartnerInput(values);
      if (partner) {
        await api.put<Partner>(`/partners/${partner.id}`, body);
        toast({ title: "Contact updated" });
      } else {
        await api.post<Partner>("/partners", body);
        toast({ title: "Contact created" });
      }
      onSaved();
    } catch (e) {
      const apiError = normaliseError(e);
      const handled = applyServerErrors(apiError, setError, { EMAIL_TAKEN: "email" });
      if (!handled) {
        toast({ variant: "destructive", title: "Could not save contact", description: apiError.message });
      }
    }
  }

  return (
    <FormShell
      title={partner ? `Edit ${partner.name}` : "New Contact"}
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
      <form onSubmit={handleSubmit(onSubmit)} noValidate className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div className="sm:col-span-2">
          <Label htmlFor="name">Name</Label>
          <Input id="name" {...register("name")} />
          {errors.name && <p className="mt-1 text-xs text-danger">{errors.name.message}</p>}
        </div>

        <div>
          <Label htmlFor="email">Email</Label>
          <Input id="email" type="email" {...register("email")} />
          {errors.email && <p className="mt-1 text-xs text-danger">{errors.email.message}</p>}
        </div>

        <div>
          <Label htmlFor="phone">Phone</Label>
          <Input id="phone" {...register("phone")} />
          {errors.phone && <p className="mt-1 text-xs text-danger">{errors.phone.message}</p>}
        </div>

        <div>
          <Label htmlFor="partner_type">Type</Label>
          <Controller
            control={control}
            name="partner_type"
            render={({ field }) => (
              <Select value={field.value} onValueChange={field.onChange}>
                <SelectTrigger id="partner_type">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="customer">Customer</SelectItem>
                  <SelectItem value="vendor">Vendor</SelectItem>
                  <SelectItem value="both">Both</SelectItem>
                </SelectContent>
              </Select>
            )}
          />
        </div>

        <div>
          <Label htmlFor="pincode">Pincode</Label>
          <Input id="pincode" {...register("pincode")} />
          {errors.pincode && <p className="mt-1 text-xs text-danger">{errors.pincode.message}</p>}
        </div>

        <div className="sm:col-span-2">
          <Label htmlFor="street">Street</Label>
          <Input id="street" {...register("street")} />
        </div>

        <div>
          <Label htmlFor="city">City</Label>
          <Input id="city" {...register("city")} />
        </div>

        <div>
          <Label htmlFor="state">State</Label>
          <Input id="state" {...register("state")} />
        </div>

        <div>
          <Label htmlFor="country">Country</Label>
          <Input id="country" {...register("country")} />
        </div>
      </form>
    </FormShell>
  );
}
