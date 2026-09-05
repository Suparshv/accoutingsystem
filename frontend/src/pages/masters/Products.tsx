import { useEffect, useState } from "react";
import { Controller, useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Plus } from "lucide-react";
import { DataTable, type DataTableColumn } from "@/components/shared/DataTable";
import { KanbanGrid } from "@/components/shared/KanbanGrid";
import { ViewSwitcher, type ViewMode } from "@/components/shared/ViewSwitcher";
import { FormShell } from "@/components/shared/FormShell";
import { MoneyDisplay } from "@/components/shared/MoneyDisplay";
import { MoneyInput } from "@/components/shared/MoneyInput";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
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
import type { Page, Product, ProductCategory, ProductInput, ProductType } from "@/types/api";

const PAGE_SIZE = 20;
const NO_CATEGORY = "none";

const TYPE_LABELS: Record<ProductType, string> = {
  goods: "Goods",
  service: "Service",
  combo: "Combo",
};

// SPEC.md §13.5 money mask — two decimals, never a JS number.
const MONEY_REGEX = /^\d+(\.\d{1,2})?$/;

// Mirrors backend/app/schemas/product.py's ProductCreate/ProductUpdate.
const productSchema = z.object({
  name: z.string().trim().min(1, "Name is required").max(200),
  product_type: z.enum(["goods", "service", "combo"]),
  category_id: z.string(), // NO_CATEGORY or a stringified id — normalised on submit
  sales_price: z.string().regex(MONEY_REGEX, "Enter a valid amount, e.g. 199.99"),
  cost_price: z.string().regex(MONEY_REGEX, "Enter a valid amount, e.g. 199.99"),
});
type ProductFormValues = z.infer<typeof productSchema>;

function toProductInput(values: ProductFormValues): ProductInput {
  return {
    name: values.name.trim(),
    product_type: values.product_type,
    category_id: values.category_id === NO_CATEGORY ? null : Number(values.category_id),
    sales_price: values.sales_price,
    cost_price: values.cost_price,
  };
}

function toFormValues(product: Product | null): ProductFormValues {
  if (!product) {
    return {
      name: "",
      product_type: "goods",
      category_id: NO_CATEGORY,
      sales_price: "0.00",
      cost_price: "0.00",
    };
  }
  return {
    name: product.name,
    product_type: product.product_type,
    category_id: product.category_id ? String(product.category_id) : NO_CATEGORY,
    sales_price: product.sales_price,
    cost_price: product.cost_price,
  };
}

type Mode = { kind: "list" } | { kind: "create" } | { kind: "edit"; product: Product };

export default function Products() {
  const [mode, setMode] = useState<Mode>({ kind: "list" });
  const [page, setPage] = useState(1);
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");
  const [viewMode, setViewMode] = useState<ViewMode>("list");

  useEffect(() => {
    const timer = setTimeout(() => {
      setSearch(searchInput);
      setPage(1);
    }, 400);
    return () => clearTimeout(timer);
  }, [searchInput]);

  const query = new URLSearchParams({ page: String(page), page_size: String(PAGE_SIZE) });
  if (search) query.set("search", search);
  const path = `/products?${query.toString()}`;

  const { data, loading, error, refetch } = useApi<Page<Product>>(path, [path]);
  const { data: categories, refetch: refetchCategories } = useApi<ProductCategory[]>(
    "/product-categories",
    [],
  );
  const categoryName = (id: number | null) =>
    categories?.find((c) => c.id === id)?.name ?? "—";

  const columns: DataTableColumn<Product>[] = [
    { key: "name", header: "Name" },
    { key: "product_type", header: "Type", render: (row) => TYPE_LABELS[row.product_type] },
    { key: "category", header: "Category", render: (row) => categoryName(row.category_id) },
    {
      key: "sales_price",
      header: "Sales Price",
      align: "right",
      render: (row) => <MoneyDisplay value={row.sales_price} />,
    },
    {
      key: "cost_price",
      header: "Cost Price",
      align: "right",
      render: (row) => <MoneyDisplay value={row.cost_price} />,
    },
  ];

  async function handleSaved() {
    setMode({ kind: "list" });
    await refetch();
  }

  if (mode.kind !== "list") {
    return (
      <ProductForm
        key={mode.kind === "edit" ? mode.product.id : "new"}
        product={mode.kind === "edit" ? mode.product : null}
        categories={categories ?? []}
        onCategoryCreated={refetchCategories}
        onBack={() => setMode({ kind: "list" })}
        onSaved={handleSaved}
      />
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-text_primary">Products</h1>
          <p className="text-sm text-text_secondary">Goods and services you buy or sell.</p>
        </div>
        <div className="flex items-center gap-2">
          <ViewSwitcher value={viewMode} onChange={setViewMode} />
          <Button type="button" onClick={() => setMode({ kind: "create" })}>
            <Plus className="mr-2 h-4 w-4" />
            New Product
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
          onRowClick={(row) => setMode({ kind: "edit", product: row })}
          searchValue={searchInput}
          onSearchChange={setSearchInput}
          onRetry={refetch}
          getRowId={(row) => row.id}
          emptyMessage="No products yet — add your first one."
        />
      ) : (
        <KanbanGrid
          items={data?.items ?? []}
          loading={loading}
          error={error ? { message: error.message } : null}
          onRetry={refetch}
          getItemId={(row) => row.id}
          onCardClick={(row) => setMode({ kind: "edit", product: row })}
          emptyMessage="No products yet."
          renderCard={(row) => (
            <div className="flex flex-col gap-1">
              <p className="font-medium text-text_primary">{row.name}</p>
              <p className="text-xs uppercase tracking-wide text-text_secondary">
                {TYPE_LABELS[row.product_type]} &middot; {categoryName(row.category_id)}
              </p>
              <MoneyDisplay value={row.sales_price} className="mt-2" />
            </div>
          )}
        />
      )}
    </div>
  );
}

