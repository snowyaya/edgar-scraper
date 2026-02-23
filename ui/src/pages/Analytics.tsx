import { useQuery } from '@tanstack/react-query'
import { analyticsApi } from '../api/client'
import PageHeader from '../components/PageHeader'
import QualityHistogram from '../components/charts/QualityHistogram'
import FilingTypeChart from '../components/charts/FilingTypeChart'
import TimelineChart from '../components/charts/TimelineChart'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell,
  PieChart, Pie, Legend,
} from 'recharts'

const LANG_COLORS = ['#60a5fa', '#4ade80', '#fb923c', '#c084fc', '#f87171']

function ChartCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="card p-5">
      <div className="font-mono text-[10px] tracking-[0.12em] uppercase mb-4" style={{ color: 'var(--text-dim)' }}>
        {title}
      </div>
      {children}
    </div>
  )
}

const CustomTooltip = ({ active, payload, label }: any) => {
  if (!active || !payload?.length) return null
  return (
    <div className="card px-3 py-2">
      <div className="font-mono text-xs font-bold" style={{ color: 'var(--gold)' }}>{label}</div>
      <div className="font-mono text-xs mt-1" style={{ color: 'var(--text-secondary)' }}>
        {payload[0].value.toLocaleString()} {payload[0].name}
      </div>
    </div>
  )
}

export default function Analytics() {
  const { data: readingTime = [] } = useQuery({
    queryKey: ['reading-time'],
    queryFn: analyticsApi.readingTime,
  })

  const { data: topCompanies = [] } = useQuery({
    queryKey: ['top-companies-10'],
    queryFn: () => analyticsApi.topCompanies(10),
  })

  const { data: languages = [] } = useQuery({
    queryKey: ['languages'],
    queryFn: analyticsApi.languages,
  })

  return (
    <div className="animate-fade-in">
      <PageHeader
        title="Analytics"
        subtitle="Corpus composition, quality distribution, and crawl cadence"
      />

      <div className="p-8 space-y-4">
        {/* Row 1: Timeline + Filing types */}
        <div className="grid grid-cols-3 gap-4">
          <div className="col-span-2">
            <ChartCard title="Documents Crawled — Last 30 Days">
              <TimelineChart />
            </ChartCard>
          </div>
          <ChartCard title="Filing Type Distribution">
            <FilingTypeChart />
          </ChartCard>
        </div>

        {/* Row 2: Quality histogram + Language pie */}
        <div className="grid grid-cols-3 gap-4">
          <div className="col-span-2">
            <ChartCard title="Quality Score Distribution">
              <QualityHistogram />
            </ChartCard>
          </div>
          <ChartCard title="Language Distribution">
            {languages.length > 0 ? (
              <ResponsiveContainer width="100%" height={200}>
                <PieChart>
                  <Pie
                    data={languages}
                    dataKey="document_count"
                    nameKey="language"
                    cx="50%"
                    cy="50%"
                    outerRadius={70}
                    strokeWidth={0}
                  >
                    {languages.map((_, i) => (
                      <Cell key={i} fill={LANG_COLORS[i % LANG_COLORS.length]} fillOpacity={0.85} />
                    ))}
                  </Pie>
                  <Tooltip
                    contentStyle={{ background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 6 }}
                    itemStyle={{ color: 'var(--text-secondary)', fontFamily: 'JetBrains Mono', fontSize: 11 }}
                    labelStyle={{ color: 'var(--gold)', fontFamily: 'JetBrains Mono', fontSize: 11 }}
                    formatter={(v: any, n: any) => [`${v} docs (${languages.find(l => l.language === n)?.percentage ?? 0}%)`, n]}
                  />
                  <Legend
                    iconType="circle"
                    iconSize={8}
                    formatter={v => <span style={{ color: 'var(--text-secondary)', fontSize: 11, fontFamily: 'JetBrains Mono' }}>{v}</span>}
                  />
                </PieChart>
              </ResponsiveContainer>
            ) : (
              <div className="flex items-center justify-center h-48 font-mono text-xs" style={{ color: 'var(--text-dim)' }}>
                No data yet
              </div>
            )}
          </ChartCard>
        </div>

        {/* Row 3: Reading time + Top companies */}
        <div className="grid grid-cols-2 gap-4">
          <ChartCard title="Reading Time Distribution">
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={readingTime} margin={{ top: 4, right: 4, left: -20, bottom: 20 }}>
                <XAxis
                  dataKey="bucket_label"
                  tick={{ fill: 'var(--text-dim)', fontSize: 10, fontFamily: 'JetBrains Mono' }}
                  axisLine={{ stroke: 'var(--border)' }}
                  tickLine={false}
                  angle={-25}
                  textAnchor="end"
                  interval={0}
                />
                <YAxis
                  tick={{ fill: 'var(--text-dim)', fontSize: 10, fontFamily: 'JetBrains Mono' }}
                  axisLine={false}
                  tickLine={false}
                />
                <Tooltip content={<CustomTooltip />} cursor={{ fill: 'rgba(255,255,255,0.03)' }} />
                <Bar dataKey="count" fill="#c084fc" fillOpacity={0.85} radius={[3, 3, 0, 0]} name="documents" />
              </BarChart>
            </ResponsiveContainer>
          </ChartCard>

          <ChartCard title="Top Companies by Document Count">
            <div className="space-y-1.5 max-h-56 overflow-y-auto pr-1">
              {topCompanies.map((co, i) => (
                <div key={co.cik} className="flex items-center gap-3">
                  <span className="font-mono text-[10px] w-5 text-right flex-shrink-0" style={{ color: 'var(--text-dim)' }}>
                    {i + 1}
                  </span>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-xs font-medium truncate" style={{ color: 'var(--text-primary)' }}>
                        {co.name}
                      </span>
                      <span className="font-mono text-xs flex-shrink-0" style={{ color: 'var(--gold)' }}>
                        {co.document_count}
                      </span>
                    </div>
                    {/* Bar */}
                    <div className="h-1 rounded mt-1" style={{ background: 'var(--border)' }}>
                      <div
                        className="h-1 rounded"
                        style={{
                          width: `${(co.document_count / (topCompanies[0]?.document_count || 1)) * 100}%`,
                          background: 'var(--gold)',
                          opacity: 0.6,
                        }}
                      />
                    </div>
                  </div>
                </div>
              ))}
              {topCompanies.length === 0 && (
                <div className="text-center py-8 font-mono text-xs" style={{ color: 'var(--text-dim)' }}>
                  No data yet
                </div>
              )}
            </div>
          </ChartCard>
        </div>
      </div>
    </div>
  )
}