/**
 * What answered, and which trace to look for.
 *
 * `request_id` is the same correlation id the backend puts on every structured
 * log line for that request. Showing it turns "the ranking looked wrong" into a
 * report someone can act on, because the exact log entry can be found from it.
 * Without it, a user report and a log file have nothing in common.
 */
export default function StatusFooter({
  modelVersion,
  requestId,
}: {
  modelVersion: string;
  requestId: string;
}) {
  return (
    <dl className="flex flex-wrap gap-x-6 gap-y-1 text-xs text-muted">
      <div className="flex gap-1.5">
        <dt>Model</dt>
        <dd className="tabular text-text">{modelVersion}</dd>
      </div>
      <div className="flex min-w-0 gap-1.5">
        <dt>Request</dt>
        <dd className="tabular truncate text-text" title={requestId}>
          {requestId}
        </dd>
      </div>
    </dl>
  );
}
