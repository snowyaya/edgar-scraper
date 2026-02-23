import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { documentsApi, DocumentFilters } from '../api/client'
import PageHeader from '../components/PageHeader'
import { FilingBadge, QualityBadge } from '../components/FilingBadge'
import { format, parseISO } from 'date-fns'

const FILING_TYPES = ['10-K', '10-Q', '8-K', 'DEF 14A']
const SORT_OPTIONS = [
  { value: 'fetched_at', label: 'Date Fetched' },
  { value: 'quality_score', label: 'Quality Score' },
  { value: 'word_count', label: 'Word Count' },
  { value: 'filing_date', label: 'Filing Date' },
]
const PAGE_SIZE = 25

export default function Documents() {
  const navigate = useNavigate()
  const [filters, setFilters] = useState<DocumentFilters>({
    limit: PAGE_SIZE,
    offset: 0,
    sort: 'fetched_at',
    order: 'desc',
  })
  const [search, setSearch] = useState('')

  const { data, isLoading } = useQuery({
    queryKey: ['documents', filters],
    queryFn: () => documentsApi.list(filters),
    placeholderData: prev => prev,
  })

  const setFilter = (key: keyof DocumentFilters, value: any) =>
    setFilters(f => ({ ...f, [key]: value || undefined, offset: 0 }))

  const page = Math.floor((filters.offset ?? 0) / PAGE_SIZE)
  const totalPages = Math.ceil((data?.total ?? 0) / PAGE_SIZE)

  return (
    <div className="animate-fade-in h-full flex flex-col">
      <PageHeader
        title="Documents"
        subtitle={data ? `${data.total.toLocaleString()} filings in corpus` : 'Loading...'}
      />

      {/* ── Filters ──────────────────────────────────────────────── */}
      <div
        className="flex flex-wrap items-center gap-3 px-8 py-4 border-b"
        style={{ borderColor: 'var(--border)', background: 'var(--bg-card)' }}
      >
        {/* Search */}
        <input
          className="input flex-1 min-w-48"
          placeholder="Search filings..."
          value={search}
          onChange={e => setSearch(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && setFilter('search', search)}
        />

        {/* Filing type */}
        <select
          className="input"
          value={filters.filing_type ?? ''}
          onChange={e => setFilter('filing_type', e.target.value)}
        >
          <option value="">All types</option>
          {FILING_TYPES.map(t => <option key={t}>{t}</option>)}
        </select>

        {/* Quality min */}
        <select
          className="input"
          value={filters.quality_min ?? ''}
          onChange={e => setFilter('quality_min', e.target.value ? Number(e.target.value) : undefined)}
        >
          <option value="">Any quality</option>
          <option value="0.8">≥ 0.80</option>
          <option value="0.7">≥ 0.70</option>
          <option value="0.5">≥ 0.50</option>
        </select>

        {/* Sort */}
        <select
          className="input"
          value={filters.sort}
          onChange={e => setFilter('sort', e.target.value)}
        >
          {SORT_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>

        <button
          className="btn btn-ghost"
          onClick={() => setFilters({ limit: PAGE_SIZE, offset: 0, sort: 'fetched_at', order: 'desc' })}
        >
          Reset
        </button>
      </div>

      {/* ── Table ────────────────────────────────────────────────── */}
      <div className="flex-1 overflow-auto">
        <table className="data-table">
          <thead style={{ position: 'sticky', top: 0, background: 'var(--bg-base)', zIndex: 1 }}>
            <tr>
              <th>Company</th>
              <th>Type</th>
              <th>Period</th>
              <th>Title</th>
              <th style={{ textAlign: 'right' }}>Words</th>
              <th style={{ textAlign: 'right' }}>Quality</th>
              <th>Fetched</th>
            </tr>
          </thead>
          <tbody>
            {isLoading && (
              <tr>
                <td colSpan={7} style={{ textAlign: 'center', padding: 40 }}>
                  <span className="font-mono text-xs" style={{ color: 'var(--text-dim)' }}>
                    Loading...
                  </span>
                </td>
              </tr>
            )}
            {!isLoading && data?.items.map(doc => (
              <tr key={doc.id} onClick={() => navigate(`/documents/${doc.id}`)}>
                <td>
                  <div className="font-medium text-sm" style={{ color: 'var(--text-primary)' }}>
                    {doc.company?.name ?? '—'}
                  </div>
                  <div className="font-mono text-[10px]" style={{ color: 'var(--text-dim)' }}>
                    {doc.company?.tickers?.join(', ')}
                  </div>
                </td>
                <td><FilingBadge type={doc.filing_type} /></td>
                <td>
                  <span className="font-mono text-xs" style={{ color: 'var(--text-secondary)' }}>
                    {doc.period_of_report
                      ? format(parseISO(doc.period_of_report), 'MMM yyyy')
                      : '—'}
                  </span>
                </td>
                <td>
                  <span
                    className="text-sm"
                    style={{ color: 'var(--text-secondary)', display: 'block', maxWidth: 300, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
                  >
                    {doc.title ?? '—'}
                  </span>
                </td>
                <td style={{ textAlign: 'right' }}>
                  <span className="font-mono text-xs" style={{ color: 'var(--text-secondary)' }}>
                    {doc.word_count?.toLocaleString() ?? '—'}
                  </span>
                </td>
                <td style={{ textAlign: 'right' }}>
                  <QualityBadge score={doc.quality_score} />
                </td>
                <td>
                  <span className="font-mono text-xs" style={{ color: 'var(--text-dim)' }}>
                    {format(parseISO(doc.fetched_at), 'MMM d, yyyy')}
                  </span>
                </td>
              </tr>
            ))}
            {!isLoading && data?.items.length === 0 && (
              <tr>
                <td colSpan={7} style={{ textAlign: 'center', padding: 60 }}>
                  <div className="font-mono text-xs" style={{ color: 'var(--text-dim)' }}>
                    No documents match your filters
                  </div>
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {/* ── Pagination ───────────────────────────────────────────── */}
      {totalPages > 1 && (
        <div
          className="flex items-center justify-between px-8 py-3 border-t"
          style={{ borderColor: 'var(--border)' }}
        >
          <span className="font-mono text-xs" style={{ color: 'var(--text-dim)' }}>
            Page {page + 1} of {totalPages} · {data?.total.toLocaleString()} total
          </span>
          <div className="flex gap-2">
            <button
              className="btn btn-ghost text-xs"
              disabled={page === 0}
              onClick={() => setFilters(f => ({ ...f, offset: Math.max(0, (f.offset ?? 0) - PAGE_SIZE) }))}
            >
              ← Prev
            </button>
            <button
              className="btn btn-ghost text-xs"
              disabled={page >= totalPages - 1}
              onClick={() => setFilters(f => ({ ...f, offset: (f.offset ?? 0) + PAGE_SIZE }))}
            >
              Next →
            </button>
          </div>
        </div>
      )}
    </div>
  )
}