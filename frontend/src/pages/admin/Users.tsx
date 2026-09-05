import { useEffect, useState } from "react";
import { Controller, useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Plus } from "lucide-react";
import { DataTable, type DataTableColumn } from "@/components/shared/DataTable";
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
import type { AppUser, Page, Partner, UserRole } from "@/types/api";

const PAGE_SIZE = 20;
const NO_PARTNER = "none";

const ROLE_LABELS: Record<UserRole, string> = {
  admin: "Administrator",
  accountant: "Accountant (invoicing user)",
  contact: "Portal user (contact)",
};

// POST /auth/users only accepts admin|contact — self-signup is the only path
// that produces an accountant (SPEC.md §9, §7.1 user_role note). Regexes
// mirror backend/app/schemas/auth.py exactly.
const LOGIN_ID_REGEX = /^[A-Za-z0-9_]{6,12}$/;
const PASSWORD_REGEX = /^(?=.*[a-z])(?=.*[A-Z])(?=.*[^A-Za-z0-9]).{9,}$/;

const userSchema = z
  .object({
    name: z.string().trim().min(1, "Name is required"),
    login_id: z
      .string()
      .regex(
        LOGIN_ID_REGEX,
        "login_id must be 6-12 characters: letters, digits and underscore only",
      ),
    email: z.string().email("Enter a valid email address"),
    role: z.enum(["admin", "contact"]),
    password: z
      .string()
      .regex(
        PASSWORD_REGEX,
        "password must be at least 9 characters and include an uppercase letter, a lowercase letter and a special character",
      ),
    confirm_password: z.string(),
    partner_id: z.string(),
  })
  .refine((data) => data.password === data.confirm_password, {
    message: "confirm_password must match password",
    path: ["confirm_password"],
  })
  // ck_users_contact_needs_partner: a portal user with no linked partner could
  // see nothing, or worse, everything (SPEC.md §7.2).
  .refine((data) => data.role !== "contact" || data.partner_id !== NO_PARTNER, {
    message: "A portal (contact) user must be linked to a contact",
    path: ["partner_id"],
  });
type UserFormValues = z.infer<typeof userSchema>;

