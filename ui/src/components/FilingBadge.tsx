import clsx from 'clsx'

const FILING_CLASSES: Record<string, string> = {
  '10-K':    'badge-10k',
  '10-Q':    'badge-10q',
  '8-K':     'badge-8k',
  'DEF 14A': 'badge-proxy',
}

const STATUS_CLASSES: Record<string, string> = {
  running:   'badge-running',
  completed: 'badge-completed',
  partial:   'badge-partial',
  failed:    'badge-failed',
}

const STATUS_ICONS: Record<string, string> = {
  running:   '⟳',
  completed: '✓',
  partial:   '◑',
  failed:    '✕',
}

export function FilingBadge({ type }: { type?: string }) {
  if (!type) return null
  return (
    <span className={clsx('badge', FILING_CLASSES[type] ?? 'badge-other')}>
      {type}
    </span>
  )
}

export function StatusBadge({ status }: { status: string }) {
  return (
    <span className={clsx('badge gap-1', STATUS_CLASSES[status] ?? 'badge-other')}>
      <span>{STATUS_ICONS[status] ?? '?'}</span>
      {status}
    </span>
  )
}

export function QualityBadge({ score }: { score?: number }) {
  if (score == null) return <span style={{ color: 'var(--text-dim)' }}>—</span>

  const color = score >= 0.8 ? '#4ade80' : score >= 0.5 ? '#e8c87a' : '#f87171'
  const bg    = score >= 0.8 ? '#0f2a1e' : score >= 0.5 ? '#1a1408' : '#2a0f0f'

  return (
    <span
      className="badge"
      style={{ background: bg, color, border: `1px solid ${color}33` }}
    >
      {score.toFixed(2)}
    </span>
  )
}