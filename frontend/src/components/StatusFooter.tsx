import { Stat } from "./ui";

/**
 * What answered, and which trace to look for.
 *
 * `request_id` is the same correlation id the service puts on every structured log
 * line for that request, and it is generated in the browser and preserved through
 * the proxy. Showing it turns "the ranking looked wrong" into a report someone can
 * act on, because the exact log entry can be found from it. Without it, a user
 * report and a log file have nothing in common.
 *
 * It deliberately does not repeat the number of applications. It used to, as
 * "Applications", while the shortlist header carried the same figure as "Ranked"
 * — one number under two names on one screen, which invites a reader to wonder
 * whether they are the same thing. The count sits with the list; this reports
 * only what answered.
 */
export default function StatusFooter({
  modelVersion,
  requestId,
}: {
  modelVersion: string;
  requestId: string;
}) {
  return (
    <div className="flex flex-wrap items-start gap-x-8 gap-y-3 rounded-xl border border-border bg-surface-2 px-4 py-3">
      <Stat label="Model" value={modelVersion} mono />
      <div className="min-w-0 flex-1">
        <Stat label="Request id — matches the server log line" value={requestId} mono />
      </div>
    </div>
  );
}
