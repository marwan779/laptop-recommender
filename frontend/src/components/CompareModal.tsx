import React, { useEffect, useMemo, useState } from 'react'
import { ExternalLink, X } from 'lucide-react'
import type { CompareEntry } from '../types/compare'
import type { FullLaptopDetailResponse } from '../types/api'
import { fetchLaptopDetail } from '../services/api'

interface CompareModalProps {
  entries: CompareEntry[]
  lang: 'ar' | 'en'
  onClose: () => void
}

interface LoadState {
  id: string
  detail: FullLaptopDetailResponse | null
  error: string | null
}

const egp = (value: number | null | undefined) =>
  value != null ? value.toLocaleString('en-US') : '—'

const val = (value: unknown, suffix = '') =>
  value === null || value === undefined || value === '' ? '—' : `${value}${suffix}`

export const CompareModal: React.FC<CompareModalProps> = ({ entries, lang, onClose }) => {
  const isAr = lang === 'ar'
  const [states, setStates] = useState<LoadState[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    Promise.allSettled(entries.map((entry) => fetchLaptopDetail(entry.id))).then((results) => {
      if (cancelled) return
      setStates(
        entries.map((entry, index) => {
          const result = results[index]
          if (result.status === 'fulfilled') {
            return { id: entry.id, detail: result.value, error: null }
          }
          return {
            id: entry.id,
            detail: null,
            error: result.reason instanceof Error ? result.reason.message : 'Failed to load',
          }
        }),
      )
      setLoading(false)
    })
    return () => {
      cancelled = true
    }
  }, [entries])

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const details = useMemo(
    () => states.map((state) => state.detail).filter((detail): detail is FullLaptopDetailResponse => !!detail),
    [states],
  )

  const winner = (values: Array<number | null | undefined>): number | null => {
    const numeric = values.filter((v): v is number => typeof v === 'number' && Number.isFinite(v))
    if (numeric.length < 2) return null
    const max = Math.max(...numeric)
    if (new Set(numeric).size === 1) return null
    return max
  }

  interface CompareRow {
    label: string
    value: (detail: FullLaptopDetailResponse) => React.ReactNode
    numeric?: (detail: FullLaptopDetailResponse) => number | null
    winnerMax?: boolean
  }

  const rows: CompareRow[] = [
    {
      label: isAr ? 'أقل سعر' : 'Lowest price',
      numeric: (d) => d.min_price_egp,
      winnerMax: false,
      value: (d) => (
        <span className="font-display font-semibold tabular-nums">
          {egp(d.min_price_egp)} {isAr ? 'ج.م' : 'EGP'}
        </span>
      ),
    },
    { label: isAr ? 'أرخص متجر' : 'Cheapest store', value: (d) => val(d.cheapest_store) },
    {
      label: isAr ? 'فرق الأسعار' : 'Price spread',
      numeric: (d) => d.price_spread_egp ?? null,
      value: (d) =>
        d.price_spread_egp != null
          ? `${egp(d.price_spread_egp)} ${isAr ? 'ج.م' : 'EGP'}`
          : '—',
    },
    {
      label: 'CPU',
      value: (d) => (
        <span dir="ltr">
          {val(d.cpu?.full_name || d.cpu?.model)}
          {d.cpu?.cores ? ` · ${d.cpu.cores}C/${d.cpu.threads}T` : ''}
        </span>
      ),
    },
    {
      label: 'GPU',
      value: (d) => (
        <span dir="ltr">
          {val(d.gpu?.model)}
          {d.gpu?.vram_gb ? ` · ${d.gpu.vram_gb}GB` : ''}
          {d.gpu?.tdp_w ? ` · ${d.gpu.tdp_w}W` : ''}
        </span>
      ),
    },
    {
      label: isAr ? 'الرام' : 'RAM',
      numeric: (d) => d.memory?.capacity_gb ?? null,
      value: (d) => (
        <span dir="ltr">
          {val(d.memory?.capacity_gb, 'GB')} {d.memory?.memory_type || ''}
          {d.memory?.is_soldered
            ? isAr
              ? ' · ملحومة'
              : ' · soldered'
            : d.memory?.max_supported_gb
            ? ` · max ${d.memory.max_supported_gb}GB`
            : ''}
        </span>
      ),
    },
    {
      label: isAr ? 'التخزين' : 'Storage',
      numeric: (d) => d.storage?.capacity_gb ?? null,
      value: (d) => (
        <span dir="ltr">
          {val(d.storage?.capacity_gb, 'GB')}
          {d.storage?.slot_count != null ? ` · ${d.storage.slot_count} slots` : ''}
        </span>
      ),
    },
    {
      label: isAr ? 'الشاشة' : 'Display',
      numeric: (d) => d.display?.size_inches ?? null,
      value: (d) => (
        <span dir="ltr">
          {val(d.display?.size_inches, '"')} {d.display?.resolution || ''} {d.display?.refresh_rate_hz ? `· ${d.display.refresh_rate_hz}Hz` : ''}
          {d.display?.panel_type ? ` · ${d.display.panel_type}` : ''}
          {d.display?.color_gamut ? ` · ${d.display.color_gamut}` : ''}
          {d.display?.brightness_nits ? ` · ${d.display.brightness_nits} nits` : ''}
        </span>
      ),
    },
    {
      label: isAr ? 'البطارية والوزن' : 'Battery & weight',
      value: (d) => (
        <span dir="ltr">
          {d.power_battery?.battery_capacity_wh ? `${d.power_battery.battery_capacity_wh}Wh` : '—'}
          {d.metrics?.estimated_battery_hours ? ` · ~${d.metrics.estimated_battery_hours}h` : ''}
          {d.physical?.weight_kg ? ` · ${d.physical.weight_kg}kg` : ''}
        </span>
      ),
    },
    {
      label: isAr ? 'التبريد' : 'Thermals',
      numeric: (d) => d.metrics?.thermals_score ?? null,
      value: (d) => val(d.metrics?.thermals_score != null ? Math.round(d.metrics.thermals_score) : null),
    },
    {
      label: isAr ? 'هدوء المراوح' : 'Acoustics',
      numeric: (d) => d.metrics?.acoustics_score ?? null,
      value: (d) => val(d.metrics?.acoustics_score != null ? Math.round(d.metrics.acoustics_score) : null),
    },
    {
      label: isAr ? 'الخامة والمفصلات' : 'Build & hinges',
      numeric: (d) => d.metrics?.build_and_hinges_score ?? null,
      value: (d) => val(d.metrics?.build_and_hinges_score != null ? Math.round(d.metrics.build_and_hinges_score) : null),
    },
    {
      label: isAr ? 'الكيبورد' : 'Keyboard',
      numeric: (d) => d.metrics?.keyboard_and_trackpad_score ?? null,
      value: (d) => val(d.metrics?.keyboard_and_trackpad_score != null ? Math.round(d.metrics.keyboard_and_trackpad_score) : null),
    },
    {
      label: isAr ? 'عمر البطارية الحقيقي' : 'Real battery',
      numeric: (d) => d.metrics?.real_battery_and_reliability_score ?? null,
      value: (d) => val(d.metrics?.real_battery_and_reliability_score != null ? Math.round(d.metrics.real_battery_and_reliability_score) : null),
    },
    {
      label: isAr ? 'أهم ميزة' : 'Top strength',
      value: (d) => <span dir="auto">{val(isAr ? d.pros_ar?.[0] : d.pros_en?.[0])}</span>,
    },
    {
      label: isAr ? 'أهم تنازل' : 'Top tradeoff',
      value: (d) => <span dir="auto">{val(isAr ? d.cons_ar?.[0] : d.cons_en?.[0])}</span>,
    },
  ]

  const columns = `minmax(94px, 118px) repeat(${entries.length}, minmax(168px, 1fr))`

  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true" onClick={onClose}>
      <div
        className="modal-frame max-h-[92vh] sm:max-h-[88vh]"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="modal-header">
          <div className="min-w-0">
            <h2 className="font-display text-[17px] font-semibold text-[var(--text-primary)]">
              {isAr ? 'مقارنة الأجهزة' : 'Compare laptops'}
            </h2>
            <p className="text-[12px] text-[var(--text-muted)]">
              {isAr ? 'نفس المعايير جنب بعض — الخلية الأفضل مميزة.' : 'Same criteria side by side — best value highlighted.'}
            </p>
          </div>
          <button type="button" onClick={onClose} className="modal-close" aria-label={isAr ? 'إغلاق' : 'Close'}>
            <X className="w-4 h-4" strokeWidth={2} />
          </button>
        </div>

        <div className="modal-body flex-1 overflow-auto">
          {loading ? (
            <div className="py-16 flex flex-col items-center gap-3">
              <div className="spinner" />
              <p className="text-[12px] text-[var(--text-muted)]">
                {isAr ? 'جاري تحميل التفاصيل...' : 'Loading details...'}
              </p>
            </div>
          ) : (
            <div className="overflow-x-auto pb-2">
              <p className="md:hidden text-[11px] text-[var(--text-muted)] mb-2">
                {isAr ? 'اسحب الجدول جانباً لمشاهدة بقية الأجهزة ←' : 'Swipe the table sideways to see the other laptops →'}
              </p>
              <div className="min-w-[420px]">
                <div
                  className="grid gap-px bg-[var(--border-subtle)] rounded-[10px] overflow-hidden"
                  style={{ gridTemplateColumns: columns }}
                >
                  {/* Header */}
                  <div className="bg-[var(--bg-raised)] cmp-sticky-cell" />
                  {entries.map((entry, index) => {
                    const state = states[index]
                    return (
                      <div key={entry.id} className="bg-[var(--bg-raised)] p-2.5 space-y-1.5">
                        <div className="studio-well !aspect-[4/3] !p-1.5">
                          <img src={entry.thumbnail_url} alt="" className="w-full h-full object-contain" />
                        </div>
                        <div dir="auto" className="cmp-name text-[12px] font-semibold text-[var(--text-primary)] line-clamp-2">
                          {entry.title}
                        </div>
                        {state?.error && (
                          <p className="text-[10px] text-[var(--danger)] line-clamp-2">{state.error}</p>
                        )}
                      </div>
                    )
                  })}

                  {/* Rows */}
                  {rows.map((row) => {
                    const nums = details.map((detail) => (row.numeric ? row.numeric(detail) : null))
                    const best = row.numeric ? winner(nums) : null
                    return (
                      <React.Fragment key={row.label}>
                        <div className="cmp-sticky-cell bg-[var(--bg-raised)] px-2.5 py-2 text-[11.5px] font-semibold text-[var(--text-secondary)] flex items-center">
                          {row.label}
                        </div>
                        {entries.map((entry, index) => {
                          const detail = states[index]?.detail
                          const numericValue = detail && row.numeric ? row.numeric(detail) : null
                          const isBest = best != null && numericValue === best
                          return (
                            <div
                              key={`${row.label}-${entry.id}`}
                              className={`px-2.5 py-2 text-[11.5px] leading-[1.5] ${
                                isBest
                                  ? 'bg-[var(--success-dim)] text-[var(--success)] font-semibold'
                                  : 'bg-[var(--bg-surface)] text-[var(--text-primary)]'
                              }`}
                            >
                              {detail ? row.value(detail) : '—'}
                            </div>
                          )
                        })}
                      </React.Fragment>
                    )
                  })}

                  {/* CTA row */}
                  <div className="bg-[var(--bg-raised)] cmp-sticky-cell" />
                  {entries.map((entry, index) => {
                    const detail = states[index]?.detail
                    return (
                      <div key={`cta-${entry.id}`} className="bg-[var(--bg-surface)] p-2">
                        {detail?.cheapest_offer_url ? (
                          <a
                            href={detail.cheapest_offer_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="btn btn-primary btn-sm w-full"
                          >
                            <span>
                              {isAr ? `اشترِ من ${detail.cheapest_store}` : `Buy at ${detail.cheapest_store}`}
                            </span>
                            <ExternalLink className="w-3 h-3" strokeWidth={2} />
                          </a>
                        ) : (
                          <span className="text-[11px] text-[var(--text-muted)]">—</span>
                        )}
                      </div>
                    )
                  })}
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
