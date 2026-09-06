import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Link, useNavigate } from "react-router-dom";
import { FieldError } from "@/components/shared/FieldError";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
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
      .min(1, "Login ID is required")
      .regex(LOGIN_ID_REGEX, "login_id must be 6-12 characters: letters, digits and underscore only"),
    email: z.string().min(1, "Email is required").email("Enter a valid email address"),
    password: z
      .string()
      .min(1, "Password is required")
      .regex(
        PASSWORD_REGEX,
        "password must be at least 9 characters and include an uppercase letter, a lowercase letter and a special character",
      ),
    confirm_password: z.string().min(1, "Confirm your password"),
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
              htmlFor="email"
              required
              className="mb-1 block text-xs font-medium text-text_secondary"
            >
              Email
            </Label>
            <Input id="email" type="email" autoComplete="email" {...register("email")} />
            <FieldError message={errors.email?.message} />
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
              autoComplete="new-password"
              {...register("password")}
            />
            <FieldError message={errors.password?.message} />
          </div>

          <div>
            <Label
              htmlFor="confirm_password"
              required
              className="mb-1 block text-xs font-medium text-text_secondary"
            >
              Confirm password
            </Label>
            <Input
              id="confirm_password"
              type="password"
              autoComplete="new-password"
              {...register("confirm_password")}
            />
            <FieldError message={errors.confirm_password?.message} />
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
