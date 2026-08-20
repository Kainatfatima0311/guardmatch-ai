"use client";

import clsx from "clsx";
import Link from "next/link";
import { useEffect, useState } from "react";
import { modelInfo } from "@/lib/api";
import { useWorkspaceStatus } from "@/lib/status";
import type { ModelInfoResponse } from "@/lib/types";

/**
 * The sidebar rail.
 *
 * The supplied mockup put seven navigation items here and this application has
 * one page. Seven dead links around one live one makes a working tool read as a
 * prototype, and a reviewer reads a greyed list as what is missing rather than as
 * what is planned. So the rail keeps the mockup's shape and fills it with things
 * that are true: the one real destination, the model actually being served, and
 * what the workspace is holding right now.
 *
 * TWO LAYOUTS, ONE SET OF FACTS
 *
 * Below `lg` this was a tall column of five stacked blocks sitting above the
 * workspace, which on a phone meant scrolling past the whole rail to reach the
 * posting. It is now a compact horizontal strip at that width.
 *
 * The layout branches and the content does not: there is no second component and
 * no duplicated markup, because two renderings of one set of facts is the drift
 * risk this project keeps finding. The nav item is the one exception and it is
 * hidden below `lg` rather than laid out differently — a navigation list with a
 * single entry pointing at the page you are already on is worth no space on a
 * phone.
 *
 * THE MODEL BLOCK IS A CLAIM THE SERVICE BACKS
 *
 * "Artifacts verified" is not a label written here. `GET /model-info` only answers
 * once the service has loaded its artifacts and matched every file against its
 * recorded hash — it returns 503 until then. So the block renders *because* the
 * request succeeded, which makes it an observation rather than an assertion. When
 * the request fails it says so instead of showing nothing, since "no model
 * information" and "a model that would not verify" must not look alike.
 */
export default function Rail() {
  const [info, setInfo] = useState<ModelInfoResponse | null>(null);
  const [unavailable, setUnavailable] = useState<string | null>(null);
  const status = useWorkspaceStatus();

  useEffect(() => {
    let cancelled = false;
    modelInfo().then((response) => {
      if (cancelled) return;
      if (response.ok) setInfo(response.data);
      else setUnavailable(response.error.detail);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="flex flex-wrap items-center gap-x-6 gap-y-2 px-4 py-2.5 sm:px-6 lg:h-full lg:flex-col lg:items-stretch lg:gap-6 lg:px-3 lg:py-4">
      <div className="flex min-w-0 items-center gap-2.5">
        {/* A mark rather than a logo: two bars reading as a ranked pair, which is
            the subject of the whole page. */}
        <span
          aria-hidden="true"
          className="flex h-8 w-8 shrink-0 flex-col items-center justify-center gap-1 rounded-lg bg-primary-wash"
        >
          <span className="block h-1 w-4 rounded-full bg-primary" />
          <span className="block h-1 w-2.5 rounded-full bg-primary opacity-55" />
        </span>
        <span className="min-w-0">
          <span className="block text-sm font-semibold tracking-tight">GuardMatch</span>
          <span className="block text-2xs tracking-[0.09em] text-muted uppercase">
            Rank workspace
          </span>
        </span>
      </div>

      <nav aria-label="Sections" className="hidden lg:block">
        <Link
          href="/"
          aria-current="page"
          className="flex items-center gap-2.5 rounded-lg bg-primary-wash px-3 py-2 text-sm font-medium text-primary"
        >
          <span aria-hidden="true">▤</span>
          Rank
        </Link>
      </nav>

      <div className="flex flex-wrap items-start gap-x-6 gap-y-2 lg:flex-col lg:gap-4 lg:border-t lg:border-border lg:pt-4">
        <Group label="Model">
          {info ? (
            <>
              <Line value={info.model_version} mono />
              <p className="mt-0.5 flex items-start gap-1.5 text-2xs leading-relaxed text-pos">
                <span aria-hidden="true">✓</span>
                <span>
                  Artifacts verified
                  <span className="hidden text-muted lg:block">
                    Every file matched its recorded hash at startup, or this would not be serving.
                  </span>
                </span>
              </p>
            </>
          ) : unavailable ? (
            <p className="text-2xs leading-relaxed text-amber">{unavailable}</p>
          ) : (
            <Line value="checking…" />
          )}
        </Group>

        <Group label="Loaded">
          <Line
            value={`${status.applications} application${status.applications === 1 ? "" : "s"}`}
          />
          {status.ranked !== null && <Line value={`${status.ranked} ranked`} />}
        </Group>
      </div>

      {/* The one carrier of this guarantee that is always on screen, now that the
          amber banner above the workspace is gone. It is deliberately the last
          thing in the rail on a wide screen and a full-width line on a narrow
          one — never hidden at any width, which is the property that made
          removing the banner safe. */}
      <div className="w-full rounded-lg border border-border bg-surface-2 px-3 py-2 lg:mt-auto lg:py-2.5">
        <p className="flex items-start gap-1.5 text-2xs leading-relaxed text-muted">
          <span aria-hidden="true" className="text-primary">
            ⓘ
          </span>
          <span>This is a shortlisting aid only. Final hiring decisions are made by humans.</span>
        </p>
      </div>
    </div>
  );
}

function Group({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className={clsx("min-w-0", "lg:px-1")}>
      <p className="text-2xs font-medium tracking-[0.09em] text-muted uppercase">{label}</p>
      <div className="mt-0.5 lg:mt-1">{children}</div>
    </div>
  );
}

function Line({ value, mono }: { value: string; mono?: boolean }) {
  return <p className={mono ? "tabular text-xs" : "text-xs"}>{value}</p>;
}
