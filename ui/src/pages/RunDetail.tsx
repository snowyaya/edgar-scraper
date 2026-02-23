import { useParams, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { runsApi } from '../api/client'
import { StatusBadge } from '../components/FilingBadge'
import { format, parseISO } from 'date-fns'

function MetaItem({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="font-mono text-[9px] tracking-[0.12em] uppercase" style={{ color: 'var(--text-dim)' }}>
        {label}
      </span>
      <span className="font-mono text-sm" style={{ color: 'var(--text-secondary)' }}>{children}</span>
    </div>
  )
}

export default function RunDetail() {
  const { runId } = useParams<{ runId: string }>()
  const navigate = useNavigate()

  const { data: run, isLoading } = useQuery({
    queryKey: ['run', runId],
    queryFn: () => runsApi.get(runId!),
    enabled: !!runId,
    refetchInterval: (query) =>
      query.state.data?.status === 'running' ? 3000 : false,
  })

  const { data: errors } = useQuery({
    queryKey: ['run-errors', runId],
    queryFn: () => runsApi.getErrors(runId!, { limit: 100 }),
    enabled: !!runId,
  })

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <span className="font-mono text-xs animate-pulse" style={{ color: 'var(--text-dim)' }}>
          Loading run...
        </span>
      </div>
    )
  }

  if (!run) {
    return <div className="p-8 font-mono text-sm" style={{ color: '#f87171' }}>Run not found.</div>
  }

  const duration = run.finished_at
    ? Math.round((new Date(run.finished_at).getTime() - new Date(run.started_at).getTime()) / 1000)
    : null

  return (
    <div className="animate-fade-in">
      {/* ── Header ────────────────────────────────────────────────── */}
      <div className="px-8 py-5 border-b" style={{ borderColor: 'var(--border)' }}>
        <button
          onClick={() => navigate('/runs')}
          className="font-mono text-[10px] mb-2 flex items-center gap-1"
          style={{ color: 'var(--text-dim)' }}
        >
          ← Runs
        </button>
        <div className="flex items-center gap-3">
          <h1 className="font-display italic text-xl" style={{ color: 'var(--text-primary)' }}>
            Run Detail
          </h1>
          <StatusBadge status={run.status} />
        </div>
        <div className="font-mono text-[10px] mt-1" style={{ color: 'var(--text-dim)' }}>
          {run.run_id}
        </div>
      </div>

      <div className="p-8 space-y-6">
        {/* ── Summary cards ─────────────────────────────────────── */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {[
            { label: 'Pages Crawled', value: run.pages_crawled, color: 'var(--text-secondary)' },
            { label: 'Pages Saved',   value: run.pages_saved,   color: '#4ade80' },
            { label: 'Pages Skipped', value: run.pages_skipped, color: 'var(--gold)' },
            { label: 'Errors',        value: run.pages_errored, color: run.pages_errored > 0 ? '#f87171' : 'var(--text-dim)' },
          ].map(({ label, value, color }) => (
            <div key={label} className="card p-4">
              <div className="font-mono text-[9px] tracking-[0.12em] uppercase mb-2" style={{ color: 'var(--text-dim)' }}>
                {label}
              </div>
              <div className="font-display italic text-3xl" style={{ color }}>
                {value}
              </div>
            </div>
          ))}
        </div>

        {/* ── Config grid ───────────────────────────────────────── */}
        <div className="card p-5">
          <div className="font-mono text-[9px] tracking-[0.12em] uppercase mb-4" style={{ color: 'var(--text-dim)' }}>
            Configuration
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
            <MetaItem label="Started">
              {format(parseISO(run.started_at), 'MMM d, yyyy HH:mm:ss')}
            </MetaItem>
            <MetaItem label="Finished">
              {run.finished_at ? format(parseISO(run.finished_at), 'MMM d, yyyy HH:mm:ss') : '—'}
            </MetaItem>
            <MetaItem label="Duration">
              {duration != null ? `${duration}s` : run.status === 'running' ? 'In progress…' : '—'}
            </MetaItem>
            <MetaItem label="Max Filings / Co.">
              {run.max_filings ?? '—'}
            </MetaItem>
            <MetaItem label="Filing Types">
              {run.filing_types?.join(', ') ?? '—'}
            </MetaItem>
            <MetaItem label="Companies (CIKs)">
              {run.start_ciks?.join(', ') ?? '—'}
            </MetaItem>
            <MetaItem label="Trigger">
              {(run.config as any)?.triggered_via ?? 'cli'}
            </MetaItem>
            <MetaItem label="Date Range">
              {(run.config as any)?.date_from
                ? `${(run.config as any).date_from} → ${(run.config as any).date_to ?? 'now'}`
                : 'All dates'}
            </MetaItem>
          </div>
          {run.error_summary && (
            <div className="mt-4 px-3 py-2 rounded font-mono text-xs"
              style={{ background: '#2a0f0f', color: '#f87171', border: '1px solid #3d1414' }}>
              {run.error_summary}
            </div>
          )}
        </div>

        {/* ── Error log ─────────────────────────────────────────── */}
        {errors && errors.total > 0 && (
          <div className="card overflow-hidden">
            <div className="px-5 py-3 border-b" style={{ borderColor: 'var(--border)' }}>
              <span className="font-mono text-[9px] tracking-[0.12em] uppercase" style={{ color: 'var(--text-dim)' }}>
                Error Log ({errors.total})
              </span>
            </div>
            <table className="data-table">
              <thead>
                <tr>
                  <th>Type</th>
                  <th>URL</th>
                  <th>HTTP</th>
                  <th>Message</th>
                  <th>Time</th>
                </tr>
              </thead>
              <tbody>
                {errors.items.map(err => (
                  <tr key={err.id} style={{ cursor: 'default' }}>
                    <td>
                      <span className="badge" style={{ background: '#2a0f0f', color: '#f87171', border: '1px solid #3d1414' }}>
                        {err.error_type ?? 'unknown'}
                      </span>
                    </td>
                    <td>
                      <span
                        className="font-mono text-[10px]"
                        style={{ color: 'var(--text-dim)', maxWidth: 280, display: 'block', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
                        title={err.url}
                      >
                        {err.url}
                      </span>
                    </td>
                    <td>
                      <span className="font-mono text-xs" style={{ color: err.http_status ? '#fb923c' : 'var(--text-dim)' }}>
                        {err.http_status ?? '—'}
                      </span>
                    </td>
                    <td>
                      <span
                        className="text-xs"
                        style={{ color: 'var(--text-dim)', maxWidth: 260, display: 'block', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
                        title={err.message ?? ''}
                      >
                        {err.message ?? '—'}
                      </span>
                    </td>
                    <td>
                      <span className="font-mono text-[10px]" style={{ color: 'var(--text-dim)' }}>
                        {format(parseISO(err.occurred_at), 'HH:mm:ss')}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {errors && errors.total === 0 && (
          <div className="font-mono text-xs text-center py-4" style={{ color: 'var(--text-dim)' }}>
            No errors recorded for this run ✓
          </div>
        )}
      </div>
    </div>
  )
}