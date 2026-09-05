import { BrowserRouter, Routes, Route } from "react-router-dom";
import { Button } from "@/components/ui/button";

function HomePage() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-4 bg-background">
      <h1 className="text-2xl font-semibold text-text_primary">
        Urban Furniture Accounting — Setup OK
      </h1>
      <p className="text-sm text-text_secondary">
        Frontend skeleton is wired up: Vite, React Router, Tailwind, shadcn/ui.
      </p>
      <Button>It works</Button>
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<HomePage />} />
      </Routes>
    </BrowserRouter>
  );
}
