import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { FieldError } from "@/components/shared/FieldError";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAuth, type AuthenticatedUser } from "@/hooks/useAuth";
import { normaliseError } from "@/lib/api";
import { applyServerErrors } from "@/lib/form-errors";

const loginSchema = z.object({
  login_id: z.string().min(1, "Login ID is required"),
  password: z.string().min(1, "Password is required"),
});
type LoginFormValues = z.infer<typeof loginSchema>;

// A contact only ever has the portal to go to (SPEC.md §13.3 role_visibility:
// "contact: sees ONLY the portal"). Every other route 403s on its own API
// calls (e.g. GET /dashboard), so routing a contact into one is never useful
// — not even a route they were bounced FROM before logging in, unless that
// bounced route is itself a portal page.
const CONTACT_HOME = "/portal/invoices";
const PORTAL_PREFIX = "/portal/";

function postLoginDestination(
  user: AuthenticatedUser,
  from: { pathname: string } | undefined,
): string {
  if (user.role === "contact") {
    return from?.pathname.startsWith(PORTAL_PREFIX) ? from.pathname : CONTACT_HOME;
  }
  return from?.pathname ?? "/";
}

export default function Login() {
  const { login, loginDemo } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [formError, setFormError] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<LoginFormValues>({ resolver: zodResolver(loginSchema) });

  async function onSubmit(values: LoginFormValues) {
    setFormError(null);
    try {
      const user = await login(values.login_id, values.password);
      const from = (location.state as { from?: { pathname: string } } | null)?.from;
      navigate(postLoginDestination(user, from), { replace: true });
    } catch (e) {
      const apiError = normaliseError(e);
      // 401 INVALID_CREDENTIALS is deliberately not field-specific (SPEC.md
      // §10.2 — it never says which of login_id/password was wrong), so it
      // always falls through to the banner.
      const handled = applyServerErrors(apiError, setError);
      if (!handled) setFormError(apiError.message);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-surface px-4">
      <div className="w-full max-w-sm rounded border border-border bg-background p-6">
        <h1 className="text-xl font-semibold text-text_primary">Log in</h1>
        <p className="mt-1 text-sm text-text_secondary">Urban Furniture Accounting</p>

        <form onSubmit={handleSubmit(onSubmit)} noValidate className="mt-6 flex flex-col gap-4">
          {formError && (
            <p role="alert" className="rounded-md bg-danger/10 px-3 py-2 text-sm text-danger">
              {formError}
            </p>
          )}

          <div>
            <Label
              htmlFor="login_id"
              required
              className="mb-1 block text-xs font-medium text-text_secondary"
            >
              Login ID
            </Label>
            <Input id="login_id" autoComplete="username" {...register("login_id")} />
            <FieldError message={errors.login_id?.message} />
          </div>

          <div>
            <Label
              htmlFor="password"
              required
              className="mb-1 block text-xs font-medium text-text_secondary"
            >
              Password
            </Label>
            <Input
              id="password"
              type="password"
              autoComplete="current-password"
              {...register("password")}
            />
            <FieldError message={errors.password?.message} />
          </div>

          <Button type="submit" disabled={isSubmitting} className="mt-2">
            {isSubmitting ? "Logging in..." : "Log in"}
          </Button>

          <div className="relative my-2">
            <div className="absolute inset-0 flex items-center">
              <span className="w-full border-t border-border" />
            </div>
            <div className="relative flex justify-center text-xs uppercase">
              <span className="bg-background px-2 text-text_secondary">or</span>
            </div>
          </div>

          <Button
            type="button"
            variant="outline"
            className="w-full"
            onClick={() => {
              loginDemo();
              navigate("/");
            }}
          >
            Explore Pages in Demo Mode
          </Button>
        </form>

        <p className="mt-4 text-center text-sm text-text_secondary">
          No account?{" "}
          <Link to="/signup" className="text-accent hover:underline">
            Sign up
          </Link>
        </p>
      </div>
    </div>
  );
}
