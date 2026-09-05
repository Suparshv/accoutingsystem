import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Link, useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useAuth } from "@/hooks/useAuth";
import { normaliseError } from "@/lib/api";
import { applyServerErrors } from "@/lib/form-errors";

// Mirrors backend/app/schemas/auth.py's LOGIN_ID_REGEX / PASSWORD_REGEX and
// their exact messages, per SPEC.md §13.5 ("same limits, same messages").
// Self-signup always becomes an "accountant" (SPEC.md §9) — there's no role
// field on this form.
const LOGIN_ID_REGEX = /^[A-Za-z0-9_]{6,12}$/;
const PASSWORD_REGEX = /^(?=.*[a-z])(?=.*[A-Z])(?=.*[^A-Za-z0-9]).{9,}$/;

const signupSchema = z
  .object({
    login_id: z
      .string()
      .regex(LOGIN_ID_REGEX, "login_id must be 6-12 characters: letters, digits and underscore only"),
    email: z.string().email("Enter a valid email address"),
    password: z
      .string()
      .regex(
        PASSWORD_REGEX,
        "password must be at least 9 characters and include an uppercase letter, a lowercase letter and a special character",
      ),
    confirm_password: z.string(),
  })
  .refine((data) => data.password === data.confirm_password, {
    message: "confirm_password must match password",
    path: ["confirm_password"],
  });
type SignupFormValues = z.infer<typeof signupSchema>;

export default function Signup() {
  const { signup } = useAuth();
  const navigate = useNavigate();
  const [formError, setFormError] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<SignupFormValues>({ resolver: zodResolver(signupSchema) });

  async function onSubmit(values: SignupFormValues) {
    setFormError(null);
    try {
      await signup({
        loginId: values.login_id,
        email: values.email,
        password: values.password,
        confirmPassword: values.confirm_password,
      });
      navigate("/", { replace: true });
    } catch (e) {
      const apiError = normaliseError(e);
      const handled = applyServerErrors(apiError, setError, {
        LOGIN_ID_TAKEN: "login_id",
        EMAIL_TAKEN: "email",
      });
      if (!handled) setFormError(apiError.message);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-surface px-4">
      <div className="w-full max-w-sm rounded border border-border bg-background p-6">
        <h1 className="text-xl font-semibold text-text_primary">Create an account</h1>
        <p className="mt-1 text-sm text-text_secondary">Urban Furniture Accounting</p>

        <form onSubmit={handleSubmit(onSubmit)} noValidate className="mt-6 flex flex-col gap-4">
          {formError && (
            <p role="alert" className="rounded-md bg-danger/10 px-3 py-2 text-sm text-danger">
              {formError}
            </p>
          )}

          <div>
            <label
              htmlFor="login_id"
              className="mb-1 block text-xs font-medium text-text_secondary"
            >
              Login ID
            </label>
            <Input id="login_id" autoComplete="username" {...register("login_id")} />
            {errors.login_id && (
              <p className="mt-1 text-xs text-danger">{errors.login_id.message}</p>
            )}
          </div>

          <div>
            <label htmlFor="email" className="mb-1 block text-xs font-medium text-text_secondary">
              Email
            </label>
            <Input id="email" type="email" autoComplete="email" {...register("email")} />
            {errors.email && <p className="mt-1 text-xs text-danger">{errors.email.message}</p>}
          </div>

          <div>
            <label
              htmlFor="password"
              className="mb-1 block text-xs font-medium text-text_secondary"
            >
              Password
            </label>
            <Input
              id="password"
              type="password"
              autoComplete="new-password"
              {...register("password")}
            />
            {errors.password && (
              <p className="mt-1 text-xs text-danger">{errors.password.message}</p>
            )}
          </div>

          <div>
            <label
              htmlFor="confirm_password"
              className="mb-1 block text-xs font-medium text-text_secondary"
            >
              Confirm password
            </label>
            <Input
              id="confirm_password"
              type="password"
              autoComplete="new-password"
              {...register("confirm_password")}
            />
            {errors.confirm_password && (
              <p className="mt-1 text-xs text-danger">{errors.confirm_password.message}</p>
            )}
          </div>

          <Button type="submit" disabled={isSubmitting} className="mt-2">
            {isSubmitting ? "Creating account..." : "Sign up"}
          </Button>
        </form>

        <p className="mt-4 text-center text-sm text-text_secondary">
          Already have an account?{" "}
          <Link to="/login" className="text-accent hover:underline">
            Log in
          </Link>
        </p>
      </div>
    </div>
  );
}
