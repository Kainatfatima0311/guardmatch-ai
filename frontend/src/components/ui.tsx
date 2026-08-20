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

/**
 * A panel.
 *
 * Elevated again, for the supplied mockup's light and soft treatment. The Console
 * phase made these flat and defined them by a rule, which was right for a
 * near-black ground where a shadow reads as a smudge; on this ground depth is
 * legible and the mockup uses it.
 *
 * `emphasis` still puts its marker on the **border** rather than on the shadow,
 * even though there is depth to spend now. A border survives a screenshot, a
 * print, and a viewer who cannot separate two shadows, and the leading candidate
 * is exactly the thing that must not depend on subtle rendering.
 */
export function Card({
  children,
  className,
  emphasis,
}: {
  children: ReactNode;
  className?: string;
  emphasis?: boolean;
}) {
  return (
    <section
      className={clsx(
        "overflow-hidden rounded-xl border bg-surface shadow-[var(--shadow-card)]",
        emphasis ? "border-primary" : "border-border",
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
 * does. The rule is a hint, not the mechanism, which is why `--border` at 1.3:1
 * is right here: WCAG 1.4.11's 3:1 governs the boundary of a *control*, and
 * `--border-strong` exists for those. Darkening a decorative rule to pass a check
 * that does not apply to it would make every panel heavier to no benefit.
 *
 * A TITLE AND AN ICON, PER THE SUPPLIED MOCKUP
 *
 * The Console phase set this as a small tracked uppercase label on the argument
 * that a heading competes with the content for the reader's first look. That
 * argument still holds and is worth keeping on the record — but the panels are now
 * three named regions in a workspace rather than rows in a dense table, and the
 * step header above them carries the sequence, so the panel titles no longer have
 * to earn their space by getting out of the way.
 *
 * The icon is decorative and `aria-hidden`. It is a landmark for someone
 * scanning, not information — every panel's meaning is in its title.
 */
export function CardHeader({
  icon,
  title,
  subtitle,
  actions,
}: {
  /** Decorative landmark. Never the only carrier of meaning. */
  icon?: string;
  title: string;
  subtitle?: string;
  actions?: ReactNode;
}) {
  return (
    <header className="flex flex-wrap items-start justify-between gap-x-4 gap-y-2 border-b border-border px-4 py-3">
      <div className="flex min-w-0 items-center gap-2.5">
        {icon && (
          <span
            aria-hidden="true"
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary-wash text-sm text-primary"
          >
            {icon}
          </span>
        )}
        <div className="min-w-0">
          <h2 className="truncate text-sm font-semibold tracking-tight">{title}</h2>
          {subtitle && <p className="truncate text-xs text-muted">{subtitle}</p>}
        </div>
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
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
  return <div className={clsx("px-4 py-4", className)}>{children}</div>;
}

/* --------------------------------------------------------------------------
   Form controls
   -------------------------------------------------------------------------- */

export function Field({
  label,
  hint,
  error,
  inline,
  children,
}: {
  label: string;
  hint?: string;
  error?: string;
  /**
   * Label in a fixed column with the value beside it, rather than stacked above.
   * Reads as a configuration being inspected instead of a form being filled,
   * which is the right posture for a panel a reviewer returns to rather than
   * completes once. Only correct in a narrow rail: the label column is fixed, so
   * a wide container would strand the value far from its name.
   */
  inline?: boolean;
  children: (props: { id: string; "aria-describedby": string | undefined }) => ReactNode;
}) {
  const id = useId();
  const hintId = hint ? `${id}-hint` : undefined;
  const errorId = error ? `${id}-error` : undefined;
  const describedBy = [hintId, errorId].filter(Boolean).join(" ") || undefined;

  const labelClass = "text-2xs font-medium tracking-[0.07em] text-muted uppercase";
  // Indent under the control rather than under the label, so a hint reads as
  // belonging to the value it qualifies. 6rem column plus a 0.75rem gap.
  const indent = inline ? "sm:pl-[6.75rem]" : undefined;

  return (
    <div className="flex flex-col gap-1">
      {inline ? (
        <div className="flex flex-col gap-1 sm:flex-row sm:items-center sm:gap-3">
          <label htmlFor={id} className={clsx(labelClass, "sm:w-24 sm:shrink-0 sm:pt-px")}>
            {label}
          </label>
          <div className="min-w-0 sm:flex-1">
            {children({ id, "aria-describedby": describedBy })}
          </div>
        </div>
      ) : (
        <>
          <label htmlFor={id} className={labelClass}>
            {label}
          </label>
          {children({ id, "aria-describedby": describedBy })}
        </>
      )}
      {hint && (
        <p id={hintId} className={clsx("text-2xs leading-relaxed text-muted", indent)}>
          {hint}
        </p>
      )}
      {error && (
        <p
          id={errorId}
          className={clsx(
            "flex items-center gap-1.5 text-2xs font-medium text-neg",
            indent,
          )}
        >
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
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium transition-colors",
        selected
          ? "border-primary bg-primary-wash text-primary"
          : "border-border-strong bg-surface text-muted hover:border-primary hover:text-text",
      )}
    >
      {/* A checkbox glyph rather than a fill, so the selected state is legible
          without depending on the difference between two backgrounds. The
          `aria-pressed` on the button is what assistive technology reads. */}
      <span aria-hidden="true" className="text-2xs">
        {selected ? "☑" : "☐"}
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
    /* No panel around it any more. A control that sits in its own tinted box
       inside a panel is two frames deep for one switch, which is exactly the
       kind of nesting the flat treatment exists to remove. */
    <div className="flex items-start gap-2.5">
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
        {hint && <span className="mt-0.5 block text-2xs text-muted">{hint}</span>}
      </label>
    </div>
  );
}

/**
 * A range paired with the number it sets.
 *
 * The slider is for getting close quickly and the number input is for being
 * exact, and neither is sufficient alone: dragging cannot reliably land on 4.5,
 * and typing gives no sense of where 4.5 sits between 0 and 40. They edit one
 * value, so there is one label and one `id` — the range is `aria-hidden` and the
 * input is the labelled control, because two focusable controls announcing the
 * same field is worse for a screen reader than one.
 */
export function Slider({
  id,
  value,
  min,
  max,
  step,
  disabled,
  onChange,
  ...rest
}: {
  id?: string;
  value: number;
  min: number;
  max: number;
  step: number;
  disabled?: boolean;
  onChange: (next: number) => void;
} & Omit<InputHTMLAttributes<HTMLInputElement>, "value" | "onChange" | "type">) {
  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-center gap-3">
        <input
          type="range"
          aria-hidden="true"
          tabIndex={-1}
          min={min}
          max={max}
          step={step}
          value={value}
          disabled={disabled}
          onChange={(e) => onChange(Number(e.target.value))}
          className="accent-primary h-1.5 min-w-0 flex-1 cursor-pointer disabled:cursor-not-allowed disabled:opacity-55"
        />
        <input
          {...rest}
          id={id}
          type="number"
          min={min}
          max={max}
          step={step}
          value={value}
          disabled={disabled}
          onChange={(e) => onChange(Number(e.target.value) || 0)}
          className="tabular w-16 shrink-0 rounded-lg border border-border-strong bg-surface-2 px-2 py-1.5 text-center text-sm transition-colors hover:border-primary disabled:cursor-not-allowed disabled:opacity-55"
        />
      </div>
      <div aria-hidden="true" className="tabular flex justify-between text-2xs text-muted">
        <span>{min}</span>
        <span>{max}</span>
      </div>
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
        "inline-flex items-center justify-center gap-1.5 rounded-lg font-medium transition-colors",
        "disabled:cursor-not-allowed disabled:opacity-50",
        size === "sm" ? "px-2.5 py-1.5 text-xs" : "px-3.5 py-2 text-sm",
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
    <div className="flex min-w-0 flex-col">
      <span className="text-2xs tracking-[0.07em] text-muted uppercase">{label}</span>
      <span className={clsx("truncate text-xs", mono && "tabular")} title={value}>
        {value}
      </span>
    </div>
  );
}
