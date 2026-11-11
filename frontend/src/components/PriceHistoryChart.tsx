import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Activity, Loader2 } from 'lucide-react'
import type { LaptopPriceHistoryResponse, StorePriceSeries } from '../types/api'
import { fetchLaptopPriceHistory } from '../services/api'

interface PriceHistoryChartProps {
  laptopId: string
  lang: 'ar' | 'en'
}

type WindowOption = 30 | 90 | 'all'

/** Store curve colors follow the reference discipline: gold first, then cyan,
 *  indigo, emerald, amber, violet. Colour identifies the store, never a value. */
const SERIES_COLORS = [
  'var(--gold)',
  'var(--cyan)',
  'var(--indigo)',
  'var(--success)',
  'var(--warning)',
  'var(--tier-expansion)',
]

const WINDOW_OPTIONS: { id: WindowOption; labelEn: string; labelAr: string }[] = [
  { id: 30, labelEn: '30D', labelAr: '30ي' },
  { id: 90, labelEn: '90D', labelAr: '90ي' },
  { id: 'all', labelEn: 'ALL', labelAr: 'الكل' },
]

const PAD = { top: 18, right: 16, bottom: 28, left: 62 }

function formatPrice(value: number): string {
  return Math.round(value).toLocaleString('en-US')
}

function formatDate(iso: string, lang: 'ar' | 'en'): string {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return iso
  return date.toLocaleDateString(lang === 'ar' ? 'ar-EG' : 'en-GB', {
    month: 'short',
    day: 'numeric',
  })
}

function formatFullDate(iso: string, lang: 'ar' | 'en'): string {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return iso
  return date.toLocaleDateString(lang === 'ar' ? 'ar-EG' : 'en-GB', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  })
}

/** Build a step-after path: M x0,y0 H x1 V y1 H x2 V y2 ... */
function buildStepPath(points: { x: number; y: number }[]): string {
  if (points.length === 0) return ''
  const [first, ...rest] = points
  let d = `M ${first.x.toFixed(2)} ${first.y.toFixed(2)}`
  for (const point of rest) {
    d += ` H ${point.x.toFixed(2)} V ${point.y.toFixed(2)}`
  }
  return d
}

