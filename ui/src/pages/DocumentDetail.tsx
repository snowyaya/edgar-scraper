import { useParams, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { documentsApi } from '../api/client'
import { FilingBadge, QualityBadge } from '../components/FilingBadge'
import { format, parseISO } from 'date-fns'
import { useState } from 'react'

function MetaRow({ label, value }: { label: string; value?: React.ReactNode }) {
  if (!value && value !== 0) return null
  return (
    <div className="flex items-start gap-3 py-2 border-b" style={{ borderColor: 'var(--border-dim)' }}>
      <span className="font-mono text-[10px] tracking-[0.1em] uppercase w-36 flex-shrink-0 pt-0.5"
        style={{ color: 'var(--text-dim)' }}>
        {label}
      </span>
      <span className="text-sm" style={{ color: 'var(--text-secondary)' }}>{value}</span>
    </div>
  )
}

const SEC_ITEM_LABELS: Record<string, string> = {
  item_1: 'Business', item_1a: 'Risk Factors', item_1b: 'Unresolved Staff Comments',
  item_2: 'Properties', item_3: 'Legal Proceedings', item_7: 'MD&A',
  item_7a: 'Quantitative Disclosures', item_8: 'Financial Statements',
  item_9a: 'Controls & Procedures', item_15: 'Exhibits',
}

export default function DocumentDetail() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [activeSection, setActiveSection] = useState<number | null>(null)
  const [copied, setCopied] = useState(false)

  const { data: doc, isLoading } = useQuery({
    queryKey: ['document', id],
    queryFn: () => documentsApi.get(id!),
    enabled: !!id,
  })

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <span className="font-mono text-xs animate-pulse" style={{ color: 'var(--text-dim)' }}>
          Loading filing...
        </span>
      </div>
    )
  }

  if (!doc) {
    return (
      <div className="p-8">
        <div className="font-mono text-sm" style={{ color: '#f87171' }}>Document not found.</div>
      </div>
    )
  }

  const handleCopy = () => {
    const payload = {
      id: doc.id, url: doc.url, title: doc.title,
      filing_type: doc.filing_type, company: doc.company,
      word_count: doc.word_count, quality_score: doc.quality_score,
      body_text: doc.body_text,
    }
    navigator.clipboard.writeText(JSON.stringify(payload, null, 2))
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const activeSec = activeSection !== null ? doc.sections[activeSection] : null

  return (
    <div className="animate-fade-in flex flex-col h-full">
      {/* ── Header ──────────────────────────────────────────────── */}
      <div className="px-8 py-5 border-b" style={{ borderColor: 'var(--border)' }}>
        <div className="flex items-start justify-between gap-4">
          <div className="flex-1 min-w-0">
            <button
              onClick={() => navigate('/documents')}
              className="font-mono text-[10px] mb-2 flex items-center gap-1"
              style={{ color: 'var(--text-dim)' }}
            >
              ← Documents
            </button>
            <h1 className="font-display italic text-xl leading-snug" style={{ color: 'var(--text-primary)' }}>
              {doc.title ?? 'Untitled Filing'}
            </h1>
            <div className="flex items-center gap-3 mt-2 flex-wrap">
              <FilingBadge type={doc.filing_type} />
              <QualityBadge score={doc.quality_score} />
              <span className="font-mono text-xs" style={{ color: 'var(--text-dim)' }}>
                {doc.company?.name}
                {doc.company?.tickers?.length ? ` · ${doc.company.tickers.join(', ')}` : ''}
              </span>
              {doc.period_of_report && (
                <span className="font-mono text-xs" style={{ color: 'var(--text-dim)' }}>
                  Period: {format(parseISO(doc.period_of_report), 'MMM d, yyyy')}
                </span>
              )}
            </div>
          </div>
          <div className="flex gap-2 flex-shrink-0">
            <button className="btn btn-ghost text-xs" onClick={handleCopy}>
              {copied ? '✓ Copied' : 'Copy JSON'}
            </button>
            <a
              href={doc.url}
              target="_blank"
              rel="noopener noreferrer"
              className="btn btn-primary text-xs"
            >
              View on SEC ↗
            </a>
          </div>
        </div>
      </div>

      {/* ── Body: 3-col layout ──────────────────────────────────── */}
      <div className="flex-1 overflow-hidden flex">

        {/* Col 1: Metadata ─────────────────────────────────────── */}
        <div
          className="w-64 flex-shrink-0 overflow-y-auto border-r p-5"
          style={{ borderColor: 'var(--border)' }}
        >
          <div className="font-mono text-[9px] tracking-[0.15em] uppercase mb-3"
            style={{ color: 'var(--text-dim)' }}>
            Filing Metadata
          </div>
          <MetaRow label="Accession #" value={
            <span className="font-mono text-xs">{doc.accession_number}</span>
          } />
          <MetaRow label="Filing Date" value={
            doc.filing_date ? format(parseISO(doc.filing_date), 'MMM d, yyyy') : undefined
          } />
          <MetaRow label="Fiscal Year" value={doc.fiscal_year} />
          <MetaRow label="Language" value={
            <span className="font-mono text-xs uppercase">{doc.language}</span>
          } />
          <MetaRow label="Word Count" value={
            <span className="font-mono text-xs">{doc.word_count?.toLocaleString()}</span>
          } />
          <MetaRow label="Reading Time" value={
            doc.reading_time_minutes
              ? `~${Math.round(doc.reading_time_minutes)} min`
              : undefined
          } />
          <MetaRow label="Tables" value={doc.table_count} />
          <MetaRow label="Fetched" value={
            format(parseISO(doc.fetched_at), 'MMM d, yyyy HH:mm')
          } />

          {/* Tags */}
          {doc.tags && doc.tags.length > 0 && (
            <div className="mt-4">
              <div className="font-mono text-[9px] tracking-[0.15em] uppercase mb-2"
                style={{ color: 'var(--text-dim)' }}>Tags</div>
              <div className="flex flex-wrap gap-1">
                {doc.tags.map(tag => (
                  <span
                    key={tag}
                    className="font-mono text-[10px] px-2 py-0.5 rounded"
                    style={{ background: 'var(--bg-base)', color: 'var(--text-dim)', border: '1px solid var(--border)' }}
                  >
                    {tag}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* SEC Sections TOC */}
          {doc.sections.length > 0 && (
            <div className="mt-5">
              <div className="font-mono text-[9px] tracking-[0.15em] uppercase mb-2"
                style={{ color: 'var(--text-dim)' }}>
                Sections ({doc.sections.length})
              </div>
              <div className="space-y-0.5">
                {doc.sections.slice(0, 20).map((s, i) => (
                  <button
                    key={s.id}
                    onClick={() => setActiveSection(activeSection === i ? null : i)}
                    className="w-full text-left px-2 py-1.5 rounded text-xs transition-colors"
                    style={{
                      background: activeSection === i ? 'var(--bg-hover)' : 'transparent',
                      color: activeSection === i ? 'var(--gold)' : 'var(--text-dim)',
                      borderLeft: activeSection === i ? '2px solid var(--gold)' : '2px solid transparent',
                    }}
                  >
                    <span style={{ paddingLeft: `${(s.level - 1) * 8}px`, display: 'block' }}>
                      {s.sec_item ? (
                        <span className="font-mono text-[10px]" style={{ color: 'var(--gold)', opacity: 0.7 }}>
                          [{SEC_ITEM_LABELS[s.sec_item] ?? s.sec_item}]{' '}
                        </span>
                      ) : null}
                      {s.heading.length > 36 ? s.heading.slice(0, 36) + '…' : s.heading}
                    </span>
                  </button>
                ))}
                {doc.sections.length > 20 && (
                  <div className="font-mono text-[10px] px-2 py-1" style={{ color: 'var(--text-dim)' }}>
                    +{doc.sections.length - 20} more sections
                  </div>
                )}
              </div>
            </div>
          )}
        </div>

        {/* Col 2: Body text / Section content ─────────────────── */}
        <div className="flex-1 overflow-y-auto p-8">
          {activeSec ? (
            <div className="animate-fade-in">
              <div className="flex items-center gap-3 mb-4">
                <button
                  onClick={() => setActiveSection(null)}
                  className="font-mono text-[10px]"
                  style={{ color: 'var(--text-dim)' }}
                >
                  ← Full text
                </button>
                {activeSec.sec_item && (
                  <span className="badge" style={{ background: '#1a1408', color: 'var(--gold)', border: '1px solid #3d3014' }}>
                    {SEC_ITEM_LABELS[activeSec.sec_item] ?? activeSec.sec_item}
                  </span>
                )}
                <span className="font-mono text-[10px]" style={{ color: 'var(--text-dim)' }}>
                  {activeSec.word_count?.toLocaleString()} words
                </span>
              </div>
              <h2 className="font-display italic text-lg mb-4" style={{ color: 'var(--text-primary)' }}>
                {activeSec.heading}
              </h2>
              <div
                className="text-sm leading-relaxed whitespace-pre-wrap"
                style={{ color: 'var(--text-secondary)', maxWidth: 720 }}
              >
                {activeSec.body_text || <em style={{ color: 'var(--text-dim)' }}>No body text for this section.</em>}
              </div>
            </div>
          ) : (
            <div
              className="text-sm leading-relaxed whitespace-pre-wrap"
              style={{ color: 'var(--text-secondary)', maxWidth: 720 }}
            >
              {doc.body_text}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}