import { useQuery } from '@tanstack/react-query'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts'
import { analyticsApi } from '../../api/client'

const COLORS: Record<string, string> = {
  '10-K':    '#60a5fa',
  '10-Q':    '#4ade80',
  '8-K':     '#fb923c',
  'DEF 14A': '#c084fc',
}

const CustomTooltip = ({ active, payload }: any) => {
  if (!active || !payload?.length) return null
  const d = payload[0].payload
  return (
    <div className="card px-3 py-2">
      <div className="font-mono text-xs font-bold" style={{ color: 'var(--gold)' }}>{d.filing_type}</div>
      <div className="font-mono text-xs mt-1" style={{ color: 'var(--text-secondary)' }}>
        {d.document_count.toLocaleString()} docs
      </div>
      {d.avg_quality_score && (
        <div className="font-mono text-xs" style={{ color: 'var(--text-dim)' }}>
          avg quality {d.avg_quality_score.toFixed(2)}
        </div>
      )}
    </div>
  )
}

export default function FilingTypeChart() {
  const { data = [] } = useQuery({
    queryKey: ['filing-types'],
    queryFn: () => analyticsApi.filingTypes(),
  })

  const colored = data.map(d => ({ ...d, fill: COLORS[d.filing_type] ?? '#94a3b8' }))

  return (
    <ResponsiveContainer width="100%" height={200}>
      <BarChart data={colored} layout="vertical" margin={{ top: 4, right: 24, left: 20, bottom: 0 }}>
        <XAxis
          type="number"
          tick={{ fill: 'var(--text-dim)', fontSize: 10, fontFamily: 'JetBrains Mono' }}
          axisLine={{ stroke: 'var(--border)' }}
          tickLine={false}
        />
        <YAxis
          type="category"
          dataKey="filing_type"
          tick={{ fill: 'var(--text-secondary)', fontSize: 11, fontFamily: 'JetBrains Mono' }}
          axisLine={false}
          tickLine={false}
          width={60}
        />
        <Tooltip content={<CustomTooltip />} cursor={{ fill: 'rgba(255,255,255,0.03)' }} />
        <Bar dataKey="document_count" radius={[0, 3, 3, 0]} fill="#60a5fa">
          {colored.map((entry, i) => (
            <rect key={i} fill={entry.fill} fillOpacity={0.85} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}