import React, { useEffect, useMemo, useState } from 'react'
import {
  Award,
  BatteryCharging,
  ChevronDown,
  ChevronUp,
  Cpu,
  ExternalLink,
  Gauge,
  Monitor,
  Tag,
  Wifi,
  X,
} from 'lucide-react'
import type { CompareEntry } from '../types/compare'
import type { FullLaptopDetailResponse } from '../types/api'
import { fetchLaptopDetail } from '../services/api'
import {
  getDisplayTierInfo,
  getSiliconTierInfo,
  getUpgradeabilityTierInfo,
} from '../utils/hardwareTiers'
import { isOfferAvailable, isPlaceholderPrice, isValidDisplayPrice } from '../utils/availability'

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

interface CompareRow {
  key: string
  label: string
  value: (detail: FullLaptopDetailResponse) => React.ReactNode
  numeric?: (detail: FullLaptopDetailResponse) => number | null
  winnerMax?: boolean
  compareKey?: (detail: FullLaptopDetailResponse) => string | number | boolean | null
}

type SectionId =
  | 'pricing'
  | 'scores'
  | 'silicon'
  | 'display'
  | 'power'
  | 'connectivity'
  | 'reviews'

interface CompareSection {
  id: SectionId
  title: string
  icon: React.ReactNode
  rows: CompareRow[]
}

const egp = (value: number | null | undefined) =>
  value != null ? value.toLocaleString('en-US') : '—'

const val = (value: unknown, suffix = '') =>
  value === null || value === undefined || value === '' ? '—' : `${value}${suffix}`

const joinParts = (parts: Array<string | number | null | undefined | false>) =>
  parts.filter((part) => part !== null && part !== undefined && part !== '' && part !== false).join(' · ')

const specCell = (primary: React.ReactNode, secondary?: string) => (
  <div dir="ltr" className="space-y-0.5 text-start tabular-nums">
    <div className="font-medium">{primary}</div>
    {secondary ? (
      <div className="text-[12px] text-[var(--text-secondary)]">{secondary}</div>
    ) : null}
  </div>
)

const renderScoreCell = (score: number | null | undefined) => {
  if (score == null || !Number.isFinite(score)) return '—'
  const rounded = Math.round(score)
  const tone =
    rounded >= 85
      ? 'text-[var(--gold-bright)]'
      : rounded < 50
        ? 'text-[var(--danger)]'
        : 'text-[var(--text-primary)]'
  return (
    <div className="flex items-center gap-2">
      <span className={`font-display font-semibold tabular-nums min-w-[26px] ${tone}`}>
        {rounded}
      </span>
      <div className="cmp-score-track">
        <div
          className="cmp-score-fill"
          style={{ width: `${Math.min(100, Math.max(0, rounded))}%` }}
        />
      </div>
    </div>
  )
}