function ProductForm({
  product,
  categories,
  onCategoryCreated,
  onBack,
  onSaved,
}: {
  product: Product | null;
  categories: ProductCategory[];
  onCategoryCreated: () => Promise<void> | void;
  onBack: () => void;
  onSaved: () => void;
}) {
  const [categoryDialogOpen, setCategoryDialogOpen] = useState(false);

  const {
    register,
    handleSubmit,
    control,
    setValue,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<ProductFormValues>({
    resolver: zodResolver(productSchema),
    defaultValues: toFormValues(product),
  });

  async function onSubmit(values: ProductFormValues) {
    try {
      const body = toProductInput(values);
      if (product) {
        await api.put<Product>(`/products/${product.id}`, body);
        toast({ title: "Product updated" });
      } else {
        await api.post<Product>("/products", body);
        toast({ title: "Product created" });
      }
      onSaved();
    } catch (e) {
      const apiError = normaliseError(e);
      const handled = applyServerErrors(apiError, setError);
      if (!handled) {
        toast({ variant: "destructive", title: "Could not save product", description: apiError.message });
      }
    }
  }

  async function handleCategoryCreated(category: ProductCategory) {
    await onCategoryCreated();
    setValue("category_id", String(category.id));
    setCategoryDialogOpen(false);
  }

  return (
    <FormShell
      title={product ? `Edit ${product.name}` : "New Product"}
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
          <Label htmlFor="product_type">Type</Label>
          <Controller
            control={control}
            name="product_type"
            render={({ field }) => (
              <Select value={field.value} onValueChange={field.onChange}>
                <SelectTrigger id="product_type">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="goods">Goods</SelectItem>
                  <SelectItem value="service">Service</SelectItem>
                  <SelectItem value="combo">Combo</SelectItem>
                </SelectContent>
              </Select>
            )}
          />
        </div>

        <div>
          <Label htmlFor="category_id">Category</Label>
          <div className="flex gap-2">
            <Controller
              control={control}
              name="category_id"
              render={({ field }) => (
                <Select value={field.value} onValueChange={field.onChange}>
                  <SelectTrigger id="category_id" className="flex-1">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value={NO_CATEGORY}>No category</SelectItem>
                    {categories.map((category) => (
                      <SelectItem key={category.id} value={String(category.id)}>
                        {category.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}
            />
            <Button
              type="button"
              variant="outline"
              size="icon"
              aria-label="Create new category"
              onClick={() => setCategoryDialogOpen(true)}
            >
              <Plus className="h-4 w-4" />
            </Button>
          </div>
        </div>

        <div>
          <Label htmlFor="sales_price">Sales Price</Label>
          <Controller
            control={control}
            name="sales_price"
            render={({ field }) => (
              <MoneyInput id="sales_price" value={field.value} onChange={field.onChange} />
            )}
          />
          {errors.sales_price && (
            <p className="mt-1 text-xs text-danger">{errors.sales_price.message}</p>
          )}
        </div>

        <div>
          <Label htmlFor="cost_price">Cost Price</Label>
          <Controller
            control={control}
            name="cost_price"
            render={({ field }) => (
              <MoneyInput id="cost_price" value={field.value} onChange={field.onChange} />
            )}
          />
          {errors.cost_price && (
            <p className="mt-1 text-xs text-danger">{errors.cost_price.message}</p>
          )}
        </div>
      </form>

      <CategoryQuickAddDialog
        open={categoryDialogOpen}
        onOpenChange={setCategoryDialogOpen}
        onCreated={handleCategoryCreated}
      />
    </FormShell>
  );
}

// SPEC.md §7.3 — "Category can be created and saved on the fly (Many2one
// field)": a product-type-only field, created inline without leaving the
// product form.
function CategoryQuickAddDialog({
  open,
  onOpenChange,
  onCreated,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreated: (category: ProductCategory) => void;
}) {
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleCreate() {
    if (!name.trim()) {
      setError("Category name is required");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const category = await api.post<ProductCategory>("/product-categories", {
        name: name.trim(),
      });
      setName("");
      onCreated(category);
    } catch (e) {
      setError(normaliseError(e).message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>New category</DialogTitle>
        </DialogHeader>
        <div>
          <Label htmlFor="new_category_name">Name</Label>
          <Input
            id="new_category_name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. Furniture"
          />
          {error && <p className="mt-1 text-xs text-danger">{error}</p>}
        </div>
        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button type="button" onClick={handleCreate} disabled={submitting}>
            {submitting ? "Creating..." : "Create"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
