import { BrowserRouter, Routes, Route } from "react-router-dom";
import { AppShell } from "@/components/layout/AppShell";
import { RequireAuth } from "@/components/RequireAuth";
import { AuthProvider } from "@/hooks/useAuth";
import { Toaster } from "@/components/ui/toaster";
import ComponentsPreview from "@/dev/ComponentsPreview";
import Login from "@/pages/auth/Login";
import Signup from "@/pages/auth/Signup";
import Contacts from "@/pages/masters/Contacts";
import Products from "@/pages/masters/Products";
import Analytics from "@/pages/masters/Analytics";

function DashboardPage() {
  return (
    <div className="flex flex-col gap-2">
      <h1 className="text-2xl font-semibold text-text_primary">Dashboard</h1>
      <p className="text-sm text-text_secondary">
        You're logged in. The real dashboard widgets land in a later phase.
      </p>
    </div>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Toaster />
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/signup" element={<Signup />} />

          {/* Temporary — not part of real navigation, and deliberately not
              behind the auth guard so anyone reviewing components doesn't
              need a login. See ComponentsPreview.tsx. */}
          <Route element={<AppShell />}>
            <Route path="/dev/components" element={<ComponentsPreview />} />
          </Route>

          <Route
            element={
              <RequireAuth>
                <AppShell />
              </RequireAuth>
            }
          >
            <Route path="/" element={<DashboardPage />} />
            <Route path="/masters/contacts" element={<Contacts />} />
            <Route path="/masters/products" element={<Products />} />
            <Route path="/masters/analytics" element={<Analytics />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}
