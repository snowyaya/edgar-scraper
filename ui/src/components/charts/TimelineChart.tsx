import { useQuery } from '@tanstack/react-query'
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts'
import { analyticsApi } from '../../api/client'
import { format, parseISO } from 'date-fns'

const CustomTooltip = ({ active, payload, label }: any) => {
  if (!active || !payload?.length) return null
  return (
    <div className="card px-3 py-2">
      <div className="font-mono text-[10px]" style={{ color: 'var(--text-dim)' }}>
        {label}
      </div>
      <div className="font-display italic text-lg" style={{ color: 'var(--gold)' }}>
        {payload[0].value}
      </div>
      <div className="font-mono text-[10px]" style={{ color: 'var(--text-dim)' }}>documents saved</div>
    </div>
  )
}

export default function TimelineChart() {
  const { data = [] } = useQuery({
    queryKey: ['timeline'],
    queryFn: () => analyticsApi.timeline(30),
  })

  const formatted = data.map(d => ({
    ...d,
    label: format(parseISO(d.date), 'MMM d'),
  }))

  return (
    <ResponsiveContainer width="100%" height={200}>
      <AreaChart data={formatted} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
        <defs>
          <linearGradient id="goldGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%"  stopColor="#e8c87a" stopOpacity={0.25} />
            <stop offset="95%" stopColor="#e8c87a" stopOpacity={0} />
          </linearGradient>
        </defs>
        <XAxis
          dataKey="label"
          tick={{ fill: 'var(--text-dim)', fontSize: 10, fontFamily: 'JetBrains Mono' }}
          axisLine={{ stroke: 'var(--border)' }}
          tickLine={false}
          interval="preserveStartEnd"
        />
        <YAxis
          tick={{ fill: 'var(--text-dim)', fontSize: 10, fontFamily: 'JetBrains Mono' }}
          axisLine={false}
          tickLine={false}
          allowDecimals={false}
        />
        <Tooltip content={<CustomTooltip />} cursor={{ stroke: 'var(--border)' }} />
        <Area
          type="monotone"
          dataKey="documents_saved"
          stroke="#e8c87a"
          strokeWidth={1.5}
          fill="url(#goldGrad)"
          dot={false}
          activeDot={{ r: 3, fill: '#e8c87a' }}
        />
      </AreaChart>
    </ResponsiveContainer>
  )
}