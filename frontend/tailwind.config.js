/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        // Design tokens — the ONLY place a hex value appears. Components always
        // reference these by name (bg-surface, text-text_secondary, ...).
        //
        // Restyled to match Odoo's own visual identity rather than SPEC.md
        // §13.1's original palette: muted plum primary, near-white greys, and
        // deliberately NO GREEN anywhere — Odoo doesn't use it, so "success"
        // states (paid / achieved / balanced) are a muted rose-plum instead.
        background: "#FFFFFF",
        surface: "#F8F9FA",
        border: "#E0E0E0",
        text_primary: "#212529",
        text_secondary: "#6C757D",
        primary_hover: "#5C3B54",
        success: "#6C4F63", // muted rose/plum — intentionally not green
        warning: "#B08D57", // muted amber/gold
        danger: "#A94442", // muted brick red
        draft: "#ADB5BD", // neutral grey

        // shadcn/ui semantic tokens — resolved via CSS variables in src/index.css,
        // which are pinned to the same SPEC.md palette. Required by the shadcn
        // primitives (Button, Dialog, Tabs, Toast, ...) for their variant classes.
        foreground: "var(--foreground)",
        primary: {
          DEFAULT: "var(--primary)",
          foreground: "var(--primary-foreground)",
        },
        accent: {
          DEFAULT: "var(--accent)",
          foreground: "var(--accent-foreground)",
        },
        card: {
          DEFAULT: "var(--card)",
          foreground: "var(--card-foreground)",
        },
        popover: {
          DEFAULT: "var(--popover)",
          foreground: "var(--popover-foreground)",
        },
        secondary: {
          DEFAULT: "var(--secondary)",
          foreground: "var(--secondary-foreground)",
        },
        muted: {
          DEFAULT: "var(--muted)",
          foreground: "var(--muted-foreground)",
        },
        destructive: {
          DEFAULT: "var(--destructive)",
          foreground: "var(--destructive-foreground)",
        },
        input: "var(--input)",
        ring: "var(--ring)",
        chart: {
          1: "var(--chart-1)",
          2: "var(--chart-2)",
          3: "var(--chart-3)",
          4: "var(--chart-4)",
          5: "var(--chart-5)",
        },
        sidebar: {
          DEFAULT: "var(--sidebar)",
          foreground: "var(--sidebar-foreground)",
          primary: "var(--sidebar-primary)",
          "primary-foreground": "var(--sidebar-primary-foreground)",
          accent: "var(--sidebar-accent)",
          "accent-foreground": "var(--sidebar-accent-foreground)",
          border: "var(--sidebar-border)",
          ring: "var(--sidebar-ring)",
        },
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
      },
    },
  },
  plugins: [require("tailwindcss-animate")],
};
