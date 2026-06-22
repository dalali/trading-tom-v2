import React, { useEffect, useState } from "react";
import { fetchEngineStatus, fetchEngineRuns, fetchEngineRunDetail, triggerEngineRun } from "../../api/endpoints";
import { useFetch } from "../../utils/useFetch";
import LoadingSkeleton from "../../components/LoadingSkeleton";
import ErrorState from "../../components/ErrorState";
import Badge from "../../components/Badge";
import ConfirmDialog from "../../components/ConfirmDialog";
import { useToast } from "../../context/ToastContext";
import { formatDateTime, statusBadgeVariant } from "../../utils/format";

const POLL_INTERVAL_MS = 4000;

/** Admin engine status / run history — docs/design.md Section 4.10.
 * Polls while a run is in progress (Section 5.1's "watch a backend job
 * progress" pattern), ~3-5s interval per assumption 10. */
export default function EnginePage() {
  const { showToast } = useToast();
  const { data: status, error: statusError, refetch: refetchStatus } = useFetch(fetchEngineStatus, []);
  const { data: runsData, loading: runsLoading, error: runsError, refetch: refetchRuns } = useFetch(
    () => fetchEngineRuns({ page: 1, page_size: 20 }),
    []
  );
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [triggering, setTriggering] = useState(false);
  const [expandedRun, setExpandedRun] = useState(null);

  const isRunning = status?.state === "running";

  useEffect(() => {
    if (!isRunning) return;
    const interval = setInterval(() => {
      refetchStatus();
      refetchRuns();
    }, POLL_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [isRunning, refetchStatus, refetchRuns]);

  async function handleTrigger() {
    setTriggering(true);
    try {
      await triggerEngineRun();
      showToast("Engine run triggered.", "success");
      setConfirmOpen(false);
      refetchStatus();
      refetchRuns();
    } catch (err) {
      if (err.status === 409) {
        showToast("A run is already in progress.", "error");
      } else {
        showToast(err.message || "Couldn't trigger a run.", "error");
      }
    } finally {
      setTriggering(false);
    }
  }

  return (
    <div>
      <h1 className="text-h1 page-title">Engine Status</h1>

      {statusError && <ErrorState message={statusError} onRetry={refetchStatus} />}

      {status && (
        <div className="card" style={{ marginBottom: "var(--space-5)" }} aria-live="polite">
          <p>
            <Badge variant={statusBadgeVariant(status.state)}>{status.state === "running" ? "Running" : "Idle"}</Badge>{" "}
            {status.state === "running"
              ? "Evaluating accounts…"
              : status.last_run
              ? `last run completed ${formatDateTime(status.last_run.finished_at)}`
              : "No runs yet"}
          </p>
          {status.next_scheduled_run && (
            <p className="text-muted">Next scheduled run: {formatDateTime(status.next_scheduled_run)}</p>
          )}
          <button
            type="button"
            className="btn btn-primary"
            disabled={isRunning}
            onClick={() => setConfirmOpen(true)}
          >
            {isRunning ? "Run In Progress…" : "Trigger Run Now"}
          </button>
          {isRunning && (
            <p className="text-small text-muted">A run is already in progress. Please wait for it to complete before triggering another.</p>
          )}
        </div>
      )}

      <h2 className="text-h2">Run History</h2>
      {runsLoading && <LoadingSkeleton rows={5} />}
      {!runsLoading && runsError && <ErrorState message={runsError} onRetry={refetchRuns} />}

      {!runsLoading && !runsError && runsData && runsData.items.length === 0 && (
        <p className="text-muted">No engine runs yet.</p>
      )}

      {!runsLoading && !runsError && runsData && runsData.items.length > 0 && (
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>Run #</th>
                <th>Started</th>
                <th className="col-center">Status</th>
                <th className="col-num">Tickers</th>
                <th className="col-num">Signals</th>
                <th className="col-num">Trades</th>
                <th className="col-num">Errors</th>
                <th aria-label="Expand" />
              </tr>
            </thead>
            <tbody>
              {runsData.items.map((run) => (
                <React.Fragment key={run.id}>
                  <tr
                    className="clickable"
                    onClick={() => setExpandedRun(expandedRun === run.id ? null : run.id)}
                  >
                    <td>{run.id}</td>
                    <td>{formatDateTime(run.started_at)}</td>
                    <td className="col-center">
                      <Badge variant={statusBadgeVariant(run.status)}>
                        {run.status.charAt(0).toUpperCase() + run.status.slice(1)}
                      </Badge>
                    </td>
                    <td className="col-num">{run.tickers_evaluated}</td>
                    <td className="col-num">{run.signals_fired}</td>
                    <td className="col-num">{run.trades_executed}</td>
                    <td className="col-num">
                      {Array.isArray(run.errors) ? run.errors.length : "—"}
                    </td>
                    <td className="col-center">{expandedRun === run.id ? "▲" : "▼"}</td>
                  </tr>
                  {expandedRun === run.id && (
                    <tr>
                      <td colSpan={8}>
                        <RunDetail runId={run.id} />
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {confirmOpen && (
        <ConfirmDialog
          title="Trigger engine run now?"
          confirmLabel="Trigger Run"
          busy={triggering}
          onConfirm={handleTrigger}
          onClose={() => setConfirmOpen(false)}
        >
          <p>This runs the exact same logic as the scheduled daily run, evaluating all active accounts immediately.</p>
        </ConfirmDialog>
      )}
    </div>
  );
}

function RunDetail({ runId }) {
  const { data, loading, error } = useFetch(() => fetchEngineRunDetail(runId), [runId]);

  if (loading) return <LoadingSkeleton rows={2} />;
  if (error) return <ErrorState message={error} />;
  if (!data) return null;

  return (
    <div className="card">
      {data.errors && data.errors.length > 0 && (
        <div className="banner banner-warning">
          <span aria-hidden="true">!</span>
          <div>
            <strong>{data.errors.length} error(s) during this run</strong>
            <ul>
              {data.errors.map((e, idx) => (
                <li key={idx}>{typeof e === "string" ? e : JSON.stringify(e)}</li>
              ))}
            </ul>
          </div>
        </div>
      )}
      <p>
        Tickers evaluated: {data.tickers_evaluated} &nbsp; Signals fired: {data.signals_fired} &nbsp; Trades total:{" "}
        {data.trades_executed} &nbsp; Users affected: {data.users_affected}
      </p>
    </div>
  );
}
