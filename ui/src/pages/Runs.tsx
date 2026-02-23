import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { runsApi, RunCreate } from '../api/client'
import PageHeader from '../components/PageHeader'
import { StatusBadge } from '../components/FilingBadge'
import { parseISO, formatDistanceToNow } from 'date-fns'

const FILING_OPTIONS = ['10-K', '10-Q', '8-K', 'DEF 14A']

function TriggerModal({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient()
  const [tickers, setTickers] = useState('')
  const [types, setTypes] = useState<string[]>(['10-K'])
  const [maxFilings, setMaxFilings] = useState(10)
  const [error, setError] = useState('')

  const mutation = useMutation({
    mutationFn: (body: RunCreate) => runsApi.create(body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['runs-recent'] })
      qc.invalidateQueries({ queryKey: ['runs'] })
      onClose()
    },
    onError: (e: any) => setError(e?.response?.data?.detail ?? 'Failed to start run'),
  })

  const handleSubmit = () => {
    const ids = tickers.split(/[\s,]+/).map(t => t.trim()).filter(Boolean)
    if (!ids.length) { setError('Enter at least one ticker or CIK'); return }
    if (!types.length) { setError('Select at least one filing type'); return }
    const isCiks = ids.every(id => /^\d{7,10}$/.test(id))
    const body: RunCreate = isCiks
      ? { ciks: ids, filing_types: types, max_filings: maxFilings }
      : { tickers: ids.map(t => t.toUpperCase()), filing_types: types, max_filings: maxFilings }
    mutation.mutate(body)
  }

  const toggleType = (t: string) =>
    setTypes(prev => prev.includes(t) ? prev.filter(x => x !== t) : [...prev, t])

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center"
      style={{ background: 'rgba(0,0,0,0.7)' }}
      onClick={onClose}
    >
      <div
        className="card w-full max-w-md p-6 animate-slide-up"
        onClick={e => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-5">
          <div className="font-display italic text-lg" style={{ color: 'var(--text-primary)' }}>
            New Crawl Run
          </div>
          <button onClick={onClose} className="font-mono text-lg" style={{ color: 'var(--text-dim)' }}>✕</button>
        </div>

        <div className="space-y-4">
          <div>
            <label className="font-mono text-[10px] tracking-[0.1em] uppercase block mb-1.5"
              style={{ color: 'var(--text-dim)' }}>
              Tickers or CIKs (comma separated)
            </label>
            <input
              className="input w-full"
              placeholder="AAPL, AMZN, 0000320193"
              value={tickers}
              onChange={e => setTickers(e.target.value)}
            />
          </div>

          <div>
            <label className="font-mono text-[10px] tracking-[0.1em] uppercase block mb-2"
              style={{ color: 'var(--text-dim)' }}>
              Filing Types
            </label>
            <div className="flex gap-2 flex-wrap">
              {FILING_OPTIONS.map(t => (
                <button
                  key={t}
                  onClick={() => toggleType(t)}
                  className="badge cursor-pointer transition-all"
                  style={types.includes(t)
                    ? { background: '#0f2744', color: '#60a5fa', border: '1px solid #2a4a72' }
                    : { background: 'var(--bg-base)', color: 'var(--text-dim)', border: '1px solid var(--border)' }
                  }
                >
                  {t}
                </button>
              ))}
            </div>
          </div>

          <div>
            <label className="font-mono text-[10px] tracking-[0.1em] uppercase block mb-1.5"
              style={{ color: 'var(--text-dim)' }}>
              Max Filings per Company
            </label>
            <input
              type="number"
              className="input w-full"
              min={1}
              max={100}
              value={maxFilings}
              onChange={e => setMaxFilings(Number(e.target.value))}
            />
          </div>

          {error && (
            <div className="font-mono text-xs px-3 py-2 rounded"
              style={{ background: '#2a0f0f', color: '#f87171', border: '1px solid #3d1414' }}>
              {error}
            </div>
          )}
        </div>

        <div className="flex gap-2 mt-6 justify-end">
          <button className="btn btn-ghost" onClick={onClose}>Cancel</button>
          <button
            className="btn btn-gold"
            onClick={handleSubmit}
            disabled={mutation.isPending}
          >
            {mutation.isPending ? 'Starting…' : '⟳ Start Crawl'}
          </button>
        </div>
      </div>
    </div>
  )
}

