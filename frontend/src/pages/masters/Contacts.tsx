import { useEffect, useState } from "react";
import { Controller, useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Plus, Trash2, Upload } from "lucide-react";
import { DataTable, type DataTableColumn } from "@/components/shared/DataTable";
import { KanbanGrid } from "@/components/shared/KanbanGrid";
import { ViewSwitcher, type ViewMode } from "@/components/shared/ViewSwitcher";
import { ContactAvatar } from "@/components/shared/ContactAvatar";
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
import type { Page, Partner, PartnerInput, PartnerType } from "@/types/api";

const PAGE_SIZE = 20;

// Mirrors core/uploads.py — same limits, same messages (SPEC.md §13.5).
const MAX_IMAGE_BYTES = 2 * 1024 * 1024;
const ACCEPTED_IMAGE_TYPES = ["image/jpeg", "image/jpg", "image/png"];

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
  const search = useDebouncedValue(searchInput);
  const [viewMode, setViewMode] = useState<ViewMode>("list");

  // A new search term is a new result set, so it starts at page 1 again.
  useEffect(() => {
    setPage(1);
  }, [search]);

  const query = new URLSearchParams({ page: String(page), page_size: String(PAGE_SIZE) });
  if (search) query.set("search", search);
  const path = `/partners?${query.toString()}`;

  const { data, loading, error, refetch } = useApi<Page<Partner>>(path, [path]);

  const columns: DataTableColumn<Partner>[] = [
    {
      key: "name",
      header: "Name",
      render: (row) => (
        <span className="flex items-center gap-2.5">
          <ContactAvatar name={row.name} imageUrl={row.image_url} />
          <span>{row.name}</span>
        </span>
      ),
    },
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
            <div className="flex items-start gap-3">
              <ContactAvatar name={row.name} imageUrl={row.image_url} size="md" />
              <div className="flex min-w-0 flex-col gap-1">
                <p className="truncate font-medium text-text_primary">{row.name}</p>
                <p className="truncate text-sm text-text_secondary">
                  {row.email ?? "No email"}
                </p>
                <p className="text-xs uppercase tracking-wide text-text_secondary">
                  {TYPE_LABELS[row.partner_type]}
                </p>
              </div>
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

  // The picked file is held here and uploaded as part of Save, rather than
  // the moment it is chosen. Two reasons: a brand-new contact has no id yet
  // to upload against, and staging it means the whole form behaves the same
  // way — nothing is persisted until you press Save, image included. The
  // preview is a local object URL, so it costs no round trip.
  const [imageFile, setImageFile] = useState<File | null>(null);
  const [imagePreview, setImagePreview] = useState<string | null>(null);
  const [imageError, setImageError] = useState<string | null>(null);
  // Removing an existing photo is staged the same way as replacing one, so
  // both follow the form's single rule: nothing is persisted until Save, and
  // Cancel undoes it. The two are mutually exclusive — picking a file cancels
  // a pending removal and vice versa.
  const [imageRemoved, setImageRemoved] = useState(false);

  const savedImageUrl = partner?.image_url ?? null;
  const hasImage = Boolean(imageFile) || (Boolean(savedImageUrl) && !imageRemoved);

  useEffect(() => {
    if (!imageFile) {
      setImagePreview(null);
      return;
    }
    const url = URL.createObjectURL(imageFile);
    setImagePreview(url);
    return () => URL.revokeObjectURL(url);
  }, [imageFile]);

  function pickImage(file: File | null) {
    setImageError(null);
    setImageRemoved(false);
    if (!file) {
      setImageFile(null);
      return;
    }
    if (!ACCEPTED_IMAGE_TYPES.includes(file.type)) {
      setImageError("Choose a JPEG or PNG image");
      setImageFile(null);
      return;
    }
    if (file.size > MAX_IMAGE_BYTES) {
      setImageError("That image is larger than the 2 MB limit");
      setImageFile(null);
      return;
    }
    setImageFile(file);
  }

  /** Clear the photo: drops a staged file, and stages the saved one for
   *  deletion if that is what is on screen. */
  function clearImage() {
    setImageError(null);
    if (imageFile) {
      setImageFile(null);
      return;
    }
    if (savedImageUrl) setImageRemoved(true);
  }

  function undoRemoveImage() {
    setImageRemoved(false);
  }

  async function onSubmit(values: PartnerFormValues) {
    try {
      const body = toPartnerInput(values);
      const saved = partner
        ? await api.put<Partner>(`/partners/${partner.id}`, body)
        : await api.post<Partner>("/partners", body);

      // A second call, and it can only happen after the first: a new contact
      // has no id to act on until it exists. If this is the part that fails,
      // the contact itself is already saved — so the message says exactly
      // that rather than implying the whole save was lost.
      if (imageFile || imageRemoved) {
        try {
          if (imageFile) {
            await api.upload<Partner>(`/partners/${saved.id}/image`, imageFile);
          } else {
            await api.delete<Partner>(`/partners/${saved.id}/image`);
          }
        } catch (imageIssue) {
          toast({
            variant: "destructive",
            title: imageFile
              ? "Contact saved, but the photo was not uploaded"
              : "Contact saved, but the photo was not removed",
            description: normaliseError(imageIssue).message,
          });
          onSaved();
          return;
        }
      }

      toast({ title: partner ? "Contact updated" : "Contact created" });
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
        <div className="flex items-center gap-4 sm:col-span-2">
          {imagePreview ? (
            <img
              src={imagePreview}
              alt=""
              className="h-28 w-28 shrink-0 rounded-full border border-border object-cover"
            />
          ) : (
            // A staged removal shows the initials placeholder immediately, so
            // the button says what the record will look like after Save.
            <ContactAvatar
              name={partner?.name || "?"}
              imageUrl={imageRemoved ? null : savedImageUrl}
              size="lg"
            />
          )}

          <div className="flex flex-col items-start gap-1.5">
            <Label htmlFor="contact_image">Photo</Label>
            {/* The native file input is replaced by a button, because its
                default rendering cannot be styled and reads as unfinished
                next to the rest of the form. */}
            <input
              id="contact_image"
              type="file"
              accept="image/jpeg,image/png"
              className="sr-only"
              onChange={(e) => pickImage(e.target.files?.[0] ?? null)}
            />
            <div className="flex items-center gap-2">
              <Button type="button" variant="outline" size="sm" asChild>
                <label htmlFor="contact_image" className="cursor-pointer">
                  <Upload className="mr-2 h-4 w-4" />
                  {hasImage ? "Replace photo" : "Upload photo"}
                </label>
              </Button>

              {hasImage && (
                <Button type="button" variant="ghost" size="sm" onClick={clearImage}>
                  <Trash2 className="mr-2 h-4 w-4 text-danger" />
                  {imageFile ? "Clear" : "Remove photo"}
                </Button>
              )}

              {imageRemoved && (
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={undoRemoveImage}
                >
                  Undo
                </Button>
              )}
            </div>

            <p className="text-xs text-text_secondary">
              {imageFile
                ? `${imageFile.name} — uploads when you save`
                : imageRemoved
                  ? "Photo will be removed when you save"
                  : "Optional. JPEG or PNG, up to 2 MB."}
            </p>
            <FieldError message={imageError} />
          </div>
        </div>

        <div className="sm:col-span-2">
          <Label htmlFor="name" required>Name</Label>
          <Input id="name" {...register("name")} />
          <FieldError message={errors.name?.message} />
        </div>

        <div>
          <Label htmlFor="email">Email</Label>
          <Input id="email" type="email" {...register("email")} />
          <FieldError message={errors.email?.message} />
        </div>

        <div>
          <Label htmlFor="phone">Phone</Label>
          <Input id="phone" {...register("phone")} />
          <FieldError message={errors.phone?.message} />
        </div>

        <div>
          <Label htmlFor="partner_type" required>Type</Label>
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
          <FieldError message={errors.partner_type?.message} />
        </div>

        <div>
          <Label htmlFor="pincode">Pincode</Label>
          <Input id="pincode" {...register("pincode")} />
          <FieldError message={errors.pincode?.message} />
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