export const CompareModal: React.FC<CompareModalProps> = ({ entries, lang, onClose }) => {
  const isAr = lang === 'ar'
  const [states, setStates] = useState<LoadState[]>([])
  const [loading, setLoading] = useState(true)
  const [diffOnly, setDiffOnly] = useState(false)
  const [expandedSections, setExpandedSections] = useState<Record<SectionId, boolean>>({
    pricing: true,
    scores: true,
    silicon: true,
    display: true,
    power: false,
    connectivity: false,
    reviews: true,
  })

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

  const winner = (
    values: Array<number | null | undefined>,
    winnerMax = true,
  ): number | null => {
    const numeric = values.filter(
      (value): value is number => typeof value === 'number' && Number.isFinite(value),
    )
    if (numeric.length < 2) return null
    if (new Set(numeric).size === 1) return null
    return winnerMax ? Math.max(...numeric) : Math.min(...numeric)
  }

  const scoreRow = (
    key: string,
    label: string,
    getter: (detail: FullLaptopDetailResponse) => number | null | undefined,
  ): CompareRow => ({
    key,
    label,
    numeric: (detail) => getter(detail) ?? null,
    winnerMax: true,
    compareKey: (detail) => getter(detail) ?? null,
    value: (detail) => renderScoreCell(getter(detail)),
  })

  const sections: CompareSection[] = [
    {
      id: 'pricing',
      title: isAr ? 'الأسعار وتوفر المتاجر' : 'Pricing & Store Availability',
      icon: <Tag className="w-4 h-4" strokeWidth={1.8} />,
      rows: [
        {
          key: 'price',
          label: isAr ? 'أقل سعر' : 'Lowest price',
          numeric: (detail) => (isValidDisplayPrice(detail.min_price_egp) ? detail.min_price_egp : null),
          winnerMax: false,
          compareKey: (detail) => (isValidDisplayPrice(detail.min_price_egp) ? detail.min_price_egp : null),
          value: (detail) =>
            isValidDisplayPrice(detail.min_price_egp) ? (
              <span className="font-display font-semibold tabular-nums text-[var(--gold)]">
                {egp(detail.min_price_egp)} {isAr ? 'ج.م' : 'EGP'}
              </span>
            ) : (
              <span className="text-[12px] text-[var(--text-muted)]">
                {isPlaceholderPrice(detail.min_price_egp) ? (isAr ? 'قريباً' : 'Coming soon') : '—'}
              </span>
            ),
        },
        {
          key: 'stock',
          label: isAr ? 'حالة التوفر' : 'Stock status',
          compareKey: (detail) => Boolean(detail.in_stock && isValidDisplayPrice(detail.min_price_egp)),
          value: (detail) =>
            detail.in_stock && isValidDisplayPrice(detail.min_price_egp) ? (
              <span className="inline-flex items-center rounded-md border border-[var(--success)] bg-[var(--success-dim)] px-2 py-0.5 text-[12px] font-semibold text-[var(--success)]">
                {isAr ? 'متوفر' : 'In stock'}
              </span>
            ) : isPlaceholderPrice(detail.min_price_egp) ? (
              <span className="inline-flex items-center rounded-md border border-[var(--warning)] bg-[var(--warning-dim)] px-2 py-0.5 text-[12px] font-semibold text-[var(--warning)]">
                {isAr ? 'قريباً' : 'Coming soon'}
              </span>
            ) : (
              <span className="inline-flex items-center rounded-md border border-[var(--danger)] bg-[var(--danger-dim)] px-2 py-0.5 text-[12px] font-semibold text-[var(--danger)]">
                {isAr ? 'غير متوفر' : 'Out of stock'}
              </span>
            ),
        },
        {
          key: 'cheapest-store',
          label: isAr ? 'أرخص متجر' : 'Cheapest store',
          compareKey: (detail) => detail.cheapest_store ?? '',
          value: (detail) => val(detail.cheapest_store),
        },
        {
          key: 'stores-spread',
          label: isAr ? 'المتاجر وفرق السعر' : 'Stores & price spread',
          compareKey: (detail) => `${detail.stores_count}-${detail.price_spread_egp ?? ''}`,
          value: (detail) => (
            <span className="tabular-nums">
              {detail.stores_count} {isAr ? 'متاجر' : 'stores'}
              {detail.price_spread_egp != null && detail.price_spread_egp > 0
                ? ` · ${isAr ? 'فرق' : 'spread'} ${egp(detail.price_spread_egp)} ${isAr ? 'ج.م' : 'EGP'}`
                : ''}
            </span>
          ),
        },
        {
          key: 'offers',
          label: isAr ? 'عروض المتاجر' : 'Store offers',
          compareKey: (detail) =>
            (detail.offers || [])
              .map((offer) => `${offer.store_key}:${offer.price_egp}:${offer.in_stock}`)
              .join('|'),
          value: (detail) => {
            const offers = (detail.offers || [])
              .filter(
                (offer) => (offer as { is_valid_price?: boolean }).is_valid_price !== false,
              )
              .sort((a, b) => a.price_egp - b.price_egp)
              .slice(0, 4)
            if (!offers.length) return '—'
            return (
              <ul className="space-y-1 text-[12px]">
                {offers.map((offer) => {
                  const avail = isOfferAvailable(offer)
                  return (
                    <li key={offer.store_key} className="flex items-center justify-between gap-2">
                      <span dir="auto" className="truncate text-[var(--text-secondary)]">
                        {offer.store_name}
                      </span>
                      <span className={`whitespace-nowrap tabular-nums ${avail ? 'text-[var(--gold)]' : 'text-[var(--text-muted)]'}`}>
                        {isValidDisplayPrice(offer.price_egp) ? `${egp(offer.price_egp)} ${isAr ? 'ج.م' : 'EGP'}` : '—'}
                        {!avail && (
                          <span className="text-[var(--danger)]">
                            {' '}
                            {isPlaceholderPrice(offer.price_egp)
                              ? isAr
                                ? '(قريباً)'
                                : '(Soon)'
                              : isAr
                              ? '(غير متوفر)'
                              : '(OOS)'}
                          </span>
                        )}
                      </span>
                    </li>
                  )
                })}
              </ul>
            )
          },
        },
      ],
    },
    {
      id: 'scores',
      title: isAr ? 'مؤشرات الأداء والفئات التشغيلية' : 'Performance Benchmarks & Tiers',
      icon: <Gauge className="w-4 h-4" strokeWidth={1.8} />,
      rows: [
        scoreRow('cpu-score', isAr ? 'قوة المعالج' : 'CPU Benchmark', (d) => d.metrics?.cpu_score),
        scoreRow('gpu-score', isAr ? 'أداء الجرافيكس' : 'GPU 3D Gaming', (d) => d.metrics?.gpu_score),
        scoreRow('display-score', isAr ? 'جودة الشاشة' : 'Display Quality', (d) => d.metrics?.display_score),
        scoreRow('value-score', isAr ? 'القيمة مقابل السعر' : 'Value for Money', (d) => d.metrics?.value_score),
        scoreRow(
          'power-therm-score',
          isAr ? 'استقرار الطاقة والتبريد' : 'Sustained Power & Thermals',
          (d) => d.metrics?.power_therm_score,
        ),
        scoreRow('mobility-score', isAr ? 'سهولة التنقل' : 'Mobility & Battery', (d) => d.metrics?.mobility_score),
        scoreRow('longevity-score', isAr ? 'عمر الشاسيه والترقية' : 'Chassis Longevity', (d) => d.metrics?.longevity_score),
        scoreRow('connectivity-score', isAr ? 'المنافذ والاتصال' : 'I/O & Connectivity', (d) => d.metrics?.connectivity_score),
        scoreRow('ergonomics-score', isAr ? 'الراحة والكيبورد' : 'Ergonomics & Typing', (d) => d.metrics?.ergonomics_score),
        scoreRow('community-score', isAr ? 'تجارب المستخدمين' : 'Owner Sentiment', (d) => d.metrics?.community_nlp_score),
        scoreRow('thermals-score', isAr ? 'التبريد تحت الضغط' : 'Cooling under Stress', (d) => d.metrics?.thermals_score),
        scoreRow('acoustics-score', isAr ? 'هدوء المراوح' : 'Fan Acoustics', (d) => d.metrics?.acoustics_score),
        scoreRow('build-score', isAr ? 'الخامة والمفصلات' : 'Build & Hinges', (d) => d.metrics?.build_and_hinges_score),
        scoreRow(
          'keyboard-score',
          isAr ? 'الكيبورد والتاتش باد' : 'Keyboard & Trackpad',
          (d) => d.metrics?.keyboard_and_trackpad_score,
        ),
        scoreRow(
          'battery-score',
          isAr ? 'البطارية الحقيقية' : 'Real Battery Runtime',
          (d) => d.metrics?.real_battery_and_reliability_score,
        ),
        {
          key: 'silicon-tier',
          label: isAr ? 'فئة المعالجة والتبريد' : 'Thermal & GPU Tier',
          compareKey: (detail) => detail.metrics?.silicon_tier ?? '',
          value: (detail) => {
            const tier = getSiliconTierInfo(detail.metrics?.silicon_tier, isAr)
            if (!tier) return '—'
            const raw = (detail.metrics?.silicon_tier || '').toUpperCase()
            const capped = raw === 'HEAVILY_CAPPED_GPU' || raw === 'MODERATELY_CAPPED_GPU'
            return (
              <span
                className={`inline-flex items-start gap-1.5 ${
                  capped ? 'text-[var(--warning)]' : 'text-[var(--text-primary)]'
                }`}
              >
                <span className="mt-0.5 flex-none">{tier.icon}</span>
                <span dir="auto">{tier.title}</span>
              </span>
            )
          },
        },
        {
          key: 'display-tier',
          label: isAr ? 'فئة الشاشة' : 'Display Tier',
          compareKey: (detail) => detail.metrics?.display_tier ?? '',
          value: (detail) =>
            getDisplayTierInfo(detail.metrics?.display_tier, isAr)?.title ??
            val(detail.metrics?.display_tier),
        },
        {
          key: 'upgradeability-tier',
          label: isAr ? 'قابلية الترقية' : 'Upgradeability Tier',
          compareKey: (detail) => detail.metrics?.upgradeability_tier ?? '',
          value: (detail) =>
            getUpgradeabilityTierInfo(detail.metrics?.upgradeability_tier, isAr)?.title ??
            val(detail.metrics?.upgradeability_tier),
        },
      ],
    },
    {
      id: 'silicon',
      title: isAr ? 'المعالج وكارت الشاشة والرام والتخزين' : 'Processor, Graphics, Memory & Storage',
      icon: <Cpu className="w-4 h-4" strokeWidth={1.8} />,
      rows: [
        {
          key: 'cpu',
          label: isAr ? 'المعالج' : 'Processor (CPU)',
          numeric: (detail) => detail.cpu?.cores ?? null,
          winnerMax: true,
          compareKey: (detail) =>
            `${detail.cpu?.full_name || detail.cpu?.model}-${detail.cpu?.cores}-${detail.cpu?.clock_boost_ghz}`,
          value: (detail) => {
            const cpu = detail.cpu
            const secondary = joinParts([
              cpu?.cores ? `${cpu.cores}C/${cpu.threads}T` : null,
              cpu?.clock_boost_ghz
                ? `${cpu.clock_boost_ghz} GHz`
                : cpu?.clock_base_ghz
                  ? `${cpu.clock_base_ghz} GHz`
                  : null,
              cpu?.cache_mb ? `${cpu.cache_mb}MB` : null,
              cpu?.base_power_w ? `${cpu.base_power_w}W` : null,
              cpu?.npu_tops ? `${cpu.npu_tops} NPU TOPS` : null,
            ])
            return specCell(cpu?.full_name || cpu?.model || '—', secondary)
          },
        },
        {
          key: 'gpu',
          label: isAr ? 'كارت الشاشة' : 'Graphics (GPU)',
          numeric: (detail) => detail.gpu?.vram_gb ?? null,
          winnerMax: true,
          compareKey: (detail) =>
            `${detail.gpu?.model}-${detail.gpu?.vram_gb}-${detail.gpu?.vram_type}`,
          value: (detail) => {
            const gpu = detail.gpu
            const secondary = joinParts([
              gpu?.integrated
                ? isAr
                  ? 'مدمج'
                  : 'Integrated'
                : gpu?.vram_gb
                  ? `${gpu.vram_gb}GB${gpu.vram_type ? ` ${gpu.vram_type}` : ''}`
                  : null,
              gpu?.ai_tops ? `${gpu.ai_tops} AI TOPS` : null,
              !gpu?.integrated && gpu?.igpu_model ? `+ ${gpu.igpu_model}` : null,
            ])
            return specCell(
              `${gpu?.model || '—'}${gpu?.variant ? ` (${gpu.variant})` : ''}`,
              secondary,
            )
          },
        },
        {
          key: 'gpu-tgp',
          label: isAr ? 'طاقة الجرافيكس (TGP)' : 'GPU Power (TGP)',
          numeric: (detail) => detail.gpu?.tdp_w ?? null,
          winnerMax: true,
          compareKey: (detail) => `${detail.gpu?.tdp_w ?? ''}-${detail.gpu?.native_max_tgp_w ?? ''}`,
          value: (detail) => {
            const gpu = detail.gpu
            if (!gpu?.tdp_w) return '—'
            const pct = gpu.tgp_utilization_pct
            return (
              <span dir="ltr" className="tabular-nums">
                {gpu.tdp_w}W
                {gpu.native_max_tgp_w && pct != null && pct < 95 ? (
                  <span className="text-[10.5px] text-[var(--warning)]">
                    {' '}
                    ({pct}%{' '}
                    {isAr
                      ? `من أصل ${gpu.native_max_tgp_w}W`
                      : `of ${gpu.native_max_tgp_w}W max`}
                    )
                  </span>
                ) : null}
              </span>
            )
          },
        },
        {
          key: 'memory',
          label: isAr ? 'الذاكرة العشوائية' : 'Memory (RAM)',
          numeric: (detail) => detail.memory?.capacity_gb ?? null,
          winnerMax: true,
          compareKey: (detail) =>
            `${detail.memory?.capacity_gb}-${detail.memory?.memory_type}-${detail.memory?.speed_mhz}-${detail.memory?.is_soldered}-${detail.memory?.max_supported_gb}`,
          value: (detail) => {
            const memory = detail.memory
            const primary = `${val(memory?.capacity_gb, 'GB')} ${memory?.memory_type || ''}${
              memory?.speed_mhz ? `-${memory.speed_mhz}` : ''
            }`
            const secondary = joinParts([
              memory?.channels,
              memory?.slot_count != null
                ? `${memory.slot_count} ${isAr ? 'فتحات' : 'slots'}`
                : null,
              memory?.is_soldered
                ? isAr
                  ? 'ملحومة'
                  : 'Soldered'
                : memory?.max_supported_gb
                  ? `${isAr ? 'أقصى حد' : 'Max'} ${memory.max_supported_gb}GB`
                  : null,
            ])
            return specCell(primary.trim(), secondary)
          },
        },
        {
          key: 'storage',
          label: isAr ? 'التخزين' : 'Storage (SSD)',
          numeric: (detail) => detail.storage?.capacity_gb ?? null,
          winnerMax: true,
          compareKey: (detail) =>
            `${detail.storage?.capacity_gb}-${detail.storage?.storage_type}-${detail.storage?.interface}-${detail.storage?.slot_count}`,
          value: (detail) => {
            const storage = detail.storage
            const secondary = joinParts([
              storage?.interface,
              storage?.slot_count != null
                ? `${storage.slot_count} ${isAr ? 'منافذ M.2' : 'slots'}`
                : null,
            ])
            return specCell(
              `${val(storage?.capacity_gb, 'GB')} ${storage?.storage_type || ''}`.trim(),
              secondary,
            )
          },
        },
      ],
    },
    {
      id: 'display',
      title: isAr ? 'الشاشة' : 'Display',
      icon: <Monitor className="w-4 h-4" strokeWidth={1.8} />,
      rows: [
        {
          key: 'display-size',
          label: isAr ? 'المقاس والدقة' : 'Size & Resolution',
          numeric: (detail) => detail.display?.size_inches ?? null,
          winnerMax: true,
          compareKey: (detail) =>
            `${detail.display?.size_inches}-${detail.display?.resolution}-${detail.display?.aspect_ratio}`,
          value: (detail) => {
            const display = detail.display
            return (
              <span dir="ltr" className="tabular-nums">
                {val(display?.size_inches, '"')} · {display?.resolution || '—'}
                {display?.aspect_ratio ? ` (${display.aspect_ratio})` : ''}
              </span>
            )
          },
        },
        {
          key: 'display-refresh',
          label: isAr ? 'التردد ونوع الشاشة' : 'Refresh Rate & Panel',
          numeric: (detail) => detail.display?.refresh_rate_hz ?? null,
          winnerMax: true,
          compareKey: (detail) => `${detail.display?.refresh_rate_hz}-${detail.display?.panel_type}`,
          value: (detail) => {
            const display = detail.display
            return (
              <span dir="ltr" className="tabular-nums">
                {display?.refresh_rate_hz ? `${display.refresh_rate_hz}Hz` : '—'}
                {display?.panel_type ? ` · ${display.panel_type}` : ''}
              </span>
            )
          },
        },
        {
          key: 'display-quality',
          label: isAr ? 'الألوان والسطوع والمزايا' : 'Color, Brightness & Features',
          numeric: (detail) => detail.display?.brightness_nits ?? null,
          winnerMax: true,
          compareKey: (detail) =>
            `${detail.display?.color_gamut}-${detail.display?.brightness_nits}-${detail.display?.touchscreen}-${detail.display?.hdr}`,
          value: (detail) => {
            const display = detail.display
            const parts = joinParts([
              display?.color_gamut,
              display?.brightness_nits ? `${display.brightness_nits} nits` : null,
              display?.hdr ? 'HDR' : null,
              display?.touchscreen ? (isAr ? 'شاشة لمس' : 'Touchscreen') : null,
            ])
            return <span className="tabular-nums">{parts || '—'}</span>
          },
        },
      ],
    },
    {
      id: 'power',
      title: isAr ? 'البطارية والشاحن والوزن' : 'Power, Battery & Portability',
      icon: <BatteryCharging className="w-4 h-4" strokeWidth={1.8} />,
      rows: [
        {
          key: 'battery',
          label: isAr ? 'سعة البطارية والعمر المتوقع' : 'Battery Capacity & Est.',
          numeric: (detail) => detail.power_battery?.battery_capacity_wh ?? null,
          winnerMax: true,
          compareKey: (detail) =>
            `${detail.power_battery?.battery_capacity_wh}-${detail.power_battery?.battery_cells}-${detail.metrics?.estimated_battery_hours}`,
          value: (detail) => {
            const battery = detail.power_battery
            const parts = joinParts([
              battery?.battery_capacity_wh ? `${battery.battery_capacity_wh}Wh` : null,
              battery?.battery_cells
                ? `${battery.battery_cells}-${isAr ? 'خلايا' : 'cell'}`
                : null,
              detail.metrics?.estimated_battery_hours
                ? `~${detail.metrics.estimated_battery_hours}h`
                : null,
            ])
            return <span className="tabular-nums">{parts || '—'}</span>
          },
        },
        {
          key: 'adapter',
          label: isAr ? 'الشاحن والشحن السريع' : 'Power Adapter & Charging',
          numeric: (detail) => detail.power_battery?.power_adapter_w ?? null,
          winnerMax: true,
          compareKey: (detail) =>
            `${detail.power_battery?.power_adapter_w}-${detail.power_battery?.usb_c_pd_charging}-${detail.power_battery?.fast_charging}`,
          value: (detail) => {
            const battery = detail.power_battery
            const parts = joinParts([
              battery?.power_adapter_w ? `${battery.power_adapter_w}W` : null,
              battery?.usb_c_pd_charging ? 'USB-C PD' : null,
              battery?.fast_charging ? (isAr ? 'شحن سريع' : 'Fast Charge') : null,
            ])
            return <span className="tabular-nums">{parts || '—'}</span>
          },
        },
        {
          key: 'weight',
          label: isAr ? 'الوزن' : 'Weight',
          numeric: (detail) => detail.physical?.weight_kg ?? null,
          winnerMax: false,
          compareKey: (detail) => detail.physical?.weight_kg ?? null,
          value: (detail) => (
            <span className="tabular-nums">
              {detail.physical?.weight_kg != null ? `${detail.physical.weight_kg} kg` : '—'}
            </span>
          ),
        },
        {
          key: 'dimensions',
          label: isAr ? 'الأبعاد' : 'Dimensions (W × D × H)',
          numeric: (detail) => detail.physical?.height_mm ?? null,
          winnerMax: false,
          compareKey: (detail) =>
            `${detail.physical?.width_mm}-${detail.physical?.depth_mm}-${detail.physical?.height_mm}`,
          value: (detail) => {
            const physical = detail.physical
            if (physical?.width_mm && physical?.depth_mm && physical?.height_mm) {
              return (
                <span dir="ltr" className="tabular-nums">
                  {physical.width_mm} × {physical.depth_mm} × {physical.height_mm} mm
                </span>
              )
            }
            return (
              <span dir="ltr" className="tabular-nums">
                {physical?.height_mm ? `${physical.height_mm} mm` : '—'}
              </span>
            )
          },
        },
      ],
    },
    {
      id: 'connectivity',
      title: isAr ? 'الهيكل والأمان والصوت والمنافذ' : 'Build, Security, Audio & Connectivity',
      icon: <Wifi className="w-4 h-4" strokeWidth={1.8} />,
      rows: [
        {
          key: 'keyboard-security',
          label: isAr ? 'الكيبورد والأمان' : 'Keyboard & Security',
          compareKey: (detail) =>
            `${detail.build_security?.has_backlit_keyboard}-${detail.build_security?.keyboard_backlight_type}-${detail.build_security?.has_fingerprint}-${detail.build_security?.has_copilot_key}-${(detail.build_security?.security_features || []).join(',')}`,
          value: (detail) => {
            const build = detail.build_security
            const parts = joinParts([
              build?.has_backlit_keyboard
                ? build.keyboard_backlight_type || (isAr ? 'كيبورد مضيء' : 'Backlit')
                : isAr
                  ? 'بدون إضاءة'
                  : 'No Backlight',
              build?.has_fingerprint ? (isAr ? 'بصمة إصبع' : 'Fingerprint') : null,
              build?.has_copilot_key ? 'Copilot Key' : null,
              build?.security_features?.length ? build.security_features.slice(0, 3).join(', ') : null,
            ])
            return (
              <span dir="auto" className="text-[12px]">
                {parts || '—'}
              </span>
            )
          },
        },
        {
          key: 'webcam-audio',
          label: isAr ? 'الكاميرا والصوتيات' : 'Webcam & Audio',
          compareKey: (detail) =>
            `${detail.audio_webcam?.webcam_resolution}-${detail.audio_webcam?.has_ir_camera}-${detail.audio_webcam?.has_privacy_shutter}-${detail.audio_webcam?.speaker_count}-${detail.audio_webcam?.audio_system}`,
          value: (detail) => {
            const audio = detail.audio_webcam
            const parts = joinParts([
              audio?.webcam_resolution ? `${audio.webcam_resolution} Cam` : null,
              audio?.has_ir_camera ? 'IR' : null,
              audio?.has_privacy_shutter ? (isAr ? 'غالق خصوصية' : 'Privacy Shutter') : null,
              audio?.speaker_count
                ? `${audio.speaker_count}x ${isAr ? 'سماعات' : 'Speakers'}${
                    audio.audio_system ? ` (${audio.audio_system})` : ''
                  }`
                : null,
            ])
            return (
              <span dir="auto" className="text-[12px]">
                {parts || '—'}
              </span>
            )
          },
        },
        {
          key: 'wireless',
          label: isAr ? 'الشبكة والاتصال' : 'Wireless & Ethernet',
          compareKey: (detail) =>
            `${detail.connectivity_os?.wifi}-${detail.connectivity_os?.bluetooth}-${detail.connectivity_os?.has_ethernet}-${detail.connectivity_os?.ethernet_speed}-${detail.connectivity_os?.has_card_reader}`,
          value: (detail) => {
            const conn = detail.connectivity_os
            const parts = joinParts([
              conn?.wifi,
              conn?.bluetooth,
              conn?.has_ethernet
                ? `RJ-45${conn.ethernet_speed ? ` (${conn.ethernet_speed})` : ''}`
                : isAr
                  ? 'بدون إيثرنت'
                  : 'No Ethernet',
              conn?.has_card_reader ? (isAr ? 'قارئ كروت SD' : 'Card Reader') : null,
            ])
            return (
              <span dir="auto" className="text-[12px]">
                {parts || '—'}
              </span>
            )
          },
        },
        {
          key: 'ports',
          label: isAr ? 'المنافذ' : 'Ports',
          compareKey: (detail) => (detail.connectivity_os?.ports || []).join('|'),
          value: (detail) => {
            const ports = detail.connectivity_os?.ports || []
            if (!ports.length) return '—'
            return (
              <ul dir="ltr" className="space-y-0.5 text-[12px]">
                {ports.map((port) => (
                  <li key={port}>{port}</li>
                ))}
              </ul>
            )
          },
        },
        {
          key: 'os',
          label: isAr ? 'نظام التشغيل' : 'Operating System',
          compareKey: (detail) => detail.connectivity_os?.operating_system ?? '',
          value: (detail) => val(detail.connectivity_os?.operating_system),
        },
      ],
    },
    {
      id: 'reviews',
      title: isAr ? 'المميزات والعيوب الفعلية' : 'Real-World Pros & Cons',
      icon: <Award className="w-4 h-4" strokeWidth={1.8} />,
      rows: [
        {
          key: 'review-evidence',
          label: isAr ? 'عدد المراجعات' : 'Review Evidence',
          numeric: (detail) => detail.reviews_evidence_count ?? null,
          winnerMax: true,
          compareKey: (detail) => detail.reviews_evidence_count ?? 0,
          value: (detail) => (
            <span className="tabular-nums">
              {detail.reviews_evidence_count
                ? `${detail.reviews_evidence_count} ${isAr ? 'مصادر' : 'sources'}`
                : '—'}
            </span>
          ),
        },
        {
          key: 'pros',
          label: isAr ? 'أبرز المميزات' : 'Top Strengths (+)',
          compareKey: (detail) =>
            ((isAr ? detail.pros_ar : detail.pros_en) || []).slice(0, 3).join('|'),
          value: (detail) => {
            const items = ((isAr ? detail.pros_ar : detail.pros_en) || []).slice(0, 3)
            if (!items.length) return '—'
            return (
              <ul className="space-y-1">
                {items.map((item, index) => (
                  <li key={`${index}-${item}`} dir="auto" className="flex gap-1.5">
                    <span className="flex-none font-semibold text-[var(--success)]">+</span>
                    <span>{item}</span>
                  </li>
                ))}
              </ul>
            )
          },
        },
        {
          key: 'cons',
          label: isAr ? 'أبرز العيوب والتنازلات' : 'Key Tradeoffs (-)',
          compareKey: (detail) =>
            ((isAr ? detail.cons_ar : detail.cons_en) || []).slice(0, 3).join('|'),
          value: (detail) => {
            const items = ((isAr ? detail.cons_ar : detail.cons_en) || []).slice(0, 3)
            if (!items.length) return '—'
            return (
              <ul className="space-y-1">
                {items.map((item, index) => (
                  <li key={`${index}-${item}`} dir="auto" className="flex gap-1.5">
                    <span className="flex-none font-semibold text-[var(--danger)]">-</span>
                    <span>{item}</span>
                  </li>
                ))}
              </ul>
            )
          },
        },
      ],
    },
  ]

  const columns = `minmax(94px, 118px) repeat(${entries.length}, minmax(168px, 1fr))`

  const rowDiffers = (row: CompareRow) => {
    if (details.length < 2) return true
    const values = details.map((detail) => {
      const value = row.compareKey
        ? row.compareKey(detail)
        : row.numeric
          ? row.numeric(detail)
          : null
      return value == null ? '' : String(value)
    })
    return new Set(values).size > 1
  }

  const sectionViews = sections.map((section) => ({
    section,
    rows: diffOnly ? section.rows.filter(rowDiffers) : section.rows,
  }))
  const anyVisibleRows = sectionViews.some((view) => view.rows.length > 0)

  const toggleSection = (id: SectionId) =>
    setExpandedSections((prev) => ({ ...prev, [id]: !prev[id] }))

  const allExpanded = (Object.keys(expandedSections) as SectionId[]).every(
    (id) => expandedSections[id],
  )
  const toggleAllSections = () => {
    const next = !allExpanded
    setExpandedSections({
      pricing: next,
      scores: next,
      silicon: next,
      display: next,
      power: next,
      connectivity: next,
      reviews: next,
    })
  }

  const renderRow = (row: CompareRow) => {
    const nums = details.map((detail) => (row.numeric ? row.numeric(detail) : null))
    const best = row.numeric ? winner(nums, row.winnerMax ?? true) : null
    return (
      <React.Fragment key={row.key}>
        <div className="cmp-sticky-cell bg-[var(--bg-raised)] px-2.5 py-2 text-[12px] font-semibold text-[var(--text-secondary)] flex items-center">
          {row.label}
        </div>
        {entries.map((entry, index) => {
          const detail = states[index]?.detail
          const numericValue = detail && row.numeric ? row.numeric(detail) : null
          const isBest = best != null && numericValue === best
          return (
            <div
              key={`${row.key}-${entry.id}`}
              className={`px-2.5 py-2 text-[12px] leading-[1.5] ${
                isBest
                  ? 'bg-[var(--success-dim)] text-[var(--success)] font-semibold shadow-[inset_0_0_0_1px_var(--success)]'
                  : 'bg-[var(--bg-surface)] text-[var(--text-primary)]'
              }`}
            >
              {detail ? row.value(detail) : '—'}
            </div>
          )
        })}
      </React.Fragment>
    )
  }

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
            <>
              <div className="flex flex-wrap items-center gap-2 mb-3">
                <button
                  type="button"
                  aria-pressed={diffOnly}
                  onClick={() => setDiffOnly((value) => !value)}
                  className={`min-h-[40px] px-3 rounded-lg border text-[12px] font-medium transition-colors ${
                    diffOnly
                      ? 'border-[var(--gold)] bg-[var(--gold-dim)] text-[var(--text-primary)]'
                      : 'border-[var(--border-subtle)] bg-[var(--bg-raised)] text-[var(--text-secondary)] hover:text-[var(--text-primary)]'
                  }`}
                >
                  {isAr ? 'الاختلافات فقط' : 'Differences only'}
                </button>
                <button
                  type="button"
                  onClick={toggleAllSections}
                  className="min-h-[40px] px-3 rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-raised)] text-[12px] font-medium text-[var(--text-secondary)] transition-colors hover:text-[var(--text-primary)]"
                >
                  {allExpanded
                    ? isAr
                      ? 'طي الكل'
                      : 'Collapse all'
                    : isAr
                      ? 'فتح الكل'
                      : 'Expand all'}
                </button>
                <span className="md:hidden text-[12px] text-[var(--text-muted)]">
                  {isAr ? 'اسحب الجدول جانباً لمشاهدة بقية الأجهزة ←' : 'Swipe the table sideways to see the other laptops →'}
                </span>
              </div>

              <div className="overflow-x-auto pb-2">
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
                          {state?.detail?.mpn && (
                            <div
                              dir="ltr"
                              className="font-mono text-[12px] text-[var(--text-muted)] truncate"
                            >
                              {state.detail.brand ? `${state.detail.brand} · ` : ''}
                              {state.detail.mpn}
                            </div>
                          )}
                          {state?.error && (
                            <p className="text-[12px] text-[var(--danger)] line-clamp-2">{state.error}</p>
                          )}
                        </div>
                      )
                    })}

                    {/* Sections */}
                    {sectionViews.map(({ section, rows: visibleRows }) => {
                      if (diffOnly && visibleRows.length === 0) return null
                      const open = expandedSections[section.id]
                      return (
                        <React.Fragment key={section.id}>
                          <button
                            type="button"
                            className="cmp-section-header"
                            aria-expanded={open}
                            onClick={() => toggleSection(section.id)}
                          >
                            <span className="flex items-center gap-2 min-w-0">
                              <span className="flex-none text-[var(--cyan)]">{section.icon}</span>
                              <span className="truncate">{section.title}</span>
                              <span className="flex-none rounded-md border border-[var(--border-subtle)] bg-[var(--bg-raised)] px-1.5 py-0.5 text-[12px] tabular-nums text-[var(--text-muted)]">
                                {visibleRows.length}
                              </span>
                            </span>
                            {open ? (
                              <ChevronUp className="w-4 h-4 flex-none text-[var(--text-muted)]" />
                            ) : (
                              <ChevronDown className="w-4 h-4 flex-none text-[var(--text-muted)]" />
                            )}
                          </button>
                          {open && visibleRows.map(renderRow)}
                        </React.Fragment>
                      )
                    })}

                    {diffOnly && !anyVisibleRows && (
                      <div
                        style={{ gridColumn: '1 / -1' }}
                        className="bg-[var(--bg-surface)] px-4 py-10 text-center text-[12px] text-[var(--text-muted)]"
                      >
                        {isAr
                          ? 'تتطابق جميع الأجهزة المقارنة في هذه المواصفات.'
                          : 'All compared laptops share identical values for these specs.'}
                      </div>
                    )}

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
                              className="btn btn-primary btn-sm w-full min-h-[40px]"
                            >
                              <span>
                                {isAr ? `اشترِ من ${detail.cheapest_store}` : `Buy at ${detail.cheapest_store}`}
                              </span>
                              <ExternalLink className="w-3 h-3" strokeWidth={2} />
                            </a>
                          ) : (
                            <span className="text-[12px] text-[var(--text-muted)]">—</span>
                          )}
                        </div>
                      )
                    })}
                  </div>
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
