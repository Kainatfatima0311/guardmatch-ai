"use client";

import { createContext, useCallback, useContext, useMemo, useState } from "react";
import type { ReactNode } from "react";

/**
 * What the workspace is currently holding, so the sidebar rail can say so.
 *
 * The rail lives in the page frame and the counts live in the workspace, which
 * are different components with no parent-child relationship between them. The
 * alternatives were to lift the whole workspace's state into the layout — which
 * would make the frame own the thing it frames — or to leave the rail decorative.
 *
 * Deliberately tiny: two numbers and a setter. It is not an application store and
 * should not become one. Anything that both the rail and the workspace need to
 * *act* on belongs in the workspace, not here; this carries only what the frame
 * displays.
 */
export interface WorkspaceStatus {
  /** Applications currently loaded, whether typed, dropped or generated. */
  applications: number;
  /** Placements in the current shortlist, or null when nothing has been ranked. */
  ranked: number | null;
  /**
   * The posting being worked on, for the header.
   *
   * Deliberately here and not the counts: the header says *what you are working
   * on* and the rail says *what is loaded and what is serving you*. Putting a
   * count in both would repeat one figure under two names on one screen, which is
   * a defect this project has already had to fix once.
   */
  posting: string | null;
}

const EMPTY: WorkspaceStatus = { applications: 0, ranked: null, posting: null };

const StatusContext = createContext<WorkspaceStatus>(EMPTY);
const SetStatusContext = createContext<(next: WorkspaceStatus) => void>(() => {});

export function StatusProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<WorkspaceStatus>(EMPTY);

  // Memoised so a consumer that only reads the setter does not re-render every
  // time the counts change.
  const publish = useCallback((next: WorkspaceStatus) => {
    setStatus((prev) =>
      prev.applications === next.applications &&
      prev.ranked === next.ranked &&
      prev.posting === next.posting
        ? prev
        : next,
    );
  }, []);

  const value = useMemo(() => status, [status]);

  return (
    <SetStatusContext.Provider value={publish}>
      <StatusContext.Provider value={value}>{children}</StatusContext.Provider>
    </SetStatusContext.Provider>
  );
}

/** For the frame: what to display. */
export function useWorkspaceStatus(): WorkspaceStatus {
  return useContext(StatusContext);
}

/** For the workspace: publish what you are holding. */
export function usePublishStatus(): (next: WorkspaceStatus) => void {
  return useContext(SetStatusContext);
}
