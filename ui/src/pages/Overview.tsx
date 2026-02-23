import { useQuery } from '@tanstack/react-query'
import { analyticsApi } from '../api/client'
import StatCard from '../components/StatCard'
import PageHeader from '../components/PageHeader'
import QualityHistogram from '../components/charts/QualityHistogram'
import FilingTypeChart from '../components/charts/FilingTypeChart'
import TimelineChart from '../components/charts/TimelineChart'
import { StatusBadge } from '../components/FilingBadge'
import { runsApi } from '../api/client'
import { formatDistanceToNow, parseISO } from 'date-fns'
import { Link } from 'react-router-dom'

export default function Overview() {
  const { data: stats } = useQuery({
    queryKey: ['overview'],
    queryFn: analyticsApi.overview,
  })

  const { data: runs = [] } = useQuery({
    queryKey: ['runs-recent'],
    queryFn: () => runsApi.list({ limit: 4 }),
  })

  const { data: topCompanies = [] } = useQuery({
    queryKey: ['top-companies'],
    queryFn: () => analyticsApi.topCompanies(5),
  })

  return (
    <div className="animate-fade-in">
      <PageHeader
        title="Overview"
        subtitle="SEC EDGAR AI corpus — pipeline status and corpus health"
      />

      <div className="p-8 space-y-8">
        {/* ── Stat cards ─────────────────────────────────────────── */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 stagger">
          <StatCard
            label="Total Documents"
            value={stats?.total_documents ?? 0}
            sub="filings in corpus"
            delay={0}
          />
          <StatCard
            label="Companies"
            value={stats?.total_companies ?? 0}
            sub="SEC registrants"
            accent="var(--blue)"
            delay={60}
          />
          <StatCard
            label="Avg Quality"
            value={stats?.avg_quality_score != null
              ? Number(stats.avg_quality_score.toFixed(2))
              : 0}
            sub="composite score"
            accent="#4ade80"
            delay={120}
          />
          <StatCard
            label="Total Words"
            value={stats?.total_words ?? 0}
            sub="across all filings"
            accent="#c084fc"
            delay={180}
          />
        </div>

        {/* ── Charts row ─────────────────────────────────────────── */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          {/* Timeline — spans 2 cols */}
          <div className="card p-5 lg:col-span-2">
            <div className="font-mono text-[10px] tracking-[0.12em] uppercase mb-4" style={{ color: 'var(--text-dim)' }}>
              Documents Crawled — Last 30 Days
            </div>
            <TimelineChart />
          </div>

          {/* Filing types */}
          <div className="card p-5">
            <div className="font-mono text-[10px] tracking-[0.12em] uppercase mb-4" style={{ color: 'var(--text-dim)' }}>
              Filing Type Distribution
            </div>
            <FilingTypeChart />
          </div>
        </div>

        {/* ── Bottom row ─────────────────────────────────────────── */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {/* Quality histogram */}
          <div className="card p-5">
            <div className="font-mono text-[10px] tracking-[0.12em] uppercase mb-4" style={{ color: 'var(--text-dim)' }}>
              Quality Score Distribution
            </div>
            <QualityHistogram />
          </div>

          {/* Top companies */}
          <div className="card p-5">
            <div className="font-mono text-[10px] tracking-[0.12em] uppercase mb-4" style={{ color: 'var(--text-dim)' }}>
              Top Companies by Document Count
            </div>
            <div className="space-y-2">
              {topCompanies.map((co, i) => (
                <div
                  key={co.cik}
                  className="flex items-center justify-between py-2 border-b"
                  style={{ borderColor: 'var(--border-dim)' }}
                >
                  <div className="flex items-center gap-3">
                    <span className="font-mono text-xs w-5 text-right" style={{ color: 'var(--text-dim)' }}>
                      {i + 1}
                    </span>
                    <div>
                      <div className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
                        {co.name}
                      </div>
                      <div className="font-mono text-[10px]" style={{ color: 'var(--text-dim)' }}>
                        {co.tickers?.join(', ')} · {co.filing_types.join(', ')}
                      </div>
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="font-mono text-sm" style={{ color: 'var(--gold)' }}>
                      {co.document_count}
                    </div>
                    <div className="font-mono text-[10px]" style={{ color: 'var(--text-dim)' }}>docs</div>
                  </div>
                </div>
              ))}
              {topCompanies.length === 0 && (
                <div className="text-center py-8 font-mono text-xs" style={{ color: 'var(--text-dim)' }}>
                  No data yet — run the scraper first
                </div>
              )}
            </div>
          </div>
        </div>

        {/* ── Recent runs ────────────────────────────────────────── */}
        <div className="card">
          <div
            className="flex items-center justify-between px-5 py-3 border-b"
            style={{ borderColor: 'var(--border)' }}
          >
            <div className="font-mono text-[10px] tracking-[0.12em] uppercase" style={{ color: 'var(--text-dim)' }}>
              Recent Crawl Runs
            </div>
            <Link to="/runs" className="font-mono text-[10px]" style={{ color: 'var(--gold)' }}>
              View all →
            </Link>
          </div>
          <table className="data-table">
            <thead>
              <tr>
                <th>Status</th>
                <th>Started</th>
                <th>Filing Types</th>
                <th style={{ textAlign: 'right' }}>Saved</th>
                <th style={{ textAlign: 'right' }}>Errors</th>
              </tr>
            </thead>
            <tbody>
              {runs.map(run => (
                <tr key={run.run_id} onClick={() => window.location.href = `/runs/${run.run_id}`}>
                  <td><StatusBadge status={run.status} /></td>
                  <td>
                    <span className="font-mono text-xs" style={{ color: 'var(--text-secondary)' }}>
                      {formatDistanceToNow(parseISO(run.started_at), { addSuffix: true })}
                    </span>
                  </td>
                  <td>
                    <span className="font-mono text-xs" style={{ color: 'var(--text-dim)' }}>
                      {run.filing_types?.join(', ') ?? '—'}
                    </span>
                  </td>
                  <td style={{ textAlign: 'right' }}>
                    <span className="font-mono text-xs" style={{ color: '#4ade80' }}>
                      {run.pages_saved}
                    </span>
                  </td>
                  <td style={{ textAlign: 'right' }}>
                    <span className="font-mono text-xs" style={{ color: run.pages_errored > 0 ? '#f87171' : 'var(--text-dim)' }}>
                      {run.pages_errored}
                    </span>
                  </td>
                </tr>
              ))}
              {runs.length === 0 && (
                <tr>
                  <td colSpan={5} style={{ textAlign: 'center', color: 'var(--text-dim)', fontFamily: 'JetBrains Mono' }}>
                    No runs yet
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