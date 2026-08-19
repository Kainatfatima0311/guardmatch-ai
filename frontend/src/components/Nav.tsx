"use client";

import clsx from "clsx";
import Link from "next/link";
import { usePathname } from "next/navigation";

/**
 * The page nav.
 *
 * The two pages after Rank are the point. The fairness audit is enforced in CI on
 * every push, and the model's provenance is served by the API on every request —
 * and until each had a page, both were readable only by opening a JSON file. A
 * check nobody looks at is a check in name.
 */
const PAGES = [
  { href: "/", label: "Rank" },
  { href: "/fairness", label: "Fairness" },
  { href: "/model", label: "Model" },
] as const;

export default function Nav() {
  const pathname = usePathname();

  return (
    <nav aria-label="Sections" className="flex items-center gap-1">
      {PAGES.map((page) => {
        const active = pathname === page.href;
        return (
          <Link
            key={page.href}
            href={page.href}
            aria-current={active ? "page" : undefined}
            className={clsx(
              "rounded-lg px-2.5 py-1.5 text-sm transition-colors",
              active
                ? "bg-primary-wash font-medium text-primary"
                : "text-muted hover:bg-surface-2 hover:text-text",
            )}
          >
            {page.label}
          </Link>
        );
      })}
    </nav>
  );
}
