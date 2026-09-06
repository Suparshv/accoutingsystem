import { useState } from "react";
import { assetUrl } from "@/lib/api";
import { cn } from "@/lib/utils";

// A contact's picture, or its initials when there isn't one — which is the
// normal case, not a degraded one, so the fallback is a designed state rather
// than a broken-image icon.

const SIZES = {
  sm: "h-8 w-8 text-xs",
  md: "h-12 w-12 text-sm",
  lg: "h-28 w-28 text-2xl",
} as const;

/** Up to two initials from a contact name: "Open Wood" -> "OW". */
function initialsOf(name: string): string {
  const words = name.trim().split(/\s+/).filter(Boolean);
  if (words.length === 0) return "?";
  const letters = words.slice(0, 2).map((word) => word[0]);
  return letters.join("").toUpperCase();
}

export function ContactAvatar({
  name,
  imageUrl,
  size = "sm",
  className,
}: {
  name: string;
  imageUrl?: string | null;
  size?: keyof typeof SIZES;
  className?: string;
}) {
  // A row can point at a file that is no longer on disk. Falling back to the
  // initials keeps the list looking deliberate instead of showing the
  // browser's broken-image glyph.
  const [failed, setFailed] = useState(false);
  const src = failed ? null : assetUrl(imageUrl);

  const shared = cn(
    "shrink-0 overflow-hidden rounded-full border border-border",
    SIZES[size],
    className,
  );

  if (src) {
    return (
      <img
        src={src}
        alt=""
        onError={() => setFailed(true)}
        className={cn(shared, "object-cover")}
      />
    );
  }

  return (
    <span
      aria-hidden="true"
      className={cn(
        shared,
        "flex items-center justify-center bg-surface font-medium text-text_secondary",
      )}
    >
      {initialsOf(name)}
    </span>
  );
}
