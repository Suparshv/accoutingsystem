// TS types mirroring the backend's Pydantic schemas (SPEC.md §4, §7, §9).
// Money fields come over the wire as strings (SPEC.md §12.1/P2) — never
// numbers — so they're typed `string` here and formatted via MoneyDisplay,
// never used in arithmetic.

export type UserRole = "admin" | "accountant" | "contact";
export type PartnerType = "customer" | "vendor" | "both";
export type ProductType = "goods" | "service" | "combo";

export type Page<T> = {
  items: T[];
  total: number;
  page: number;
  page_size: number;
};

export type Partner = {
  id: number;
  name: string;
  email: string | null;
  phone: string | null;
  partner_type: PartnerType;
  street: string | null;
  city: string | null;
  state: string | null;
  country: string | null;
  pincode: string | null;
  is_active: boolean;
};

export type PartnerInput = {
  name: string;
  email?: string | null;
  phone?: string | null;
  partner_type: PartnerType;
  street?: string | null;
  city?: string | null;
  state?: string | null;
  country?: string | null;
  pincode?: string | null;
};

export type ProductCategory = {
  id: number;
  name: string;
};

export type Product = {
  id: number;
  name: string;
  product_type: ProductType;
  category_id: number | null;
  sales_price: string;
  cost_price: string;
  is_active: boolean;
};

export type ProductInput = {
  name: string;
  product_type: ProductType;
  category_id?: number | null;
  sales_price: string;
  cost_price: string;
};

export type AnalyticAccount = {
  id: number;
  name: string;
  is_active: boolean;
};

export type AnalyticAccountInput = {
  name: string;
};
