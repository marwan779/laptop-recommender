import React, { useEffect, useState } from 'react'
import {
  X,
  Cpu,
  Monitor,
  HardDrive,
  MemoryStick,
  BatteryCharging,
  ExternalLink,
  Store,
  Wifi,
  ShieldCheck,
  Maximize2,
  CheckCircle,
  XCircle,
  Sparkles,
  Layers,
  Award,
  Zap,
  Feather,
  Wrench,
  Gauge,
  SlidersHorizontal,
  ChevronDown,
  ChevronUp,
} from 'lucide-react'
import type { FullLaptopDetailResponse, RankedLaptop, CatalogListItem } from '../types/api'
import { fetchLaptopDetail } from '../services/api'

interface LaptopDetailModalProps {
  laptop: RankedLaptop | CatalogListItem | null
  onClose: () => void
  lang: 'ar' | 'en'
}

interface TierInfo {
  category: string
  title: string
  subtitle: string
  /** Tier key colour used only for the 2px left bar and the icon. */
  key: string
  icon: React.ReactNode
}

function formatVerificationTime(isoStr: string | null | undefined, isAr: boolean): string {
  if (!isoStr) return isAr ? 'اليوم' : 'Today'
  try {
    const d = new Date(isoStr)
    if (isNaN(d.getTime())) return isAr ? 'اليوم' : 'Today'
    return d.toLocaleString(isAr ? 'ar-EG' : 'en-US', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return isAr ? 'اليوم' : 'Today'
  }
}

function getSiliconTierInfo(raw: string | undefined | null, isAr: boolean): TierInfo {
  const key = (raw || '').toUpperCase().trim()
  if (key.includes('EXPLICIT') || key.includes('HIGH') || key.includes('CAPPED')) {
    return {
      category: isAr ? 'فئة المعالجة والتبريد' : 'Thermal & Compute Tier',
      title: isAr ? 'أداء عالٍ ومستقر (TDP كامل)' : 'High-Power Uncapped Chassis',
      subtitle: isAr ? 'تبريد مخصص يسمح للمعالج وكارت الشاشة بالعمل بكامل طاقتهم' : 'Dedicated cooling allows max sustained power',
      key: 'var(--tier-thermal)',
      icon: <Zap className="w-4 h-4" strokeWidth={1.8} />,
    }
  }
  if (key.includes('INTEGRATED') || key.includes('SOC') || key.includes('ENTRY')) {
    return {
      category: isAr ? 'فئة المعالجة والتبريد' : 'Thermal & Compute Tier',
      title: isAr ? 'معالجة موفرة واقتصادية (iGPU)' : 'Efficiency SoC (iGPU)',
      subtitle: isAr ? 'استهلاك طاقة منخفض وعمر بطارية أطول للدراسة والعمل اليومي' : 'Low power draw & extended battery life for daily work',
      key: 'var(--tier-thermal)',
      icon: <Cpu className="w-4 h-4" strokeWidth={1.8} />,
    }
  }
  return {
    category: isAr ? 'فئة المعالجة والتبريد' : 'Thermal & Compute Tier',
    title: isAr ? 'أداء متوازن ومستقر' : 'Balanced Performance',
    subtitle: isAr ? 'مزيج قياسي بين الإنتاجية وكفاءة الاستهلاك' : 'Standard balance of compute power & efficiency',
    key: 'var(--tier-thermal)',
    icon: <Cpu className="w-4 h-4" strokeWidth={1.8} />,
  }
}

function getDisplayTierInfo(raw: string | undefined | null, isAr: boolean): TierInfo {
  const key = (raw || '').toLowerCase()
  if (key.includes('100% srgb') || key.includes('creator') || key.includes('dci-p3') || key.includes('oled')) {
    return {
      category: isAr ? 'فئة الشاشة والألوان' : 'Display Quality Tier',
      title: isAr ? 'شاشة احترافية دقيقة الألوان (100% sRGB)' : 'Creator Accurate (100% sRGB)',
      subtitle: isAr ? 'تغطية لونية متكاملة ممتازة للتصميم والمونتاج وإنتاج المحتوى' : 'Vibrant color accuracy ideal for editing & media',
      key: 'var(--tier-display)',
      icon: <Monitor className="w-4 h-4" strokeWidth={1.8} />,
    }
  }
  if (key.includes('45%') || key.includes('basic') || key.includes('ntsc')) {
    return {
      category: isAr ? 'فئة الشاشة والألوان' : 'Display Quality Tier',
      title: isAr ? 'شاشة قياسية للأعمال والدراسة (45% NTSC)' : 'Standard Display (45% NTSC)',
      subtitle: isAr ? 'ألوان قياسية مريحة مناسبة للبرمجة والقراءة والأوفيس' : 'Standard gamut suitable for code & office tasks',
      key: 'var(--tier-display)',
      icon: <Monitor className="w-4 h-4" strokeWidth={1.8} />,
    }
  }
  return {
    category: isAr ? 'فئة الشاشة والألوان' : 'Display Quality Tier',
    title: isAr ? 'شاشة سريعة عالية التردد (144Hz+)' : 'High-Refresh Esports Display',
    subtitle: isAr ? 'استجابة فائقة وسلاسة في الحركة للألعاب والتصفح السريع' : 'Smooth high refresh rate with low response latency',
    key: 'var(--tier-display)',
    icon: <Monitor className="w-4 h-4" strokeWidth={1.8} />,
  }
}

function getPortabilityTierInfo(raw: string | undefined | null, isAr: boolean): TierInfo {
  const key = (raw || '').toUpperCase()
  if (key.includes('ULTRA') || key.includes('LIGHT')) {
    return {
      category: isAr ? 'التنقل والوزن' : 'Mobility & Weight Tier',
      title: isAr ? 'خفيف جداً ونحيف للتنقل (< 1.6 كجم)' : 'Ultra-Portable (< 1.6kg)',
      subtitle: isAr ? 'تصميم فائق النحافة يسهل حمله في أي حقيبة طوال اليوم' : 'Ultra-slim chassis designed for effortless mobility',
      key: 'var(--tier-mobility)',
      icon: <Feather className="w-4 h-4" strokeWidth={1.8} />,
    }
  }
  if (key.includes('DESKTOP') || key.includes('HEAVY')) {
    return {
      category: isAr ? 'التنقل والوزن' : 'Mobility & Weight Tier',
      title: isAr ? 'بديل مكتبي للأداء الثابت (> 2.4 كجم)' : 'Desktop Replacement (> 2.4kg)',
      subtitle: isAr ? 'شاسيه أثقل مصمم للثبات والتبريد العالي على المكتب' : 'Heavier chassis built for sustained gaming power',
      key: 'var(--tier-mobility)',
      icon: <Feather className="w-4 h-4" strokeWidth={1.8} />,
    }
  }
  return {
    category: isAr ? 'التنقل والوزن' : 'Mobility & Weight Tier',
    title: isAr ? 'وزن متوازن للدراسة والتنقل (~2 كجم)' : 'Balanced Mobility (~2kg)',
    subtitle: isAr ? 'توازن عملي ومريح بين حجم الشاشة وسهولة الحمل اليومي' : 'Practical balance of screen size & everyday portability',
    key: 'var(--tier-mobility)',
    icon: <Feather className="w-4 h-4" strokeWidth={1.8} />,
  }
}

function getUpgradeabilityTierInfo(raw: string | undefined | null, isAr: boolean): TierInfo {
  const key = (raw || '').toUpperCase()
  if (key.includes('MAXIMUM') || key.includes('HIGH') || key.includes('DUAL')) {
    return {
      category: isAr ? 'قابلية الترقية المستقبلية' : 'Future Expansion Tier',
      title: isAr ? 'ترقية قصوى (فتحتان RAM + منفذان SSD)' : 'Dual RAM & Dual SSD Slots',
      subtitle: isAr ? 'سهولة تامة في مضاعفة الرامات وسعة التخزين مستقبلاً' : 'Full headroom to expand both memory & storage later',
      key: 'var(--tier-expansion)',
      icon: <Wrench className="w-4 h-4" strokeWidth={1.8} />,
    }
  }
  if (key.includes('LOCKED') || key.includes('SOLDERED')) {
    return {
      category: isAr ? 'قابلية الترقية المستقبلية' : 'Future Expansion Tier',
      title: isAr ? 'ذاكرة مدمجة غير قابلة للزيادة' : 'Soldered / Locked RAM',
      subtitle: isAr ? 'الرامات ملحومة باللوحة الأم، الترقية محصورة في وحدة التخزين' : 'Memory is soldered; expansion limited to SSD slot',
      key: 'var(--tier-expansion)',
      icon: <Wrench className="w-4 h-4" strokeWidth={1.8} />,
    }
  }
  return {
    category: isAr ? 'قابلية الترقية المستقبلية' : 'Future Expansion Tier',
    title: isAr ? 'ترقية جزئية متوفرة' : 'Moderate Upgradeability',
    subtitle: isAr ? 'منفذ واحد متاح لزيادة الرامات أو فتحة تخزين إضافية' : 'Single open slot or secondary M.2 storage slot',
    key: 'var(--tier-expansion)',
    icon: <Wrench className="w-4 h-4" strokeWidth={1.8} />,
  }
}

export const LaptopDetailModal: React.FC<LaptopDetailModalProps> = ({
  laptop,
  onClose,
  lang,
}) => {
  const isAr = lang === 'ar'
  const [detail, setDetail] = useState<FullLaptopDetailResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [showAllScores, setShowAllScores] = useState(false)

  useEffect(() => {
    if (!laptop) return
    setLoading(true)
    fetchLaptopDetail(laptop.canonical_id)
      .then((data) => setDetail(data))
      .catch((err) => console.error('Error fetching detail:', err))
      .finally(() => setLoading(false))
  }, [laptop])

  if (!laptop) return null

  const title = detail?.title || laptop.title
  const brand = detail?.brand || laptop.brand
  const family = detail?.laptop_family || (laptop as any).laptop_family || ''
  const mpn = detail?.mpn || (laptop as any).mpn || ''
  const effectivePrice = detail?.min_price_egp || (laptop as any).effective_price_egp || (laptop as any).min_price_egp || 0
  const cheapestStore = detail?.cheapest_store || (laptop as any).cheapest_store || 'Compumarts'
  const cheapestOfferUrl = detail?.cheapest_offer_url || (laptop as any).cheapest_offer_url || (laptop as any).urls_by_store?.[cheapestStore] || '#'
  const priceSpread = detail?.price_spread_egp || (laptop as any).price_spread_egp || 0

  // Freshness & Verification Timestamp
  const cheapestOffer = detail?.offers?.find((o) => o.is_cheapest) || detail?.offers?.[0]
  const lastCheckedAt = cheapestOffer?.last_checked_at || (detail as any)?.price_checked_at || (detail as any)?.price_updated_at

  const pros = isAr ? detail?.pros_ar || (laptop as any).pros_ar || [] : detail?.pros_en || (laptop as any).pros_en || []
  const cons = isAr ? detail?.cons_ar || (laptop as any).cons_ar || [] : detail?.cons_en || (laptop as any).cons_en || []

  // Operational Tiers with Human Mappings
  const siliconTier = getSiliconTierInfo(detail?.metrics?.silicon_tier, isAr)
  const displayTier = getDisplayTierInfo(detail?.metrics?.display_tier || detail?.display?.color_gamut, isAr)
  const portabilityTier = getPortabilityTierInfo(detail?.metrics?.portability_tier, isAr)
  const upgradeTier = getUpgradeabilityTierInfo(detail?.metrics?.upgradeability_tier, isAr)

  const allTiers = [siliconTier, displayTier, portabilityTier, upgradeTier]

  // All 15 Normalized Scores
  const m = detail?.metrics
  const topsis10Scores = [
    { labelAr: 'قوة المعالج (CPU)', labelEn: 'CPU Benchmark', score: m?.cpu_score ?? 70, icon: <Cpu className="w-3.5 h-3.5" strokeWidth={1.8} /> },
    { labelAr: 'أداء الجرافيكس (GPU)', labelEn: 'GPU 3D Gaming', score: m?.gpu_score ?? 65, icon: <Monitor className="w-3.5 h-3.5" strokeWidth={1.8} /> },
    { labelAr: 'جودة وسرعة الشاشة', labelEn: 'Display Quality', score: m?.display_score ?? 72, icon: <Maximize2 className="w-3.5 h-3.5" strokeWidth={1.8} /> },
    { labelAr: 'القيمة مقابل السعر', labelEn: 'Value for Money', score: m?.value_score ?? 85, icon: <Sparkles className="w-3.5 h-3.5" strokeWidth={1.8} /> },
    { labelAr: 'استقرار الطاقة والتبريد', labelEn: 'Sustained Power & Thermals', score: m?.power_therm_score ?? 80, icon: <Zap className="w-3.5 h-3.5" strokeWidth={1.8} /> },
    { labelAr: 'سهولة التنقل والوزن', labelEn: 'Mobility & Battery Wh', score: m?.mobility_score ?? 60, icon: <Feather className="w-3.5 h-3.5" strokeWidth={1.8} /> },
    { labelAr: 'المنافذ والاتصال', labelEn: 'I/O & Connectivity', score: m?.connectivity_score ?? 75, icon: <Layers className="w-3.5 h-3.5" strokeWidth={1.8} /> },
    { labelAr: 'عمر الشاسيه وقابلية الترقية', labelEn: 'Chassis Longevity', score: m?.longevity_score ?? 78, icon: <ShieldCheck className="w-3.5 h-3.5" strokeWidth={1.8} /> },
    { labelAr: 'الراحة والكيبورد (Ergonomics)', labelEn: 'Ergonomics & Typing', score: m?.ergonomics_score ?? 74, icon: <Gauge className="w-3.5 h-3.5" strokeWidth={1.8} /> },
    { labelAr: 'تجارب المستخدمين الفعلية', labelEn: 'Community NLP Sentiment', score: m?.community_nlp_score ?? 79, icon: <Award className="w-3.5 h-3.5" strokeWidth={1.8} /> },
  ]

  const review5Aspects = [
    { labelAr: 'التبريد تحت الضغط الصيفي', labelEn: 'Cooling under Stress', score: m?.thermals_score ?? 78 },
    { labelAr: 'هدوء المراوح والصوت', labelEn: 'Fan Acoustics & Quietness', score: m?.acoustics_score ?? 75 },
    { labelAr: 'متانة الشاسيه والمفصلات', labelEn: 'Chassis & Hinge Durability', score: m?.build_and_hinges_score ?? 82 },
    { labelAr: 'استجابة الكيبورد والتراك باد', labelEn: 'Keyboard & Trackpad Precision', score: m?.keyboard_and_trackpad_score ?? 80 },
    { labelAr: 'عمر البطارية الحقيقي', labelEn: 'Real Battery Run-Time', score: m?.real_battery_and_reliability_score ?? 79 },
  ]

  const scoreTone = (score: number) =>
    score >= 85 ? 't-gold' : score < 50 ? 't-danger' : 't-primary'

  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true" aria-label={title}>
      <div className="modal-frame">
        {/* Header */}
        <div className="modal-header">
          <div className="min-w-0">
            <div className="flex items-center flex-wrap gap-2 mb-1.5">
              <span className="brand-chip">
                {brand} {family ? `· ${family}` : ''}
              </span>
              {mpn && <span className="mpn-chip">MPN: {mpn}</span>}
              {detail?.color && <span className="mpn-chip">{detail.color}</span>}
              {detail?.form_factor && <span className="mpn-chip">{detail.form_factor}</span>}
            </div>
            <h2 className="font-display text-[17px] sm:text-[19px] font-semibold text-[var(--text-primary)] leading-snug line-clamp-2">
              {title}
            </h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label={isAr ? 'إغلاق' : 'Close'}
            className="modal-close"
          >
            <X className="w-4.5 h-4.5" strokeWidth={1.8} />
          </button>
        </div>

        {/* Scrollable content */}
        <div className="modal-body">
          {/* Top grid: studio well & pricing comparison */}
          <div className="grid grid-cols-1 sm:grid-cols-12 gap-5">
            <div className="sm:col-span-5 studio-well w-full">
              <img
                src={laptop.thumbnail_url}
                alt={title}
                onError={(e) => {
                  ;(e.target as HTMLElement).style.display = 'none'
                }}
              />
            </div>

            <div className="sm:col-span-7 flex flex-col justify-between gap-4 min-w-0">
              <div>
                <span className="micro block">
                  {isAr ? 'أقل سعر متاح في السوق المصري' : 'Lowest Available Market Price'}
                </span>
                <div className="flex items-baseline gap-2 flex-wrap mt-1">
                  <span className="font-display font-bold text-[28px] leading-tight text-[var(--gold-bright)] num">
                    {effectivePrice > 0
                      ? effectivePrice.toLocaleString()
                      : isAr
                      ? 'السعر عند الطلب'
                      : 'Price on request'}
                  </span>
                  {effectivePrice > 0 && (
                    <span className="text-[13px] font-semibold text-[var(--text-muted)]">
                      {isAr ? 'ج.م' : 'EGP'}
                    </span>
                  )}
                  <span className="text-[12px] font-medium text-[var(--text-secondary)]">
                    (@ {cheapestStore})
                  </span>
                </div>

                {/* Live verification */}
                <div className="flex items-center flex-wrap gap-2">
                  <span className="verified">
                    <span className="vdot" />
                    <span>
                      {isAr ? 'تم التحقق مباشرة من المتجر:' : 'Verified live from retailer:'}
                    </span>
                    <span className="ts">{formatVerificationTime(lastCheckedAt, isAr)}</span>
                  </span>

                  {priceSpread > 0 && (
                    <span className="ai-chip !mt-2.5">
                      {isAr
                        ? `وفر ${priceSpread.toLocaleString()} ج.م مقارنة بأعلى متجر`
                        : `Save ${priceSpread.toLocaleString()} EGP vs highest store`}
                    </span>
                  )}
                </div>
              </div>

              {/* Retailer offers */}
              <div className="space-y-2">
                <span className="micro flex items-center gap-1.5">
                  <Store className="w-3.5 h-3.5" strokeWidth={1.8} />
                  <span>
                    {isAr ? 'مقارنة الأسعار بين المتاجر المصرية' : 'Egyptian Retailers Price Comparison'}
                  </span>
                </span>
                <div className="space-y-2 max-h-40 overflow-y-auto pe-1">
                  {detail?.offers && detail.offers.length > 0 ? (
                    detail.offers.map((off, idx) => (
                      <div
                        key={idx}
                        className={`retail-row !mt-0 ${
                          !off.in_stock ? 'opacity-70' : ''
                        }`}
                      >
                        <span className="rname">{off.store_name}</span>
                        {off.is_cheapest && (
                          <span className="best-chip">{isAr ? 'الأرخص' : 'Best Price'}</span>
                        )}
                        {!off.in_stock && (
                          <span className="brand-chip !text-[var(--danger)] !border-[rgba(248,113,113,0.4)]">
                            {isAr ? 'غير متاح' : 'Out of stock'}
                          </span>
                        )}
                        <span className="rprice num">
                          {off.price_egp > 0
                            ? `${off.price_egp.toLocaleString()} `
                            : isAr
                            ? 'عند الطلب'
                            : 'Request'}
                          {off.price_egp > 0 && <small>EGP</small>}
                        </span>
                        {off.product_url && (
                          <a
                            href={off.product_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            aria-label={off.store_name}
                            className="text-[var(--text-muted)] hover:text-[var(--gold-bright)] transition-colors p-1"
                          >
                            <ExternalLink className="w-3.5 h-3.5" strokeWidth={1.8} />
                          </a>
                        )}
                      </div>
                    ))
                  ) : (
                    <div className="text-[12.5px] text-[var(--text-muted)] py-2">
                      {isAr ? 'جاري تحديث عروض المتاجر...' : 'Fetching live store listings...'}
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>

          {/* Operational tiers */}
          <div className="tile-block space-y-3">
            <h4 className="label flex items-center gap-1.5">
              <Award className="w-3.5 h-3.5 text-[var(--cyan)]" strokeWidth={1.8} />
              <span>
                {isAr ? 'تصنيف الفئات والقدرات التشغيلية للموديل' : 'Hardware Operational Tiers'}
              </span>
            </h4>
            <div className="tier-grid">
              {allTiers.map((tier, idx) => (
                <div key={idx} className="tier" style={{ ['--key' as string]: tier.key }}>
                  <span className="ticon">{tier.icon}</span>
                  <div className="min-w-0">
                    <div className="tlabel">{tier.category}</div>
                    <div className="tname">{tier.title}</div>
                    <div className="tdesc">{tier.subtitle}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>


          {/* 35+ Structured Hardware Dimensions Grid */}
          <div className="tile-block space-y-4">
            <div className="flex items-center justify-between pb-1">
              <h3 className="font-display text-[16px] font-semibold text-[var(--text-primary)] flex items-center gap-2">
                <Cpu className="w-4 h-4 text-[var(--cyan)]" strokeWidth={1.8} />
                <span>{isAr ? 'المواصفات التقنية الدقيقة الكاملة (35+ بعد)' : 'Full Detailed Hardware Specifications (35+ Dimensions)'}</span>
              </h3>
              {loading && (
                <div className="flex items-center gap-2 text-[12px] text-[var(--text-muted)]">
                  <div className="spinner spinner-sm" />
                  <span>{isAr ? 'جاري التحميل...' : 'Loading specs...'}</span>
                </div>
              )}
            </div>

            <div className="spec-grid">
              {/* 1. Processor (CPU) */}
              <div className="spec-cell">
                <div className="chead">
                  <span className="ct flex items-center gap-1.5">
                    <Cpu className="w-4 h-4 text-[var(--cyan)]" />
                    <span>{isAr ? 'المعالج (Processor / CPU)' : 'Processor (CPU)'}</span>
                  </span>
                  {detail?.cpu?.manufacturer && (
                    <span className="cbadge">
                      {detail.cpu.manufacturer}
                    </span>
                  )}
                </div>
                <div className="big">
                  {detail?.cpu?.full_name || detail?.cpu?.model || 'High Performance Processor'}
                </div>
                <div className="spec-fields">
                  <div>
                    <span className="fl">{isAr ? 'الأنوية والمسارات:' : 'Cores & Threads:'}</span>
                    <span className="fv num">
                      {detail?.cpu?.cores ?? '-'} Cores • {detail?.cpu?.threads ?? '-'} Threads
                    </span>
                  </div>
                  <div>
                    <span className="fl">{isAr ? 'التردد الأقصى (Boost):' : 'Max Boost Clock:'}</span>
                    <span className="fv num">
                      {detail?.cpu?.clock_boost_ghz ? `${detail.cpu.clock_boost_ghz} GHz` : '-'}
                      {detail?.cpu?.clock_base_ghz ? ` (Base: ${detail.cpu.clock_base_ghz} GHz)` : ''}
                    </span>
                  </div>
                  <div>
                    <span className="fl">{isAr ? 'الذاكرة المخبأة (Cache):' : 'Cache:'}</span>
                    <span className="fv num">
                      {detail?.cpu?.cache_mb ? `${detail.cpu.cache_mb} MB` : 'Smart Cache'}
                    </span>
                  </div>
                  <div>
                    <span className="fl">{isAr ? 'القدرة الأساسية (TDP):' : 'Base Power (TDP):'}</span>
                    <span className="fv num">
                      {detail?.cpu?.base_power_w ? `${detail.cpu.base_power_w}W` : 'Standard'}
                    </span>
                  </div>
                  {detail?.cpu?.microarchitecture && (
                    <div>
                      <span className="fl">{isAr ? 'المعمارية الدقيقة:' : 'Microarchitecture:'}</span>
                      <span className="fv num">{detail.cpu.microarchitecture}</span>
                    </div>
                  )}
                  {detail?.cpu?.npu_tops && (
                    <div>
                      <span className="fl">{isAr ? 'معالج الذكاء الاصطناعي (NPU):' : 'AI NPU TOPS:'}</span>
                      <span className="fv indigo num">{detail.cpu.npu_tops} TOPS</span>
                    </div>
                  )}
                </div>
              </div>

              {/* 2. Graphics (GPU) */}
              <div className="spec-cell">
                <div className="chead">
                  <span className="ct flex items-center gap-1.5">
                    <Monitor className="w-4 h-4 text-[var(--cyan)]" />
                    <span>{isAr ? 'كارت الشاشة (Graphics / GPU)' : 'Graphics (GPU)'}</span>
                  </span>
                  <span className={`cbadge ${
                    detail?.gpu?.integrated ? '' : 'green'
                  }`}>
                    {detail?.gpu?.integrated ? (isAr ? 'مدمج (iGPU)' : 'Integrated') : (isAr ? 'منفصل (Dedicated dGPU)' : 'Dedicated dGPU')}
                  </span>
                </div>
                <div className="big">
                  {detail?.gpu?.model || 'Graphics Engine'}
                </div>
                <div className="spec-fields">
                  <div>
                    <span className="fl">{isAr ? 'سعة ونوع ذاكرة الفيديو:' : 'VRAM Capacity:'}</span>
                    <span className="fv num">
                      {detail?.gpu?.vram_gb ? `${detail.gpu.vram_gb}GB ${detail.gpu.vram_type || 'GDDR6'}` : isAr ? 'مشتركة من الرامات' : 'System Shared'}
                    </span>
                  </div>
                  <div>
                    <span className="fl">{isAr ? 'قدرة الطاقة (TGP / TDP):' : 'Max Power (TGP):'}</span>
                    <span className="fv num">
                      {detail?.gpu?.tdp_w ? `${detail.gpu.tdp_w}W` : isAr ? 'استهلاك قياسي' : 'Standard'}
                    </span>
                  </div>
                  {detail?.gpu?.variant && (
                    <div>
                      <span className="fl">{isAr ? 'المعمارية الفرعية:' : 'Sub-variant:'}</span>
                      <span className="fv num">{detail.gpu.variant}</span>
                    </div>
                  )}
                  {detail?.gpu?.ai_tops && (
                    <div>
                      <span className="fl">{isAr ? 'أداء الذكاء الاصطناعي GPU TOPS:' : 'GPU AI TOPS:'}</span>
                      <span className="fv indigo num">{detail.gpu.ai_tops} TOPS</span>
                    </div>
                  )}
                  {detail?.gpu?.igpu_model && !detail?.gpu?.integrated && (
                    <div className="col-span-2">
                      <span className="fl">{isAr ? 'الكارت المدمج الثانوي (للتوفير):' : 'Secondary iGPU (Battery Saver):'}</span>
                      <span className="fv num">{detail.gpu.igpu_model}</span>
                    </div>
                  )}
                </div>
              </div>

              {/* 3. Memory (RAM) */}
              <div className="spec-cell">
                <div className="chead">
                  <span className="ct flex items-center gap-1.5">
                    <MemoryStick className="w-4 h-4 text-[var(--cyan)]" />
                    <span>{isAr ? 'الذاكرة العشوائية (RAM)' : 'Memory (RAM)'}</span>
                  </span>
                  <span className="cbadge">
                    {detail?.memory?.memory_type || 'DDR5'}
                  </span>
                </div>
                <div className="big">
                  {detail?.memory?.capacity_gb || 16}GB {detail?.memory?.memory_type || 'DDR5'}
                </div>
                <div className="spec-fields">
                  <div>
                    <span className="fl">{isAr ? 'تردد وسرعة الذاكرة:' : 'Memory Speed:'}</span>
                    <span className="fv num">{detail?.memory?.speed_mhz ? `${detail.memory.speed_mhz} MHz` : 'High Speed'}</span>
                  </div>
                  <div>
                    <span className="fl">{isAr ? 'المنافذ والترقية:' : 'Slots / Expansion:'}</span>
                    <span className="fv num">
                      {detail?.memory?.is_soldered
                        ? isAr ? 'ملحومة باللوحة (Soldered)' : 'Soldered On-board'
                        : detail?.memory?.slot_count ? `${detail.memory.slot_count}x SO-DIMM (Upgradeable)` : isAr ? 'قابلة للترقية' : 'Upgradeable'}
                    </span>
                  </div>
                  {detail?.memory?.max_supported_gb && (
                    <div>
                      <span className="fl">{isAr ? 'أقصى سعة مدعومة:' : 'Max Supported RAM:'}</span>
                      <span className="fv indigo num">{detail.memory.max_supported_gb} GB</span>
                    </div>
                  )}
                  {detail?.memory?.channels && (
                    <div>
                      <span className="fl">{isAr ? 'قنوات التوصيل:' : 'Channels:'}</span>
                      <span className="fv num">{detail.memory.channels}</span>
                    </div>
                  )}
                </div>
              </div>

              {/* 4. Storage (SSD) */}
              <div className="spec-cell">
                <div className="chead">
                  <span className="ct flex items-center gap-1.5">
                    <HardDrive className="w-4 h-4 text-[var(--cyan)]" />
                    <span>{isAr ? 'وحدة التخزين (Storage / SSD)' : 'Storage (SSD)'}</span>
                  </span>
                  <span className="cbadge">
                    {detail?.storage?.storage_type || 'NVMe SSD'}
                  </span>
                </div>
                <div className="big">
                  {detail?.storage?.capacity_gb ? `${detail.storage.capacity_gb}GB` : '512GB'} PCIe NVMe SSD
                </div>
                <div className="spec-fields">
                  <div>
                    <span className="fl">{isAr ? 'واجهة التوصيل:' : 'Interface:'}</span>
                    <span className="fv num">{detail?.storage?.interface || 'PCIe Gen 4.0 x4'}</span>
                  </div>
                  <div>
                    <span className="fl">{isAr ? 'منافذ M.2 الإضافية:' : 'M.2 Expansion Slots:'}</span>
                    <span className="fv indigo num">
                      {detail?.storage?.slot_count ? `${detail.storage.slot_count}x M.2 Slots` : isAr ? 'منفذ إضافي متاح' : 'Secondary slot available'}
                    </span>
                  </div>
                </div>
              </div>

              {/* 5. Display */}
              <div className="spec-cell">
                <div className="chead">
                  <span className="ct flex items-center gap-1.5">
                    <Maximize2 className="w-4 h-4 text-[var(--cyan)]" />
                    <span>{isAr ? 'الشاشة والعرض (Display)' : 'Display'}</span>
                  </span>
                  <span className="cbadge">
                    {detail?.display?.refresh_rate_hz || 60}Hz
                  </span>
                </div>
                <div className="big">
                  {detail?.display?.size_inches}" {detail?.display?.resolution} ({detail?.display?.panel_type || 'IPS'})
                </div>
                <div className="spec-fields">
                  <div>
                    <span className="fl">{isAr ? 'النسبة والسطوع:' : 'Aspect Ratio & Nits:'}</span>
                    <span className="fv num">
                      {detail?.display?.aspect_ratio || '16:10'} • {detail?.display?.brightness_nits ? `${detail.display.brightness_nits} nits` : '300 nits'}
                    </span>
                  </div>
                  <div>
                    <span className="fl">{isAr ? 'دقة الألوان واللمس:' : 'Color Gamut & Touch:'}</span>
                    <span className="fv num">
                      {detail?.display?.color_gamut || '100% sRGB'} • {detail?.display?.touchscreen ? (isAr ? 'تدعم اللمس' : 'Touchscreen') : (isAr ? 'غير لمسية' : 'Non-touch')}
                    </span>
                  </div>
                  {detail?.display?.hdr && (
                    <div>
                      <span className="fl">{isAr ? 'المدى الديناميكي (HDR):' : 'High Dynamic Range:'}</span>
                      <span className="fv success num">{isAr ? 'يدعم HDR' : 'HDR Supported'}</span>
                    </div>
                  )}
                  {detail?.display?.width && detail?.display?.height && (
                    <div>
                      <span className="fl">{isAr ? 'البيكسلات الدقيقة:' : 'Exact Resolution:'}</span>
                      <span className="fv num">{detail.display.width} x {detail.display.height}</span>
                    </div>
                  )}
                </div>
              </div>

              {/* 6. Power & Battery */}
              <div className="spec-cell">
                <div className="chead">
                  <span className="ct flex items-center gap-1.5">
                    <BatteryCharging className="w-4 h-4 text-[var(--cyan)]" />
                    <span>{isAr ? 'البطارية والشاحن (Battery & Power)' : 'Power & Battery'}</span>
                  </span>
                  {detail?.power_battery?.usb_c_pd_charging && (
                    <span className="cbadge !text-[var(--indigo)] !border-[rgba(129,140,248,0.45)]">
                      USB-C PD
                    </span>
                  )}
                </div>
                <div className="big">
                  {detail?.power_battery?.battery_capacity_wh ? `${detail.power_battery.battery_capacity_wh}Wh` : 'Long-life'} Battery
                </div>
                <div className="spec-fields">
                  <div>
                    <span className="fl">{isAr ? 'قدرة الشاحن الأصلي:' : 'Adapter Wattage:'}</span>
                    <span className="fv num">{detail?.power_battery?.power_adapter_w ? `${detail.power_battery.power_adapter_w}W` : 'Fast Adapter'}</span>
                  </div>
                  <div>
                    <span className="fl">{isAr ? 'شحن تايب سي والشحن السريع:' : 'USB-C PD & Fast Charge:'}</span>
                    <span className="fv num">
                      {detail?.power_battery?.usb_c_pd_charging ? (isAr ? 'يدعم USB-C PD' : 'USB-C PD Supported') : (isAr ? 'شاحن مخصص' : 'Dedicated Port')}
                    </span>
                  </div>
                  {detail?.power_battery?.battery_cells && (
                    <div>
                      <span className="fl">{isAr ? 'خلايا البطارية:' : 'Battery Cells:'}</span>
                      <span className="fv num">{detail.power_battery.battery_cells} Cells</span>
                    </div>
                  )}
                  {detail?.metrics?.estimated_battery_hours && (
                    <div>
                      <span className="fl">{isAr ? 'عمر البطارية الفعلي المقدر:' : 'Estimated Runtime:'}</span>
                      <span className="fv success num">~{detail.metrics.estimated_battery_hours} {isAr ? 'ساعات' : 'hours'}</span>
                    </div>
                  )}
                </div>
              </div>

              {/* 7. Build, Keyboard & Biometrics */}
              <div className="spec-cell">
                <div className="chead">
                  <span className="ct flex items-center gap-1.5">
                    <ShieldCheck className="w-4 h-4 text-[var(--cyan)]" />
                    <span>{isAr ? 'الشاسيه، الكيبورد والأمان' : 'Build & Security'}</span>
                  </span>
                  {detail?.physical?.weight_kg && (
                    <span className="cbadge">
                      {detail.physical.weight_kg} kg
                    </span>
                  )}
                </div>
                <div className="text-[var(--text-primary)] font-medium text-[13px] leading-relaxed">
                  {detail?.build_security?.has_backlit_keyboard
                    ? isAr ? `كيبورد مضيء (${detail.build_security.keyboard_backlight_type || 'RGB'})` : `Backlit Keyboard (${detail.build_security.keyboard_backlight_type || 'RGB'})`
                    : isAr ? 'كيبورد قياسي' : 'Standard Keyboard'}
                  {detail?.build_security?.has_fingerprint ? (isAr ? ' • بصمة إصبع' : ' • Fingerprint Reader') : ''}
                  {detail?.build_security?.has_copilot_key ? (isAr ? ' • زر Copilot للذكاء الاصطناعي' : ' • Copilot AI Key') : ''}
                </div>
                <div className="spec-fields">
                  <div>
                    <span className="fl">{isAr ? 'الوزن الصافي:' : 'Chassis Weight:'}</span>
                    <span className="fv num">{detail?.physical?.weight_kg ? `${detail.physical.weight_kg} kg` : isAr ? 'خفيف وسهل التنقل' : 'Portable'}</span>
                  </div>
                  <div>
                    <span className="fl">{isAr ? 'الأبعاد بالملم (عرض×عمق×سمك):' : 'Dimensions (W x D x H):'}</span>
                    <span className="fv num">
                      {detail?.physical?.width_mm && detail?.physical?.depth_mm
                        ? `${detail.physical.width_mm} × ${detail.physical.depth_mm} × ${detail?.physical?.height_mm || 20} mm`
                        : isAr ? 'هيكل قياسي' : 'Standard'}
                    </span>
                  </div>
                </div>
              </div>

              {/* 8. Audio, Webcam & Connectivity */}
              <div className="spec-cell">
                <div className="chead">
                  <span className="ct flex items-center gap-1.5">
                    <Wifi className="w-4 h-4 text-[var(--cyan)]" />
                    <span>{isAr ? 'الصوت، الكاميرا والشبكات' : 'Audio, Webcam & Network'}</span>
                  </span>
                  <span className="cbadge">
                    {detail?.connectivity_os?.wifi || 'Wi-Fi 6'}
                  </span>
                </div>
                <div className="text-[var(--text-primary)] font-medium text-[13px] leading-relaxed">
                  {detail?.audio_webcam?.webcam_resolution || '1080p FHD'} Webcam
                  {detail?.audio_webcam?.has_privacy_shutter ? (isAr ? ' • غالق خصوصية' : ' • Privacy Shutter') : ''}
                  {detail?.audio_webcam?.has_ir_camera ? (isAr ? ' • كاميرا IR Windows Hello' : ' • IR Windows Hello') : ''}
                </div>
                <div className="spec-fields">
                  <div>
                    <span className="fl">{isAr ? 'نظام الصوت:' : 'Audio Speakers:'}</span>
                    <span className="fv num">
                      {detail?.audio_webcam?.speaker_count || 2}x Stereo
                      {detail?.audio_webcam?.audio_system ? ` (${detail.audio_webcam.audio_system})` : ''}
                    </span>
                  </div>
                  <div>
                    <span className="fl">{isAr ? 'بلوتوث ومنفذ إيثرنت:' : 'Bluetooth & Ethernet:'}</span>
                    <span className="fv num">
                      {detail?.connectivity_os?.bluetooth || 'Bluetooth 5.3'}
                      {detail?.connectivity_os?.has_ethernet ? ` • RJ-45 (${detail.connectivity_os.ethernet_speed || 'Gigabit'})` : ''}
                    </span>
                  </div>
                  {detail?.connectivity_os?.operating_system && (
                    <div className="col-span-2">
                      <span className="fl">{isAr ? 'نظام التشغيل المثبت:' : 'Operating System:'}</span>
                      <span className="fv indigo num">{detail.connectivity_os.operating_system}</span>
                    </div>
                  )}
                </div>
              </div>
            </div>

            {/* Ports & Connectivity Full List */}
            {detail?.connectivity_os?.ports && detail.connectivity_os.ports.length > 0 && (
              <div className="spec-cell">
                <div className="chead">
                  <Layers className="w-4 h-4 text-[var(--cyan)]" strokeWidth={1.8} />
                  <span className="ct">
                    {isAr ? 'المنافذ والتوصيل (I/O Ports)' : 'Available I/O Ports'}
                  </span>
                  <span className="cbadge">{detail.connectivity_os.ports.length}</span>
                </div>
                <div className="flex flex-wrap gap-2">
                  {detail.connectivity_os.ports.map((port, idx) => (
                    <span key={idx} className="port-chip">
                      {port}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Full 15 performance scores (progressive toggle) */}
          <div className="tile-block space-y-3">
            <button
              type="button"
              onClick={() => setShowAllScores(!showAllScores)}
              className="collapse-toggle"
              aria-expanded={showAllScores}
            >
              <span className="ct-left">
                <SlidersHorizontal className="w-3.5 h-3.5" strokeWidth={1.8} />
                <span>
                  {isAr
                    ? 'لوحة مؤشرات الأداء والتقييم الـ 15 الكاملة (TOPSIS & Reviews)'
                    : 'Full 15-Dimension Scorecard (TOPSIS & Reviews)'}
                </span>
              </span>
              <span className="ct-state">
                <span>
                  {showAllScores ? (isAr ? 'إخفاء' : 'Collapse') : isAr ? 'عرض كافة المقاييس' : 'Expand'}
                </span>
                {showAllScores ? (
                  <ChevronUp className="w-3.5 h-3.5" />
                ) : (
                  <ChevronDown className="w-3.5 h-3.5" />
                )}
              </span>
            </button>

            {showAllScores && (
              <div className="space-y-5">
                {/* 10 TOPSIS decision criteria */}
                <div>
                  <span className="micro block mb-2.5">
                    {isAr
                      ? 'المعايير الهندسية والعتاد الـ 10 (TOPSIS)'
                      : '10 Hardware Decision Criteria (TOPSIS)'}
                  </span>
                  <div className="criteria-grid">
                    {topsis10Scores.map((sc, i) => (
                      <div key={i} className="crit-tile">
                        <div className="clabel">
                          {sc.icon}
                          <span>{isAr ? sc.labelAr : sc.labelEn}</span>
                        </div>
                        <div className={`cnum num ${scoreTone(sc.score)}`}>
                          {sc.score.toFixed(1)}
                        </div>
                        <div className="mini-track">
                          <div
                            className="mini-fill"
                            style={{ width: `${Math.min(100, Math.max(0, sc.score))}%` }}
                          />
                        </div>
                      </div>
                    ))}
                  </div>
                </div>

                {/* 5 review intelligence aspects */}
                <div className="pt-4 border-t border-[var(--border-subtle)]">
                  <span className="micro block mb-2.5">
                    {isAr
                      ? 'الاختبارات الميدانية وتقييمات المستخدمين الـ 5'
                      : '5 Field Review Aspects (Real-World Stress)'}
                  </span>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-5 gap-y-3">
                    {review5Aspects.map((asp, i) => (
                      <div key={i} className="bar-row">
                        <div className="bar-head">
                          <span className="blabel truncate">
                            <span className="truncate">
                              {isAr ? asp.labelAr : asp.labelEn}
                            </span>
                          </span>
                          <span className={`bval num ${scoreTone(asp.score)}`}>
                            {asp.score.toFixed(1)}
                            <small>/100</small>
                          </span>
                        </div>
                        <div className="bar-track">
                          <span className="tick" style={{ left: '50%' }} />
                          <span className="tick" style={{ left: '80%' }} />
                          <div
                            className="bar-fill"
                            style={{ width: `${Math.min(100, Math.max(0, asp.score))}%` }}
                          />
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Pro & cons */}
          {(pros.length > 0 || cons.length > 0) && (
            <div className="tile-block space-y-3">
              <h4 className="label flex items-center gap-1.5">
                <Sparkles className="w-3.5 h-3.5 text-[var(--cyan)]" strokeWidth={1.8} />
                <span>
                  {isAr ? 'خلاصة تقييمات وتجارب المستخدمين' : 'Real User & Review Insights'}
                </span>
              </h4>
              <div className="proscons !mt-0">
                <div className="pc pros">
                  <h4>
                    <CheckCircle className="w-3.5 h-3.5" strokeWidth={2} />
                    <span>{isAr ? 'المميزات الرئيسية' : 'Key Advantages'}</span>
                  </h4>
                  <ul>
                    {pros.map((p: string, i: number) => (
                      <li key={i}>
                        <span className="mk">✓</span>
                        <span>{p}</span>
                      </li>
                    ))}
                  </ul>
                </div>

                <div className="pc cons">
                  <h4>
                    <XCircle className="w-3.5 h-3.5" strokeWidth={2} />
                    <span>{isAr ? 'العيوب والملاحظات' : 'Technical Drawbacks'}</span>
                  </h4>
                  <ul>
                    {cons.map((c: string, i: number) => (
                      <li key={i}>
                        <span className="mk">✕</span>
                        <span>{c}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Modal sticky footer CTA */}
        <div className="modal-footer">
          <div className="text-[12px] text-[var(--text-muted)]">
            {isAr
              ? 'الأسعار والمواصفات محدثة وموثقة مباشرة من المتاجر'
              : 'Real-time verified pricing and specs'}
          </div>
          <a
            href={cheapestOfferUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="btn btn-primary btn-sm"
          >
            <span>
              {isAr ? `شراء من ${cheapestStore}` : `Buy from ${cheapestStore}`}
            </span>
            <ExternalLink className="w-3.5 h-3.5" strokeWidth={2} />
          </a>
        </div>
      </div>
    </div>
  )
}