export default function Users() {
  const [creating, setCreating] = useState(false);
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
  const path = `/auth/users?${query.toString()}`;

  const { data, loading, error, refetch } = useApi<Page<AppUser>>(path, [path]);
  const { data: partners } = useApi<Page<Partner>>("/partners?page=1&page_size=100", []);

  const columns: DataTableColumn<AppUser>[] = [
    { key: "name", header: "Name" },
    { key: "login_id", header: "Login ID" },
    { key: "email", header: "Email" },
    { key: "role", header: "Role", render: (row) => ROLE_LABELS[row.role] },
    {
      key: "is_active",
      header: "Active",
      render: (row) => (row.is_active ? "Yes" : "No"),
    },
  ];

  if (creating) {
    return (
      <UserForm
        partners={partners?.items ?? []}
        onBack={() => setCreating(false)}
        onSaved={async () => {
          setCreating(false);
          await refetch();
        }}
      />
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-text_primary">Users</h1>
          <p className="text-sm text-text_secondary">
            Administrator-only. Creating users is the one thing an accountant cannot do.
          </p>
        </div>
        <Button type="button" onClick={() => setCreating(true)}>
          <Plus className="mr-2 h-4 w-4" />
          New User
        </Button>
      </div>

      {/* No edit form: the backend exposes GET and POST for users, no PUT. */}
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
        emptyMessage="No users yet."
      />
    </div>
  );
}

function UserForm({
  partners,
  onBack,
  onSaved,
}: {
  partners: Partner[];
  onBack: () => void;
  onSaved: () => void;
}) {
  const {
    register,
    handleSubmit,
    control,
    watch,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<UserFormValues>({
    resolver: zodResolver(userSchema),
    defaultValues: {
      name: "",
      login_id: "",
      email: "",
      role: "contact",
      password: "",
      confirm_password: "",
      partner_id: NO_PARTNER,
    },
  });

  const role = watch("role");

  async function onSubmit(values: UserFormValues) {
    try {
      await api.post<AppUser>("/auth/users", {
        name: values.name.trim(),
        login_id: values.login_id,
        email: values.email,
        role: values.role,
        password: values.password,
        confirm_password: values.confirm_password,
        partner_id: values.partner_id === NO_PARTNER ? null : Number(values.partner_id),
      });
      toast({ title: "User created" });
      onSaved();
    } catch (e) {
      const apiError = normaliseError(e);
      const handled = applyServerErrors(apiError, setError, {
        LOGIN_ID_TAKEN: "login_id",
        EMAIL_TAKEN: "email",
        CONTACT_REQUIRES_PARTNER: "partner_id",
      });
      if (!handled) {
        toast({
          variant: "destructive",
          title: "Could not create user",
          description: apiError.message,
        });
      }
    }
  }

  return (
    <FormShell
      title="New User"
      onBack={onBack}
      actions={[
        { label: "Cancel", variant: "outline", onClick: onBack },
        {
          label: isSubmitting ? "Creating..." : "Create",
          onClick: handleSubmit(onSubmit),
          disabled: isSubmitting,
        },
      ]}
    >
      <form
        onSubmit={handleSubmit(onSubmit)}
        noValidate
        className="grid grid-cols-1 gap-4 sm:grid-cols-2"
      >
        <div>
          <Label htmlFor="name">Name</Label>
          <Input id="name" {...register("name")} />
          {errors.name && <p className="mt-1 text-xs text-danger">{errors.name.message}</p>}
        </div>

        <div>
          <Label htmlFor="login_id">Login ID</Label>
          <Input id="login_id" {...register("login_id")} />
          {errors.login_id && (
            <p className="mt-1 text-xs text-danger">{errors.login_id.message}</p>
          )}
        </div>

        <div>
          <Label htmlFor="email">Email</Label>
          <Input id="email" type="email" {...register("email")} />
          {errors.email && <p className="mt-1 text-xs text-danger">{errors.email.message}</p>}
        </div>

        <div>
          <Label htmlFor="role">Role</Label>
          <Controller
            control={control}
            name="role"
            render={({ field }) => (
              <Select value={field.value} onValueChange={field.onChange}>
                <SelectTrigger id="role">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="admin">Administrator</SelectItem>
                  <SelectItem value="contact">User (portal / contact)</SelectItem>
                </SelectContent>
              </Select>
            )}
          />
          <p className="mt-1 text-xs text-text_secondary">
            Accountants are created by public self-signup, not here.
          </p>
        </div>

        <div className="sm:col-span-2">
          <Label htmlFor="partner_id">Linked contact {role === "contact" && "(required)"}</Label>
          <Controller
            control={control}
            name="partner_id"
            render={({ field }) => (
              <Select value={field.value} onValueChange={field.onChange}>
                <SelectTrigger id="partner_id">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={NO_PARTNER}>No linked contact</SelectItem>
                  {partners.map((partner) => (
                    <SelectItem key={partner.id} value={String(partner.id)}>
                      {partner.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
          />
          {errors.partner_id && (
            <p className="mt-1 text-xs text-danger">{errors.partner_id.message}</p>
          )}
        </div>

        <div>
          <Label htmlFor="password">Password</Label>
          <Input id="password" type="password" {...register("password")} />
          {errors.password && (
            <p className="mt-1 text-xs text-danger">{errors.password.message}</p>
          )}
        </div>

        <div>
          <Label htmlFor="confirm_password">Confirm password</Label>
          <Input id="confirm_password" type="password" {...register("confirm_password")} />
          {errors.confirm_password && (
            <p className="mt-1 text-xs text-danger">{errors.confirm_password.message}</p>
          )}
        </div>
      </form>
    </FormShell>
  );
}