export default function Runs() {
  const navigate = useNavigate()
  const [showModal, setShowModal] = useState(false)

  const { data: runs = [], isLoading } = useQuery({
    queryKey: ['runs'],
    queryFn: () => runsApi.list({ limit: 50 }),
    refetchInterval: 5000, // poll every 5s for running jobs
  })

  const runningCount = runs.filter(r => r.status === 'running').length

  return (
    <div className="animate-fade-in">
      {showModal && <TriggerModal onClose={() => setShowModal(false)} />}

      <PageHeader
        title="Crawl Runs"
        subtitle={runningCount > 0
          ? `${runningCount} run${runningCount > 1 ? 's' : ''} in progress — auto-refreshing`
          : `${runs.length} total runs`
        }
        action={
          <button className="btn btn-gold" onClick={() => setShowModal(true)}>
            ⟳ New Run
          </button>
        }
      />

      <div className="p-8">
        <div className="card overflow-hidden">
          <table className="data-table">
            <thead>
              <tr>
                <th>Status</th>
                <th>Run ID</th>
                <th>Filing Types</th>
                <th>Started</th>
                <th>Duration</th>
                <th style={{ textAlign: 'right' }}>Crawled</th>
                <th style={{ textAlign: 'right' }}>Saved</th>
                <th style={{ textAlign: 'right' }}>Errors</th>
              </tr>
            </thead>
            <tbody>
              {isLoading && (
                <tr>
                  <td colSpan={8} style={{ textAlign: 'center', padding: 40 }}>
                    <span className="font-mono text-xs" style={{ color: 'var(--text-dim)' }}>Loading...</span>
                  </td>
                </tr>
              )}
              {runs.map(run => {
                const duration = run.finished_at
                  ? Math.round((new Date(run.finished_at).getTime() - new Date(run.started_at).getTime()) / 1000)
                  : null

                return (
                  <tr key={run.run_id} onClick={() => navigate(`/runs/${run.run_id}`)}>
                    <td><StatusBadge status={run.status} /></td>
                    <td>
                      <span className="font-mono text-[10px]" style={{ color: 'var(--text-dim)' }}>
                        {run.run_id.slice(0, 8)}…
                      </span>
                    </td>
                    <td>
                      <span className="font-mono text-xs" style={{ color: 'var(--text-secondary)' }}>
                        {run.filing_types?.join(', ') ?? '—'}
                      </span>
                    </td>
                    <td>
                      <span className="font-mono text-xs" style={{ color: 'var(--text-secondary)' }}>
                        {formatDistanceToNow(parseISO(run.started_at), { addSuffix: true })}
                      </span>
                    </td>
                    <td>
                      <span className="font-mono text-xs" style={{ color: 'var(--text-dim)' }}>
                        {duration != null ? `${duration}s` : run.status === 'running' ? '…' : '—'}
                      </span>
                    </td>
                    <td style={{ textAlign: 'right' }}>
                      <span className="font-mono text-xs" style={{ color: 'var(--text-secondary)' }}>
                        {run.pages_crawled}
                      </span>
                    </td>
                    <td style={{ textAlign: 'right' }}>
                      <span className="font-mono text-xs" style={{ color: '#4ade80' }}>
                        {run.pages_saved}
                      </span>
                    </td>
                    <td style={{ textAlign: 'right' }}>
                      <span className="font-mono text-xs"
                        style={{ color: run.pages_errored > 0 ? '#f87171' : 'var(--text-dim)' }}>
                        {run.pages_errored}
                      </span>
                    </td>
                  </tr>
                )
              })}
              {!isLoading && runs.length === 0 && (
                <tr>
                  <td colSpan={8} style={{ textAlign: 'center', padding: 60 }}>
                    <div className="font-mono text-xs" style={{ color: 'var(--text-dim)' }}>
                      No runs yet — click "New Run" to start crawling
                    </div>
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}