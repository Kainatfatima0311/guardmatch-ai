"use client";

import clsx from "clsx";
import type {
  ButtonHTMLAttributes,
  InputHTMLAttributes,
  ReactNode,
  SelectHTMLAttributes,
} from "react";
import { useId } from "react";

/**
 * The building blocks this interface needs.
 *
 * Written here rather than pulled from a component library, because the whole
 * requirement is a form, a disclosure and a horizontal bar — and a bar is a div
 * with a width. A kit would add a dependency tree larger than the app it serves.
 *
 * Two rules hold across all of them. `--border-strong` is used for anything a
 * user can interact with, since WCAG asks 3:1 of a control boundary and the
 * decorative `--border` is deliberately below that. And no state is ever
 * signalled by colour alone: every chip carries a glyph, every switch an
 * `aria-checked`, every error an icon as well as a tint.
 */

/* --------------------------------------------------------------------------
   Surfaces
   -------------------------------------------------------------------------- */

export function Card({
  children,
  className,
  raised,
}: {
  children: ReactNode;
  className?: string;
  raised?: boolean;
}) {
  return (
    <section
      className={clsx(
        "overflow-hidden rounded-xl border border-border bg-surface",
        raised ? "shadow-[var(--shadow-raised)]" : "shadow-[var(--shadow-card)]",
        className,
      )}
    >
      {children}
    </section>
  );
}

/**
 * A numbered section header.
 *
 * The step number is the point. Three cards stacked in a column read as three
 * unrelated panels; the same three numbered read as a sequence with an order to
 * work through. It is a visual affordance only — nothing is gated on finishing a
 * step, because a reviewer may fill these in whatever order suits them.
 *
 * A HAIRLINE RULE, NOT A FILLED BAND
 *
 * This header used to sit on `surface-2`. With three input cards and a card per
 * candidate, that made the page a stack of banded boxes, and the band was making
 * a claim that is not true: a fill says the header is a different *kind* of
 * surface from the content, when all that is true is that one thing ends and
 * another begins. A rule says only the second.
 *
 * Which means the separation has to come from type and space instead, and it
 * does — the title is `text-base font-semibold` against `text-sm` content. The
 * rule is a hint, not the mechanism, which is why `--border` at 1.3:1 is right
 * here: WCAG 1.4.11's 3:1 governs the boundary of a *control*, and `--border-strong`
 * exists for those. Darkening a decorative rule to pass a check that does not
 * apply to it would make every card heavier to no benefit.
 */
export function CardHeader({
  step,
  title,
  subtitle,
  actions,
}: {
  step?: number;
  title: string;
  subtitle?: string;
  actions?: ReactNode;
}) {
  return (
    <header className="flex flex-wrap items-start justify-between gap-x-4 gap-y-3 border-b border-border px-4 py-3.5 sm:px-6 sm:py-4">
      <div className="flex min-w-0 items-start gap-3">
        {step !== undefined && (
          <span
            aria-hidden="true"
            className="tabular mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-primary-wash text-2xs font-semibold text-primary"
          >
            {step}
          </span>
        )}
        <div className="min-w-0">
          <h2 className="text-base font-semibold tracking-tight">{title}</h2>
          {subtitle && <p className="mt-0.5 text-sm text-muted">{subtitle}</p>}
        </div>
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </header>
  );
}

/**
 * Padding that answers to the width it is given.
 *
 * One fixed value from phone to monitor means the same cramped gutter on a wide
 * screen that a narrow one needs. The step at `sm` is small on purpose: a
 * responsive scale with many steps is a scale nobody can hold in their head, and
 * two values cover the difference that actually matters here.
 */
export function CardBody({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={clsx("px-4 py-4 sm:px-6 sm:py-5", className)}>{children}</div>;
}

/* --------------------------------------------------------------------------
   Form controls
   -------------------------------------------------------------------------- */

export function Field({
  label,
  hint,
  error,
  children,
}: {
  label: string;
  hint?: string;
  error?: string;
  children: (props: { id: string; "aria-describedby": string | undefined }) => ReactNode;
}) {
  const id = useId();
  const hintId = hint ? `${id}-hint` : undefined;
  const errorId = error ? `${id}-error` : undefined;
  const describedBy = [hintId, errorId].filter(Boolean).join(" ") || undefined;

  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="text-sm font-medium">
        {label}
      </label>
      {children({ id, "aria-describedby": describedBy })}
      {hint && (
        <p id={hintId} className="text-xs leading-relaxed text-muted">
          {hint}
        </p>
      )}
      {error && (
        <p id={errorId} className="flex items-center gap-1.5 text-xs font-medium text-neg">
          <span aria-hidden="true">▲</span>
          {error}
        </p>
      )}
    </div>
  );
}

