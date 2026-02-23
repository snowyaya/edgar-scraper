interface PageHeaderProps {
  title: string
  subtitle?: string
  action?: React.ReactNode
}

export default function PageHeader({ title, subtitle, action }: PageHeaderProps) {
  return (
    <div
      className="flex items-start justify-between px-8 py-6 border-b"
      style={{ borderColor: 'var(--border)' }}
    >
      <div>
        <h1 className="font-display italic text-2xl leading-tight" style={{ color: 'var(--text-primary)' }}>
          {title}
        </h1>
        {subtitle && (
          <p className="font-mono text-xs mt-1" style={{ color: 'var(--text-dim)' }}>
            {subtitle}
          </p>
        )}
      </div>
      {action && <div className="ml-4 flex-shrink-0">{action}</div>}
    </div>
  )
}