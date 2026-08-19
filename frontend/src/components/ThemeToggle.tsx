"use client";

import clsx from "clsx";
import { useSyncExternalStore } from "react";

/**
 * Three states, not two.
 *
 * "System" is a real choice and the default one: it means "follow the OS", and a
 * two-way toggle silently removes it the first time anyone clicks. The stored
 * value is therefore absent, "light" or "dark" — and absent is not the same as
 * light, which is why `data-theme` is removed rather than set when system wins.
 *
 * The matching palette lives in globals.css, where each theme is declared twice
 * on purpose — once under `prefers-color-scheme` and once under `[data-theme]` —
 * so an explicit choice wins even when it disagrees with the OS.
 *
 * The initial value is applied by an inline script in the layout, before first
 * paint, so there is no flash of the wrong theme. This component only reads it
 * back, through `useSyncExternalStore` rather than an effect: localStorage is
 * external state, and reading it that way gives a correct server snapshot for
 * hydration and a subscription that keeps two open tabs in step for free.
 */

type Choice = "system" | "light" | "dark";

const STORAGE_KEY = "guardmatch-theme";

const OPTIONS: { value: Choice; label: string; glyph: string }[] = [
  { value: "light", label: "Light", glyph: "☀" },
  { value: "dark", label: "Dark", glyph: "☾" },
  { value: "system", label: "System", glyph: "◐" },
];

/** Notified by other tabs via `storage`, and by this one via a manual dispatch. */
function subscribe(onChange: () => void): () => void {
  window.addEventListener("storage", onChange);
  window.addEventListener(STORAGE_KEY, onChange);
  return () => {
    window.removeEventListener("storage", onChange);
    window.removeEventListener(STORAGE_KEY, onChange);
  };
}

function readChoice(): Choice {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    return stored === "light" || stored === "dark" ? stored : "system";
  } catch {
    // Private-browsing modes can throw on access. Following the OS is the right
    // fallback, and it is what the CSS does with no attribute set anyway.
    return "system";
  }
}

/** During server render nothing is stored yet, so the OS is what will apply. */
function serverChoice(): Choice {
  return "system";
}

function apply(choice: Choice): void {
  const root = document.documentElement;
  if (choice === "system") {
    delete root.dataset.theme;
    localStorage.removeItem(STORAGE_KEY);
  } else {
    root.dataset.theme = choice;
    localStorage.setItem(STORAGE_KEY, choice);
  }
  // `storage` does not fire in the tab that made the change.
  window.dispatchEvent(new Event(STORAGE_KEY));
}

export default function ThemeToggle() {
  const choice = useSyncExternalStore(subscribe, readChoice, serverChoice);

  return (
    <div
      role="group"
      aria-label="Colour theme"
      className="inline-flex rounded-lg border border-border-strong bg-surface-2 p-0.5"
    >
      {OPTIONS.map((option) => {
        const active = choice === option.value;
        return (
          <button
            key={option.value}
            type="button"
            aria-pressed={active}
            onClick={() => apply(option.value)}
            className={clsx(
              "rounded-md px-2 py-1 text-xs transition-colors",
              active ? "bg-primary text-primary-contrast font-medium" : "text-muted",
            )}
          >
            <span aria-hidden="true">{option.glyph}</span>
            <span className="sr-only sm:not-sr-only sm:ml-1.5">{option.label}</span>
          </button>
        );
      })}
    </div>
  );
}
