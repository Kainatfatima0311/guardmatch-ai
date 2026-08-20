/**
 * Initials, from a name that never leaves the browser.
 *
 * The display name comes from the file a reviewer dropped and is held only
 * client-side — `name` is a blocked attribute in this system, so it is not in the
 * request and the service would refuse it if it were. The avatar is therefore
 * derived from something the model has never seen, which is the point.
 *
 * EVERY AVATAR IS THE SAME COLOUR, AND THAT IS DELIBERATE
 *
 * The supplied mockup gave each candidate a different hue — green, blue, orange,
 * pink. This palette reserves its colours for meaning: amber is a constraint on
 * how the output may be used, positive and negative are the direction of a SHAP
 * contribution, primary is an interactive affordance and the leading candidate.
 * An orange avatar would read as a warning about that person and a green one as
 * something in their favour, neither of which anything here is claiming.
 *
 * So the initials carry the identity and the hue carries nothing. Reserving
 * colour is what lets a reader learn the language once, and spending it on
 * decoration is how that stops working.
 */
export default function Avatar({ name }: { name: string }) {
  return (
    <span
      aria-hidden="true"
      className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-border bg-surface-2 text-2xs font-semibold text-muted"
    >
      {initials(name)}
    </span>
  );
}

/**
 * At most two letters, from the first and last word that has one.
 *
 * Falls back to the first character of anything usable, and to a neutral glyph
 * rather than an empty circle when there is nothing — a reference like `c_00042`
 * has no letters at all until the underscore is stripped.
 */
export function initials(name: string): string {
  const words = name
    .replace(/\.[a-z0-9]+$/i, "") // a file extension is not part of a name
    .split(/[\s_\-.]+/)
    .map((w) => w.replace(/[^\p{L}\p{N}]/gu, ""))
    .filter(Boolean);

  if (words.length === 0) return "·";
  if (words.length === 1) return words[0]!.slice(0, 2).toUpperCase();
  return (words[0]![0]! + words[words.length - 1]![0]!).toUpperCase();
}
