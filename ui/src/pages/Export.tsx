import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { analyticsApi } from '../api/client'
import PageHeader from '../components/PageHeader'

const FILING_TYPES = ['10-K', '10-Q', '8-K', 'DEF 14A']

interface ExportFilters {
  filing_type?: string
  language?: string
  quality_min?: string
  company_cik?: string
  fiscal_year?: string
  content_type?: string
}

function buildExportUrl(filters: ExportFilters): string {
  const params = new URLSearchParams()
  Object.entries(filters).forEach(([k, v]) => { if (v) params.set(k, v) })
  const qs = params.toString()
  return `/api/export${qs ? `?${qs}` : ''}`
}

export default function Export() {
  const [filters, setFilters] = useState<ExportFilters>({})
  const [downloading, setDownloading] = useState(false)

  const { data: overview } = useQuery({
    queryKey: ['overview'],
    queryFn: analyticsApi.overview,
  })

  const setFilter = (k: keyof ExportFilters, v: string) =>
    setFilters(f => ({ ...f, [k]: v || undefined }))

  const exportUrl = buildExportUrl(filters)

  const handleDownload = async () => {
    setDownloading(true)
    try {
      const a = document.createElement('a')
      a.href = exportUrl
      a.download = 'edgar_corpus.jsonl'
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
    } finally {
      setTimeout(() => setDownloading(false), 1500)
    }
  }

  const schemaFields = [
    { field: 'id',                  type: 'uuid',    desc: 'Unique document identifier' },
    { field: 'content_hash',        type: 'string',  desc: 'SHA-256 of body_text — dedup key' },
    { field: 'schema_version',      type: 'int',     desc: 'Schema version for migration tracking' },
    { field: 'url',                 type: 'string',  desc: 'Source URL on SEC EDGAR' },
    { field: 'accession_number',    type: 'string',  desc: 'SEC accession number (e.g. 0000320193-23-000077)' },
    { field: 'company.cik',         type: 'string',  desc: 'SEC Central Index Key, zero-padded to 10 digits' },
    { field: 'company.name',        type: 'string',  desc: 'Registrant legal name' },
    { field: 'company.tickers',     type: 'string[]', desc: 'Exchange ticker symbols' },
    { field: 'company.sic_code',    type: 'string',  desc: 'SEC Standard Industrial Classification code' },
    { field: 'filing_type',         type: 'string',  desc: '10-K | 10-Q | 8-K | DEF 14A' },
    { field: 'filing_date',         type: 'date',    desc: 'Date filing was submitted to SEC' },
    { field: 'period_of_report',    type: 'date',    desc: 'Fiscal period this filing covers' },
    { field: 'fiscal_year',         type: 'int',     desc: 'Calendar year of the reporting period' },
    { field: 'fetched_at',          type: 'datetime', desc: 'Timestamp when the document was scraped' },
    { field: 'title',               type: 'string',  desc: 'Document title (extracted or constructed)' },
    { field: 'body_text',           type: 'string',  desc: 'Clean, structured full text content' },
    { field: 'headings',            type: 'string[]', desc: 'Ordered list of all section headings' },
    { field: 'sections',            type: 'object[]', desc: 'Section-level content with SEC item tags' },
    { field: 'word_count',          type: 'int',     desc: 'Total word count — use for LLM context budgeting' },
    { field: 'char_count',          type: 'int',     desc: 'Total character count' },
    { field: 'reading_time_minutes', type: 'float',  desc: 'Estimated reading time at 238 wpm' },
    { field: 'language',            type: 'string',  desc: 'ISO 639-1 detected language code' },
    { field: 'content_type',        type: 'string',  desc: 'annual_report | quarterly_report | current_report | proxy_statement' },
    { field: 'quality_score',       type: 'float',   desc: 'Composite 0.0–1.0 signal for ranking and filtering' },
    { field: 'has_tables',          type: 'bool',    desc: 'True if document contains HTML tables' },
    { field: 'table_count',         type: 'int',     desc: 'Number of tables — proxy for financial statement density' },
    { field: 'tags',                type: 'string[]', desc: 'Derived tags: filing type, sector, detected SEC items' },
  ]

  return (
    <div className="animate-fade-in">
      <PageHeader
        title="Export Corpus"
        subtitle="Download the full collection as newline-delimited JSON"
      />

      <div className="p-8 space-y-6">
        {/* ── Stats banner ──────────────────────────────────────── */}
        <div
          className="rounded-lg px-6 py-4 flex items-center gap-8"
          style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}
        >
          <div>
            <div className="font-mono text-[10px] tracking-[0.1em] uppercase mb-1" style={{ color: 'var(--text-dim)' }}>
              Corpus Size
            </div>
            <div className="font-display italic text-2xl" style={{ color: 'var(--gold)' }}>
              {overview?.total_documents?.toLocaleString() ?? '—'}
            </div>
            <div className="font-mono text-[10px]" style={{ color: 'var(--text-dim)' }}>documents</div>
          </div>
          <div>
            <div className="font-mono text-[10px] tracking-[0.1em] uppercase mb-1" style={{ color: 'var(--text-dim)' }}>
              Total Words
            </div>
            <div className="font-display italic text-2xl" style={{ color: '#c084fc' }}>
              {overview?.total_words ? (overview.total_words / 1_000_000).toFixed(1) + 'M' : '—'}
            </div>
            <div className="font-mono text-[10px]" style={{ color: 'var(--text-dim)' }}>words</div>
          </div>
          <div>
            <div className="font-mono text-[10px] tracking-[0.1em] uppercase mb-1" style={{ color: 'var(--text-dim)' }}>
              Avg Quality
            </div>
            <div className="font-display italic text-2xl" style={{ color: '#4ade80' }}>
              {overview?.avg_quality_score?.toFixed(2) ?? '—'}
            </div>
            <div className="font-mono text-[10px]" style={{ color: 'var(--text-dim)' }}>score</div>
          </div>
          <div className="ml-auto">
            <div className="font-mono text-[10px]" style={{ color: 'var(--text-dim)' }}>Format</div>
            <div className="font-mono text-sm mt-0.5" style={{ color: 'var(--text-secondary)' }}>
              application/x-ndjson
            </div>
            <div className="font-mono text-[10px]" style={{ color: 'var(--text-dim)' }}>
              one JSON object per line
            </div>
          </div>
        </div>

        <div className="grid grid-cols-3 gap-6">
          {/* ── Filters ───────────────────────────────────────── */}
          <div className="col-span-1 card p-5 space-y-4">
            <div className="font-mono text-[10px] tracking-[0.12em] uppercase" style={{ color: 'var(--text-dim)' }}>
              Filter Export
            </div>

            <div>
              <label className="font-mono text-[10px] block mb-1.5" style={{ color: 'var(--text-dim)' }}>
                Filing Type
              </label>
              <select className="input w-full" value={filters.filing_type ?? ''}
                onChange={e => setFilter('filing_type', e.target.value)}>
                <option value="">All types</option>
                {FILING_TYPES.map(t => <option key={t}>{t}</option>)}
              </select>
            </div>

            <div>
              <label className="font-mono text-[10px] block mb-1.5" style={{ color: 'var(--text-dim)' }}>
                Min Quality Score
              </label>
              <select className="input w-full" value={filters.quality_min ?? ''}
                onChange={e => setFilter('quality_min', e.target.value)}>
                <option value="">Any quality</option>
                <option value="0.9">≥ 0.90 (high)</option>
                <option value="0.8">≥ 0.80</option>
                <option value="0.7">≥ 0.70</option>
                <option value="0.5">≥ 0.50</option>
              </select>
            </div>

            <div>
              <label className="font-mono text-[10px] block mb-1.5" style={{ color: 'var(--text-dim)' }}>
                Company CIK
              </label>
              <input className="input w-full" placeholder="e.g. 0000320193"
                value={filters.company_cik ?? ''}
                onChange={e => setFilter('company_cik', e.target.value)} />
            </div>

            <div>
              <label className="font-mono text-[10px] block mb-1.5" style={{ color: 'var(--text-dim)' }}>
                Fiscal Year
              </label>
              <input className="input w-full" placeholder="e.g. 2023" type="number"
                value={filters.fiscal_year ?? ''}
                onChange={e => setFilter('fiscal_year', e.target.value)} />
            </div>

            <div>
              <label className="font-mono text-[10px] block mb-1.5" style={{ color: 'var(--text-dim)' }}>
                Language
              </label>
              <input className="input w-full" placeholder="e.g. en"
                value={filters.language ?? ''}
                onChange={e => setFilter('language', e.target.value)} />
            </div>

            {/* URL preview */}
            <div className="pt-2">
              <div className="font-mono text-[9px] mb-1" style={{ color: 'var(--text-dim)' }}>Endpoint</div>
              <div
                className="font-mono text-[9px] break-all px-2 py-1.5 rounded"
                style={{ background: 'var(--bg-base)', color: 'var(--text-dim)', border: '1px solid var(--border)' }}
              >
                {exportUrl}
              </div>
            </div>

            <button
              className="btn btn-gold w-full justify-center"
              onClick={handleDownload}
              disabled={downloading}
            >
              {downloading ? '↓ Preparing…' : '↓ Download JSONL'}
            </button>
          </div>

          {/* ── Schema reference ──────────────────────────────── */}
          <div className="col-span-2 card overflow-hidden">
            <div className="px-5 py-3 border-b" style={{ borderColor: 'var(--border)' }}>
              <span className="font-mono text-[9px] tracking-[0.12em] uppercase" style={{ color: 'var(--text-dim)' }}>
                Document Schema — AI Document Object
              </span>
            </div>
            <div className="overflow-y-auto" style={{ maxHeight: 480 }}>
              <table className="data-table">
                <thead style={{ position: 'sticky', top: 0, background: 'var(--bg-card)', zIndex: 1 }}>
                  <tr>
                    <th>Field</th>
                    <th>Type</th>
                    <th>Description</th>
                  </tr>
                </thead>
                <tbody>
                  {schemaFields.map(({ field, type, desc }) => (
                    <tr key={field} style={{ cursor: 'default' }}>
                      <td>
                        <span className="font-mono text-xs" style={{ color: 'var(--gold)' }}>{field}</span>
                      </td>
                      <td>
                        <span className="font-mono text-[10px] px-2 py-0.5 rounded"
                          style={{ background: 'var(--bg-base)', color: '#c084fc', border: '1px solid var(--border)' }}>
                          {type}
                        </span>
                      </td>
                      <td>
                        <span className="text-xs" style={{ color: 'var(--text-dim)' }}>{desc}</span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}