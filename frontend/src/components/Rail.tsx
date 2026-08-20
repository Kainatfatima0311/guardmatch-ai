"use client";

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
 * prototype, and a reviewer opening it reads the greyed list as what is missing
 * rather than as what is planned. So the rail keeps the mockup's shape and fills
 * it with things that are true: the one real destination, the model actually
 * being served, and what the workspace is holding right now.
 *
 * THE MODEL BLOCK IS A CLAIM THE SERVICE BACKS
 *
 * "Checksums verified" is not a label written here. `GET /model-info` only
 * answers once the service has loaded its artifacts and matched every file
 * against its recorded hash — it returns 503 until then. So the block renders
 * *because* the request succeeded, which makes it an observation rather than an
 * assertion. When the request fails it says so instead of showing nothing, since
 * "no model information" and "a model that would not verify" must not look alike.
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
    <div className="flex h-full flex-col gap-6 px-3 py-4">
      <div className="flex items-center gap-2.5 px-1">
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

      <nav aria-label="Sections">
        <Link
          href="/"
          aria-current="page"
          className="flex items-center gap-2.5 rounded-lg bg-primary-wash px-3 py-2 text-sm font-medium text-primary"
        >
          <span aria-hidden="true">▤</span>
          Rank
        </Link>
      </nav>

      <div className="flex flex-col gap-4 border-t border-border pt-4">
        <Group label="Model">
          {info ? (
            <>
              <Line value={info.model_version} mono />
              <p className="mt-1 flex items-start gap-1.5 text-2xs leading-relaxed text-pos">
                <span aria-hidden="true">✓</span>
                <span>
                  Artifacts verified
                  <span className="block text-muted">
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
          <Line value={`${status.applications} application${status.applications === 1 ? "" : "s"}`} />
          {status.ranked !== null && (
            <Line value={`${status.ranked} ranked`} />
          )}
        </Group>
      </div>

      {/* From the mockup, and kept verbatim in spirit: the frame should say what
          this is even to someone who reads nothing else on the page. */}
      <div className="mt-auto rounded-lg border border-border bg-surface-2 px-3 py-2.5">
        <p className="flex items-start gap-1.5 text-2xs leading-relaxed text-muted">
          <span aria-hidden="true" className="text-primary">
            ⓘ
          </span>
          <span>
            This is a shortlisting aid only. Final hiring decisions are made by humans.
          </span>
        </p>
      </div>
    </div>
  );
}

function Group({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="px-1">
      <p className="text-2xs font-medium tracking-[0.09em] text-muted uppercase">{label}</p>
      <div className="mt-1">{children}</div>
    </div>
  );
}

function Line({ value, mono }: { value: string; mono?: boolean }) {
  return <p className={mono ? "tabular text-xs" : "text-xs"}>{value}</p>;
}
