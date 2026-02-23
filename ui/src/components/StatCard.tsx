import { useEffect, useRef, useState } from 'react'

interface StatCardProps {
  label: string
  value: number | string
  sub?: string
  accent?: string
  animate?: boolean
  delay?: number
}

function useCountUp(target: number, duration = 1000, delay = 0) {
  const [current, setCurrent] = useState(0)
  const rafRef = useRef<number>()

  useEffect(() => {
    const timer = setTimeout(() => {
      const start = performance.now()
      const tick = (now: number) => {
        const elapsed = now - start
        const progress = Math.min(elapsed / duration, 1)
        // Ease out cubic
        const eased = 1 - Math.pow(1 - progress, 3)
        setCurrent(Math.round(eased * target))
        if (progress < 1) rafRef.current = requestAnimationFrame(tick)
      }
      rafRef.current = requestAnimationFrame(tick)
    }, delay)

    return () => {
      clearTimeout(timer)
      if (rafRef.current) cancelAnimationFrame(rafRef.current)
    }
  }, [target, duration, delay])

  return current
}

export default function StatCard({ label, value, sub, accent = 'var(--gold)', animate = true, delay = 0 }: StatCardProps) {
  const isNumber = typeof value === 'number'
  const displayed = animate && isNumber ? useCountUp(value as number, 800, delay) : value

  const formatted = typeof displayed === 'number'
    ? displayed.toLocaleString()
    : displayed

  return (
    <div
      className="card animate-slide-up p-5 flex flex-col justify-between"
      style={{ animationDelay: `${delay}ms`, animationFillMode: 'both' }}
    >
      <div className="font-mono text-[10px] tracking-[0.12em] uppercase mb-3" style={{ color: 'var(--text-dim)' }}>
        {label}
      </div>
      <div>
        <div className="font-display text-3xl italic leading-none" style={{ color: accent }}>
          {formatted}
        </div>
        {sub && (
          <div className="font-mono text-[11px] mt-2" style={{ color: 'var(--text-dim)' }}>
            {sub}
          </div>
        )}
      </div>
    </div>
  )
}