const CONTROL =
  "w-full rounded-lg border border-border-strong bg-surface-2 px-3 py-2 text-sm " +
  "transition-colors placeholder:text-muted hover:border-primary " +
  "disabled:cursor-not-allowed disabled:opacity-55";

export function TextInput({
  invalid,
  ...props
}: InputHTMLAttributes<HTMLInputElement> & { invalid?: boolean }) {
  return (
    <input
      {...props}
      aria-invalid={invalid || undefined}
      className={clsx(CONTROL, invalid && "border-neg", props.className)}
    />
  );
}

export function Select({
  options,
  placeholder,
  invalid,
  ...props
}: SelectHTMLAttributes<HTMLSelectElement> & {
  options: readonly { value: string; label: string }[];
  placeholder?: string;
  invalid?: boolean;
}) {
  return (
    <select
      {...props}
      aria-invalid={invalid || undefined}
      className={clsx(CONTROL, "cursor-pointer", invalid && "border-neg", props.className)}
    >
      {placeholder && (
        <option value="" disabled>
          {placeholder}
        </option>
      )}
      {options.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  );
}

/**
 * A toggleable chip. `aria-pressed` carries the state for assistive technology,
 * and the glyph carries it for anyone who cannot separate the selected fill from
 * the unselected one.
 */
export function Chip({
  selected,
  onToggle,
  children,
  note,
}: {
  selected: boolean;
  onToggle: () => void;
  children: ReactNode;
  note?: string;
}) {
  return (
    <button
      type="button"
      aria-pressed={selected}
      onClick={onToggle}
      title={note}
      className={clsx(
        "inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-medium transition-colors",
        selected
          ? "border-primary bg-primary text-primary-contrast shadow-[var(--shadow-sm)]"
          : "border-border-strong bg-surface-2 text-muted hover:border-primary hover:text-text",
      )}
    >
      <span aria-hidden="true" className="text-2xs">
        {selected ? "✓" : "+"}
      </span>
      {children}
    </button>
  );
}

export function Toggle({
  checked,
  onChange,
  label,
  hint,
}: {
  checked: boolean;
  onChange: (next: boolean) => void;
  label: string;
  hint?: string;
}) {
  const id = useId();
  return (
    <div className="flex items-start gap-3 rounded-lg border border-border bg-surface-2 px-3 py-3">
      <button
        type="button"
        id={id}
        role="switch"
        aria-checked={checked}
        onClick={() => onChange(!checked)}
        className={clsx(
          "mt-0.5 inline-flex shrink-0 items-center rounded-full border transition-colors",
          checked ? "border-primary bg-primary" : "border-border-strong bg-surface-3",
        )}
        style={{ height: "1.375rem", width: "2.5rem" }}
      >
        <span
          aria-hidden="true"
          className={clsx(
            "rounded-full transition-transform",
            checked ? "bg-primary-contrast" : "bg-muted",
          )}
          style={{
            height: "0.875rem",
            width: "0.875rem",
            marginLeft: "0.1875rem",
            transform: checked ? "translateX(1.0625rem)" : "none",
          }}
        />
      </button>
      <label htmlFor={id} className="cursor-pointer text-sm">
        <span className="font-medium">{label}</span>
        {hint && <span className="mt-0.5 block text-xs text-muted">{hint}</span>}
      </label>
    </div>
  );
}

/* --------------------------------------------------------------------------
   Actions
   -------------------------------------------------------------------------- */

export function Button({
  variant = "secondary",
  size = "md",
  className,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "ghost" | "danger";
  size?: "sm" | "md";
}) {
  return (
    <button
      {...props}
      className={clsx(
        "inline-flex items-center justify-center gap-2 rounded-lg font-medium transition-colors",
        "disabled:cursor-not-allowed disabled:opacity-50",
        size === "sm" ? "px-2.5 py-1.5 text-xs" : "px-4 py-2.5 text-sm",
        variant === "primary" &&
          "bg-primary text-primary-contrast shadow-[var(--shadow-sm)] hover:bg-primary-hover",
        variant === "secondary" &&
          "border border-border-strong bg-surface-2 text-text hover:border-primary",
        variant === "ghost" && "text-muted hover:bg-surface-2 hover:text-text",
        variant === "danger" && "text-muted hover:bg-neg-wash hover:text-neg",
        className,
      )}
    />
  );
}

/** A small labelled figure, for counts, versions and correlation ids. */
export function Stat({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex min-w-0 flex-col gap-0.5">
      <span className="text-2xs tracking-wide text-muted uppercase">{label}</span>
      <span className={clsx("truncate text-sm", mono && "tabular")} title={value}>
        {value}
      </span>
    </div>
  );
}
