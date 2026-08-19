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
 * The small set of building blocks this interface needs.
 *
 * Written here rather than pulled from a component library, because the whole
 * requirement is a form, a disclosure and a horizontal bar — and a bar is a div
 * with a width. A kit would add a dependency tree larger than the app it serves.
 *
 * Two rules hold across all of them: `--border-strong` is used for anything a
 * user can interact with, since WCAG asks 3:1 of a control boundary and the
 * decorative `--border` is 1.3:1; and state is never signalled by colour alone.
 */

export function Card({
  title,
  subtitle,
  actions,
  children,
  className,
}: {
  title?: string;
  subtitle?: string;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section
      className={clsx(
        "rounded-xl border border-border bg-surface shadow-[var(--shadow)]",
        className,
      )}
    >
      {(title || actions) && (
        <header className="flex flex-wrap items-start justify-between gap-3 border-b border-border px-5 py-4">
          <div>
            {title && <h2 className="font-semibold tracking-tight">{title}</h2>}
            {subtitle && <p className="mt-0.5 text-sm text-muted">{subtitle}</p>}
          </div>
          {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
        </header>
      )}
      <div className="px-5 py-4">{children}</div>
    </section>
  );
}

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
        <p id={hintId} className="text-xs text-muted">
          {hint}
        </p>
      )}
      {error && (
        <p id={errorId} className="text-xs text-neg">
          {error}
        </p>
      )}
    </div>
  );
}

const controlClass =
  "w-full rounded-lg border border-border-strong bg-surface-2 px-3 py-2 text-sm " +
  "placeholder:text-muted disabled:opacity-60";

export function TextInput(props: InputHTMLAttributes<HTMLInputElement>) {
  return <input {...props} className={clsx(controlClass, props.className)} />;
}

export function Select({
  options,
  placeholder,
  ...props
}: SelectHTMLAttributes<HTMLSelectElement> & {
  options: readonly { value: string; label: string }[];
  placeholder?: string;
}) {
  return (
    <select {...props} className={clsx(controlClass, props.className)}>
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
 * and the check glyph carries it for anyone who cannot separate the selected
 * fill from the unselected one.
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
        "inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-sm transition-colors",
        selected
          ? "border-primary bg-primary text-primary-contrast font-medium"
          : "border-border-strong bg-surface-2 text-text hover:bg-surface",
      )}
    >
      <span aria-hidden="true" className="text-xs">
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
    <div className="flex items-start gap-3">
      <button
        type="button"
        id={id}
        role="switch"
        aria-checked={checked}
        onClick={() => onChange(!checked)}
        className={clsx(
          "mt-0.5 inline-flex h-6 w-11 shrink-0 items-center rounded-full border transition-colors",
          checked ? "border-primary bg-primary" : "border-border-strong bg-surface-2",
        )}
      >
        <span
          aria-hidden="true"
          className={clsx(
            "ml-0.5 h-4.5 w-4.5 rounded-full transition-transform",
            checked ? "translate-x-5 bg-primary-contrast" : "bg-muted",
          )}
          style={{ height: "1.125rem", width: "1.125rem" }}
        />
      </button>
      <label htmlFor={id} className="text-sm">
        <span className="font-medium">{label}</span>
        {hint && <span className="block text-xs text-muted">{hint}</span>}
      </label>
    </div>
  );
}

export function Button({
  variant = "secondary",
  className,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "ghost";
}) {
  return (
    <button
      {...props}
      className={clsx(
        "inline-flex items-center justify-center gap-2 rounded-lg px-4 py-2 text-sm font-medium",
        "disabled:cursor-not-allowed disabled:opacity-50",
        variant === "primary" && "bg-primary text-primary-contrast",
        variant === "secondary" && "border border-border-strong bg-surface-2 text-text",
        variant === "ghost" && "text-muted hover:text-text",
        className,
      )}
    />
  );
}