export const PriceHistoryChart: React.FC<PriceHistoryChartProps> = ({ laptopId, lang }) => {
  const isAr = lang === 'ar'
  const [windowOption, setWindowOption] = useState<WindowOption>(90)
  const [data, setData] = useState<LaptopPriceHistoryResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<boolean>(false)
  const [hiddenStores, setHiddenStores] = useState<Set<string>>(new Set())
  const [hover, setHover] = useState<{ x: number; index: number } | null>(null)
  const svgRef = useRef<SVGSVGElement | null>(null)

  const days = windowOption === 'all' ? undefined : windowOption

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(false)

    fetchLaptopPriceHistory(laptopId, days)
      .then((res) => {
        if (cancelled) return
        setData(res)
        setHiddenStores(new Set())
      })
      .catch((err) => {
        if (cancelled) return
        console.error(err)
        setError(true)
      })
      .finally(() => {
        if (cancelled) return
        setLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [laptopId, days])

  const visibleSeries = useMemo(
    () => (data?.series ?? []).filter((s) => !hiddenStores.has(s.store_key)),
    [data, hiddenStores]
  )

  const geometry = useMemo(() => {
    if (!data || data.series.length === 0) return null

    const timestamps: number[] = []
    const prices: number[] = []
    for (const series of data.series) {
      for (const point of series.points) {
        const t = new Date(point.recorded_at).getTime()
        if (!Number.isNaN(t)) timestamps.push(t)
        prices.push(point.price_egp)
      }
    }
    if (timestamps.length === 0 || prices.length === 0) return null

    const minTime = Math.min(...timestamps)
    const maxTime = Math.max(...timestamps)
    const rawMin = Math.min(...prices)
    const rawMax = Math.max(...prices)
    // 8% top/bottom padding keeps curves off the plot edges.
    const rawSpan = rawMax - rawMin
    const span = rawSpan === 0 ? (rawMin > 0 ? rawMin * 0.1 : 1000) : rawSpan
    const minPrice = Math.max(0, rawMin - span * 0.08)
    const maxPrice = rawMax + span * 0.08
    const timeSpan = Math.max(86400000, maxTime - minTime)

    return { minTime, maxTime, minPrice, maxPrice, timeSpan }
  }, [data])

  const [size, setSize] = useState({ width: 720, height: 260 })
  const containerRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    const observer = new ResizeObserver((entries) => {
      const entry = entries[0]
      if (!entry) return
      const width = Math.max(320, entry.contentRect.width)
      setSize({ width, height: width < 520 ? 220 : 260 })
    })
    observer.observe(el)
    return () => observer.disconnect()
  }, [])

  const plot = useMemo(() => {
    if (!geometry) return null
    const innerWidth = size.width - PAD.left - PAD.right
    const innerHeight = size.height - PAD.top - PAD.bottom
    const xOf = (iso: string) => {
      const t = new Date(iso).getTime()
      return PAD.left + ((t - geometry.minTime) / geometry.timeSpan) * innerWidth
    }
    const yOf = (price: number) =>
      PAD.top +
      (1 - (price - geometry.minPrice) / Math.max(1, geometry.maxPrice - geometry.minPrice)) *
        innerHeight

    return { innerWidth, innerHeight, xOf, yOf }
  }, [geometry, size])

  const gridLines = useMemo(() => {
    if (!geometry) return []
    const steps = 4
    return Array.from({ length: steps + 1 }, (_, i) => {
      // ratio 0 is top of SVG canvas, ratio 1 is bottom.
      // Top shows highest price (maxPrice); Bottom shows lowest price (minPrice).
      const ratio = i / steps
      const value = geometry.maxPrice - ((geometry.maxPrice - geometry.minPrice) * i) / steps
      return { value, ratio }
    })
  }, [geometry])

  const timeTicks = useMemo(() => {
    if (!geometry || !data) return []
    const count: number = size.width < 520 ? 3 : 5
    return Array.from({ length: count }, (_, i) => {
      const ratio = i / (count - 1)
      const t = geometry.minTime + geometry.timeSpan * ratio
      return { iso: new Date(t).toISOString(), ratio }
    })
  }, [geometry, data, size.width])

  const handlePointer = useCallback(
    (event: React.PointerEvent<SVGSVGElement>) => {
      if (!plot || !data || !geometry) return
      const rect = svgRef.current?.getBoundingClientRect()
      if (!rect) return
      const px = event.clientX - rect.left
      const clamped = Math.min(PAD.left + plot.innerWidth, Math.max(PAD.left, px))
      const t = geometry.minTime + ((clamped - PAD.left) / plot.innerWidth) * geometry.timeSpan
      setHover({ x: clamped, index: t })
    },
    [plot, data, geometry]
  )

  const hoverReadout = useMemo(() => {
    if (!hover || !data) return null
    const hoverTime = hover.index
    const rows = data.series
      .filter((s) => !hiddenStores.has(s.store_key))
      .map((series) => {
        // Last point at or before the hovered time = active step value.
        let active = series.points[0]
        for (const point of series.points) {
          if (new Date(point.recorded_at).getTime() <= hoverTime) active = point
        }
        return { series, price: active?.price_egp ?? series.current_price_egp }
      })
    const iso = new Date(hoverTime).toISOString()
    return { iso, rows }
  }, [hover, data, hiddenStores])

  const colorFor = (storeKey: string): string => {
    const index = data?.series.findIndex((s) => s.store_key === storeKey) ?? 0
    return SERIES_COLORS[(index < 0 ? 0 : index) % SERIES_COLORS.length]
  }

  const toggleStore = (storeKey: string) => {
    setHiddenStores((prev) => {
      const next = new Set(prev)
      if (next.has(storeKey)) next.delete(storeKey)
      else next.add(storeKey)
      return next
    })
  }

  const hasSeries = (data?.series.length ?? 0) > 0

  return (
    <div className="price-history">
      <div className="price-history-head">
        <span className="label flex items-center gap-1.5">
          <Activity className="w-3.5 h-3.5" strokeWidth={1.8} style={{ color: 'var(--cyan)' }} />
          <span>{isAr ? 'تتبع تغير الأسعار عبر الزمن' : 'Price History Telemetry'}</span>
        </span>

        <div className="seg" role="group" aria-label={isAr ? 'نطاق زمني' : 'Time window'}>
          {WINDOW_OPTIONS.map((opt) => (
            <button
              key={String(opt.id)}
              type="button"
              aria-pressed={windowOption === opt.id}
              onClick={() => setWindowOption(opt.id)}
            >
              {isAr ? opt.labelAr : opt.labelEn}
            </button>
          ))}
        </div>
      </div>

      {/* KPI summary row */}
      <div className="price-history-kpis">
        <div className="kpi">
          <span className="micro">{isAr ? 'أفضل سعر حالي' : 'Current Best Price'}</span>
          <span className="kpi-value gold num">
            {formatPrice(data?.current_best_price_egp ?? 0)}
            <small> EGP</small>
          </span>
        </div>
        <div className="kpi">
          <span className="micro">{isAr ? 'أقل سعر مسجل' : 'Lowest Recorded'}</span>
          <span className="kpi-value success num">
            {formatPrice(data?.lowest_ever_price_egp ?? 0)}
            <small> EGP</small>
          </span>
          <span className="kpi-note mono">{data?.lowest_ever_store || '—'}</span>
        </div>
        <div className="kpi">
          <span className="micro">{isAr ? 'أعلى سعر مسجل' : 'Highest Recorded'}</span>
          <span className="kpi-value secondary num">
            {formatPrice(data?.highest_ever_price_egp ?? 0)}
            <small> EGP</small>
          </span>
        </div>
      </div>

      {/* Plot well */}
      <div className="price-plot-well" ref={containerRef}>
        {loading && !data ? (
          <div className="price-plot-state">
            <Loader2 className="w-4 h-4 animate-spin" strokeWidth={1.8} />
            <span>{isAr ? 'جاري تحميل سجل الأسعار...' : 'Loading price history...'}</span>
          </div>
        ) : error ? (
          <div className="price-plot-state">
            <span>
              {isAr ? 'تعذر تحميل سجل الأسعار.' : 'Could not load price history.'}
            </span>
          </div>
        ) : !hasSeries ? (
          <div className="price-plot-state">
            <span>
              {isAr ? 'لا يوجد سجل أسعار كافٍ لهذا الموديل بعد.' : 'No price history recorded yet.'}
            </span>
          </div>
        ) : (
          <svg
            ref={svgRef}
            width={size.width}
            height={size.height}
            viewBox={`0 0 ${size.width} ${size.height}`}
            role="img"
            aria-label={isAr ? 'مخطط تاريخ الأسعار' : 'Price history chart'}
            className="price-plot-svg"
            onPointerMove={handlePointer}
            onPointerLeave={() => setHover(null)}
          >
            {/* horizontal EGP grid hairlines */}
            {gridLines.map((line) => {
              const y = PAD.top + line.ratio * (size.height - PAD.top - PAD.bottom)
              return (
                <g key={`grid-${line.ratio}`}>
                  <line
                    x1={PAD.left}
                    x2={size.width - PAD.right}
                    y1={y}
                    y2={y}
                    stroke="var(--border-subtle)"
                    strokeWidth={1}
                  />
                  <text
                    x={PAD.left - 8}
                    y={y + 4}
                    textAnchor="end"
                    className="price-axis-label"
                  >
                    {formatPrice(line.value)}
                  </text>
                </g>
              )
            })}

            {/* vertical date ticks */}
            {timeTicks.map((tick, i) => {
              const x = PAD.left + tick.ratio * (size.width - PAD.left - PAD.right)
              return (
                <g key={`tick-${i}`}>
                  <line
                    x1={x}
                    x2={x}
                    y1={PAD.top}
                    y2={size.height - PAD.bottom}
                    stroke="var(--border-subtle)"
                    strokeWidth={1}
                    strokeDasharray="2 4"
                    opacity={0.55}
                  />
                  <text
                    x={x}
                    y={size.height - PAD.bottom + 16}
                    textAnchor={i === 0 ? 'start' : i === timeTicks.length - 1 ? 'end' : 'middle'}
                    className="price-axis-label"
                  >
                    {formatDate(tick.iso, lang)}
                  </text>
                </g>
              )
            })}

            {/* step-after lines, one per store */}
            {plot &&
              visibleSeries.map((series: StorePriceSeries) => {
                const color = colorFor(series.store_key)
                const coords = series.points.map((p) => ({
                  x: plot.xOf(p.recorded_at),
                  y: plot.yOf(p.price_egp),
                  isLive: p.is_live_edge,
                }))
                const path = buildStepPath(coords)
                return (
                  <g key={series.store_key}>
                    <path
                      d={path}
                      fill="none"
                      stroke={color}
                      strokeWidth={2}
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                    {coords.map((c, i) =>
                      c.isLive ? (
                        <g key={`live-${i}`}>
                          <circle cx={c.x} cy={c.y} r={5} fill={color} opacity={0.22} />
                          <circle cx={c.x} cy={c.y} r={3} fill={color} />
                        </g>
                      ) : (
                        <circle key={`pt-${i}`} cx={c.x} cy={c.y} r={2.5} fill={color} />
                      )
                    )}
                  </g>
                )
              })}

            {/* crosshair */}
            {hover && (
              <g pointerEvents="none">
                <line
                  x1={hover.x}
                  x2={hover.x}
                  y1={PAD.top}
                  y2={size.height - PAD.bottom}
                  stroke="var(--text-muted)"
                  strokeWidth={1}
                  strokeDasharray="3 3"
                />
              </g>
            )}
          </svg>
        )}

        {hoverReadout && hasSeries && !loading && !error && (
          <div className="price-crosshair-readout">
            <span className="mono readout-date">
              {formatFullDate(hoverReadout.iso, lang)}
            </span>
            <div className="readout-rows">
              {hoverReadout.rows.map(({ series, price }) => (
                <span key={series.store_key} className="readout-row">
                  <span
                    className="readout-dot"
                    style={{ background: colorFor(series.store_key) }}
                  />
                  <span className="readout-store">{series.store_name}</span>
                  <span className="readout-price num">{formatPrice(price)} EGP</span>
                </span>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Store legend pills — click to toggle visibility */}
      {hasSeries && (
        <div className="price-legend">
          {data?.series.map((series) => {
            const isHidden = hiddenStores.has(series.store_key)
            const color = colorFor(series.store_key)
            return (
              <button
                key={series.store_key}
                type="button"
                aria-pressed={!isHidden}
                onClick={() => toggleStore(series.store_key)}
                className={`legend-pill ${isHidden ? 'is-hidden' : ''}`}
                title={
                  isAr
                    ? 'اضغط لعرض/إخفاء هذا المتجر'
                    : 'Click to toggle this store'
                }
              >
                <span className="legend-swatch" style={{ background: color }} />
                <span className="legend-name">{series.store_name}</span>
                <span className="legend-price num">{formatPrice(series.current_price_egp)}</span>
                {series.is_cheapest && !isHidden && (
                  <span className="legend-best">{isAr ? 'الأرخص' : 'Best'}</span>
                )}
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
}

export default PriceHistoryChart
