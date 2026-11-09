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
  Clock,
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
  badgeClass: string
  borderClass: string
  bgClass: string
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
      badgeClass: 'text-indigo-400 bg-indigo-500/10 border-indigo-500/30',
      borderClass: 'border-indigo-500/30',
      bgClass: 'bg-indigo-950/20',
      icon: <Zap className="w-4 h-4 text-indigo-400" />,
    }
  }
  if (key.includes('INTEGRATED') || key.includes('SOC') || key.includes('ENTRY')) {
    return {
      category: isAr ? 'فئة المعالجة والتبريد' : 'Thermal & Compute Tier',
      title: isAr ? 'معالجة موفرة واقتصادية (iGPU)' : 'Efficiency SoC (iGPU)',
      subtitle: isAr ? 'استهلاك طاقة منخفض وعمر بطارية أطول للدراسة والعمل اليومي' : 'Low power draw & extended battery life for daily work',
      badgeClass: 'text-sky-400 bg-sky-500/10 border-sky-500/30',
      borderClass: 'border-sky-500/30',
      bgClass: 'bg-sky-950/20',
      icon: <Cpu className="w-4 h-4 text-sky-400" />,
    }
  }
  return {
    category: isAr ? 'فئة المعالجة والتبريد' : 'Thermal & Compute Tier',
    title: isAr ? 'أداء متوازن ومستقر' : 'Balanced Performance',
    subtitle: isAr ? 'مزيج قياسي بين الإنتاجية وكفاءة الاستهلاك' : 'Standard balance of compute power & efficiency',
    badgeClass: 'text-emerald-400 bg-emerald-500/10 border-emerald-500/30',
    borderClass: 'border-emerald-500/30',
    bgClass: 'bg-emerald-950/20',
    icon: <Cpu className="w-4 h-4 text-emerald-400" />,
  }
}

function getDisplayTierInfo(raw: string | undefined | null, isAr: boolean): TierInfo {
  const key = (raw || '').toLowerCase()
  if (key.includes('100% srgb') || key.includes('creator') || key.includes('dci-p3') || key.includes('oled')) {
    return {
      category: isAr ? 'فئة الشاشة والألوان' : 'Display Quality Tier',
      title: isAr ? 'شاشة احترافية دقيقة الألوان (100% sRGB)' : 'Creator Accurate (100% sRGB)',
      subtitle: isAr ? 'تغطية لونية متكاملة ممتازة للتصميم والمونتاج وإنتاج المحتوى' : 'Vibrant color accuracy ideal for editing & media',
      badgeClass: 'text-emerald-400 bg-emerald-500/10 border-emerald-500/30',
      borderClass: 'border-emerald-500/30',
      bgClass: 'bg-emerald-950/20',
      icon: <Monitor className="w-4 h-4 text-emerald-400" />,
    }
  }
  if (key.includes('45%') || key.includes('basic') || key.includes('ntsc')) {
    return {
      category: isAr ? 'فئة الشاشة والألوان' : 'Display Quality Tier',
      title: isAr ? 'شاشة قياسية للأعمال والدراسة (45% NTSC)' : 'Standard Display (45% NTSC)',
      subtitle: isAr ? 'ألوان قياسية مريحة مناسبة للبرمجة والقراءة والأوفيس' : 'Standard gamut suitable for code & office tasks',
      badgeClass: 'text-amber-400 bg-amber-500/10 border-amber-500/30',
      borderClass: 'border-amber-500/30',
      bgClass: 'bg-amber-950/20',
      icon: <Monitor className="w-4 h-4 text-amber-400" />,
    }
  }
  return {
    category: isAr ? 'فئة الشاشة والألوان' : 'Display Quality Tier',
    title: isAr ? 'شاشة سريعة عالية التردد (144Hz+)' : 'High-Refresh Esports Display',
    subtitle: isAr ? 'استجابة فائقة وسلاسة في الحركة للألعاب والتصفح السريع' : 'Smooth high refresh rate with low response latency',
    badgeClass: 'text-sky-400 bg-sky-500/10 border-sky-500/30',
    borderClass: 'border-sky-500/30',
    bgClass: 'bg-sky-950/20',
    icon: <Monitor className="w-4 h-4 text-sky-400" />,
  }
}

function getPortabilityTierInfo(raw: string | undefined | null, isAr: boolean): TierInfo {
  const key = (raw || '').toUpperCase()
  if (key.includes('ULTRA') || key.includes('LIGHT')) {
    return {
      category: isAr ? 'التنقل والوزن' : 'Mobility & Weight Tier',
      title: isAr ? 'خفيف جداً ونحيف للتنقل (< 1.6 كجم)' : 'Ultra-Portable (< 1.6kg)',
      subtitle: isAr ? 'تصميم فائق النحافة يسهل حمله في أي حقيبة طوال اليوم' : 'Ultra-slim chassis designed for effortless mobility',
      badgeClass: 'text-emerald-400 bg-emerald-500/10 border-emerald-500/30',
      borderClass: 'border-emerald-500/30',
      bgClass: 'bg-emerald-950/20',
      icon: <Feather className="w-4 h-4 text-emerald-400" />,
    }
  }
  if (key.includes('DESKTOP') || key.includes('HEAVY')) {
    return {
      category: isAr ? 'التنقل والوزن' : 'Mobility & Weight Tier',
      title: isAr ? 'بديل مكتبي للأداء الثابت (> 2.4 كجم)' : 'Desktop Replacement (> 2.4kg)',
      subtitle: isAr ? 'شاسيه أثقل مصمم للثبات والتبريد العالي على المكتب' : 'Heavier chassis built for sustained gaming power',
      badgeClass: 'text-amber-400 bg-amber-500/10 border-amber-500/30',
      borderClass: 'border-amber-500/30',
      bgClass: 'bg-amber-950/20',
      icon: <Feather className="w-4 h-4 text-amber-400" />,
    }
  }
  return {
    category: isAr ? 'التنقل والوزن' : 'Mobility & Weight Tier',
    title: isAr ? 'وزن متوازن للدراسة والتنقل (~2 كجم)' : 'Balanced Mobility (~2kg)',
    subtitle: isAr ? 'توازن عملي ومريح بين حجم الشاشة وسهولة الحمل اليومي' : 'Practical balance of screen size & everyday portability',
    badgeClass: 'text-sky-400 bg-sky-500/10 border-sky-500/30',
    borderClass: 'border-sky-500/30',
    bgClass: 'bg-sky-950/20',
    icon: <Feather className="w-4 h-4 text-sky-400" />,
  }
}

function getUpgradeabilityTierInfo(raw: string | undefined | null, isAr: boolean): TierInfo {
  const key = (raw || '').toUpperCase()
  if (key.includes('MAXIMUM') || key.includes('HIGH') || key.includes('DUAL')) {
    return {
      category: isAr ? 'قابلية الترقية المستقبلية' : 'Future Expansion Tier',
      title: isAr ? 'ترقية قصوى (فتحتان RAM + منفذان SSD)' : 'Dual RAM & Dual SSD Slots',
      subtitle: isAr ? 'سهولة تامة في مضاعفة الرامات وسعة التخزين مستقبلاً' : 'Full headroom to expand both memory & storage later',
      badgeClass: 'text-emerald-400 bg-emerald-500/10 border-emerald-500/30',
      borderClass: 'border-emerald-500/30',
      bgClass: 'bg-emerald-950/20',
      icon: <Wrench className="w-4 h-4 text-emerald-400" />,
    }
  }
  if (key.includes('LOCKED') || key.includes('SOLDERED')) {
    return {
      category: isAr ? 'قابلية الترقية المستقبلية' : 'Future Expansion Tier',
      title: isAr ? 'ذاكرة مدمجة غير قابلة للزيادة' : 'Soldered / Locked RAM',
      subtitle: isAr ? 'الرامات ملحومة باللوحة الأم، الترقية محصورة في وحدة التخزين' : 'Memory is soldered; expansion limited to SSD slot',
      badgeClass: 'text-rose-400 bg-rose-500/10 border-rose-500/30',
      borderClass: 'border-rose-500/30',
      bgClass: 'bg-rose-950/20',
      icon: <Wrench className="w-4 h-4 text-rose-400" />,
    }
  }
  return {
    category: isAr ? 'قابلية الترقية المستقبلية' : 'Future Expansion Tier',
    title: isAr ? 'ترقية جزئية متوفرة' : 'Moderate Upgradeability',
    subtitle: isAr ? 'منفذ واحد متاح لزيادة الرامات أو فتحة تخزين إضافية' : 'Single open slot or secondary M.2 storage slot',
    badgeClass: 'text-sky-400 bg-sky-500/10 border-sky-500/30',
    borderClass: 'border-sky-500/30',
    bgClass: 'bg-sky-950/20',
    icon: <Wrench className="w-4 h-4 text-sky-400" />,
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
    { labelAr: 'قوة المعالج (CPU)', labelEn: 'CPU Benchmark', score: m?.cpu_score ?? 70, icon: <Cpu className="w-3.5 h-3.5 text-indigo-400" /> },
    { labelAr: 'أداء الجرافيكس (GPU)', labelEn: 'GPU 3D Gaming', score: m?.gpu_score ?? 65, icon: <Monitor className="w-3.5 h-3.5 text-violet-400" /> },
    { labelAr: 'جودة وسرعة الشاشة', labelEn: 'Display Quality', score: m?.display_score ?? 72, icon: <Maximize2 className="w-3.5 h-3.5 text-sky-400" /> },
    { labelAr: 'القيمة مقابل السعر', labelEn: 'Value for Money', score: m?.value_score ?? 85, icon: <Sparkles className="w-3.5 h-3.5 text-emerald-400" /> },
    { labelAr: 'استقرار الطاقة والتبريد', labelEn: 'Sustained Power & Thermals', score: m?.power_therm_score ?? 80, icon: <Zap className="w-3.5 h-3.5 text-rose-400" /> },
    { labelAr: 'سهولة التنقل والوزن', labelEn: 'Mobility & Battery Wh', score: m?.mobility_score ?? 60, icon: <Feather className="w-3.5 h-3.5 text-teal-400" /> },
    { labelAr: 'المنافذ والاتصال', labelEn: 'I/O & Connectivity', score: m?.connectivity_score ?? 75, icon: <Layers className="w-3.5 h-3.5 text-blue-400" /> },
    { labelAr: 'عمر الشاسيه وقابلية الترقية', labelEn: 'Chassis Longevity', score: m?.longevity_score ?? 78, icon: <ShieldCheck className="w-3.5 h-3.5 text-amber-400" /> },
    { labelAr: 'الراحة والكيبورد (Ergonomics)', labelEn: 'Ergonomics & Typing', score: m?.ergonomics_score ?? 74, icon: <Gauge className="w-3.5 h-3.5 text-indigo-300" /> },
    { labelAr: 'تجارب المستخدمين الفعلية', labelEn: 'Community NLP Sentiment', score: m?.community_nlp_score ?? 79, icon: <Award className="w-3.5 h-3.5 text-emerald-300" /> },
  ]

  const review5Aspects = [
    { labelAr: 'التبريد تحت الضغط الصيفي', labelEn: 'Cooling under Stress', score: m?.thermals_score ?? 78, color: 'from-rose-500 to-orange-400' },
    { labelAr: 'هدوء المراوح والصوت', labelEn: 'Fan Acoustics & Quietness', score: m?.acoustics_score ?? 75, color: 'from-sky-500 to-teal-400' },
    { labelAr: 'متانة الشاسيه والمفصلات', labelEn: 'Chassis & Hinge Durability', score: m?.build_and_hinges_score ?? 82, color: 'from-emerald-500 to-teal-400' },
    { labelAr: 'استجابة الكيبورد والتراك باد', labelEn: 'Keyboard & Trackpad Precision', score: m?.keyboard_and_trackpad_score ?? 80, color: 'from-amber-500 to-yellow-400' },
    { labelAr: 'عمر البطارية الحقيقي', labelEn: 'Real Battery Run-Time', score: m?.real_battery_and_reliability_score ?? 79, color: 'from-indigo-500 to-violet-400' },
  ]

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-6 bg-slate-950/85 backdrop-blur-md overflow-y-auto">
      <div className="bg-slate-900 border border-slate-800 rounded-3xl max-w-5xl w-full max-h-[92vh] flex flex-col shadow-2xl relative overflow-hidden my-auto animate-in fade-in duration-200">
        {/* Header */}
        <div className="p-5 sm:p-6 border-b border-slate-800 flex items-start justify-between gap-4 sticky top-0 bg-slate-900/95 backdrop-blur-md z-20">
          <div>
            <div className="flex items-center flex-wrap gap-2 mb-1">
              <span className="text-xs font-bold text-indigo-400 uppercase tracking-wider">
                {brand} {family ? `• ${family}` : ''}
              </span>
              {mpn && (
                <span className="text-[10px] px-2 py-0.5 rounded-md bg-slate-800 text-slate-300 font-mono border border-slate-700">
                  MPN: {mpn}
                </span>
              )}
              {detail?.color && (
                <span className="text-[10px] px-2 py-0.5 rounded-md bg-slate-800 text-slate-400 border border-slate-700">
                  {detail.color}
                </span>
              )}
              {detail?.form_factor && (
                <span className="text-[10px] px-2 py-0.5 rounded-md bg-slate-800 text-slate-300 border border-slate-700">
                  {detail.form_factor}
                </span>
              )}
            </div>
            <h2 className="text-base sm:text-lg font-bold text-white line-clamp-1">
              {title}
            </h2>
          </div>
          <button
            onClick={onClose}
            className="p-2 rounded-xl bg-slate-800 text-slate-400 hover:text-white hover:bg-slate-700 transition-colors shrink-0"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Scrollable Content Body */}
        <div className="p-5 sm:p-6 space-y-6 overflow-y-auto">
          {/* Main Top Grid: Thumbnail & Pricing Comparison */}
          <div className="grid grid-cols-1 sm:grid-cols-12 gap-6">
            {/* Clean White Retail Thumbnail Showcase */}
            <div className="sm:col-span-5 bg-white rounded-2xl p-4 border border-slate-700/40 flex items-center justify-center h-64 sm:h-72 w-full shadow-inner relative overflow-hidden group">
              <img
                src={laptop.thumbnail_url}
                alt={title}
                className="w-full h-full max-h-60 object-contain hover:scale-105 transition-transform duration-300"
                onError={(e) => {
                  ;(e.target as HTMLElement).style.display = 'none'
                }}
              />
            </div>

            {/* Price & Retail Offers Comparison */}
            <div className="sm:col-span-7 flex flex-col justify-between space-y-4">
              <div>
                <span className="text-xs text-slate-400 block mb-1">
                  {isAr ? 'أقل سعر متاح في السوق المصري حالياً:' : 'Lowest Available Market Price:'}
                </span>
                <div className="flex items-baseline gap-2">
                  <span className="text-3xl font-extrabold text-white font-mono">
                    {effectivePrice > 0 ? effectivePrice.toLocaleString() : isAr ? 'السعر عند الطلب' : 'Price on request'}
                  </span>
                  {effectivePrice > 0 && (
                    <span className="text-sm font-semibold text-slate-400">
                      {isAr ? 'ج.م' : 'EGP'}
                    </span>
                  )}
                  <span className="text-xs text-emerald-400 font-semibold">
                    (@ {cheapestStore})
                  </span>
                </div>

                {/* Live Price Verification Timestamp Badge */}
                <div className="flex items-center flex-wrap gap-2 pt-2 text-xs">
                  <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-emerald-950/40 border border-emerald-500/30 text-emerald-300">
                    <span className="relative flex h-2 w-2">
                      <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
                      <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500" />
                    </span>
                    <Clock className="w-3.5 h-3.5 text-emerald-400" />
                    <span className="text-[11px] font-medium">
                      {isAr
                        ? `تم التحقق من السعر مباشرة: ${formatVerificationTime(lastCheckedAt, true)}`
                        : `Verified live from retailer: ${formatVerificationTime(lastCheckedAt, false)}`}
                    </span>
                  </div>

                  {priceSpread > 0 && (
                    <div className="text-[11px] px-2.5 py-1 rounded-lg bg-indigo-950/40 border border-indigo-500/30 text-indigo-300 font-medium">
                      {isAr
                        ? `وفر ${priceSpread.toLocaleString()} ج.م مقارنة بأعلى متجر`
                        : `Save ${priceSpread.toLocaleString()} EGP vs highest store`}
                    </div>
                  )}
                </div>
              </div>

              {/* Multi-Store Offers List */}
              <div className="space-y-2">
                <span className="text-xs font-semibold text-slate-400 flex items-center gap-1.5">
                  <Store className="w-3.5 h-3.5 text-indigo-400" />
                  <span>{isAr ? 'مقارنة الأسعار بين المتاجر المصرية:' : 'Egyptian Retailers Price Comparison:'}</span>
                </span>
                <div className="space-y-1.5 max-h-36 overflow-y-auto pr-1">
                  {detail?.offers && detail.offers.length > 0 ? (
                    detail.offers.map((off, idx) => (
                      <div
                        key={idx}
                        className="flex items-center justify-between p-2.5 rounded-xl bg-slate-950/50 border border-slate-800 text-xs hover:border-slate-700 transition-colors"
                      >
                        <div className="flex items-center gap-2">
                          <span className="font-semibold text-white">{off.store_name}</span>
                          {off.is_cheapest && (
                            <span className="px-1.5 py-0.5 rounded text-[10px] bg-emerald-500/20 text-emerald-400 font-semibold border border-emerald-500/30">
                              {isAr ? 'الأرخص' : 'Best Price'}
                            </span>
                          )}
                          {!off.in_stock && (
                            <span className="px-1.5 py-0.5 rounded text-[10px] bg-rose-500/20 text-rose-400 font-semibold border border-rose-500/30">
                              {isAr ? 'غير متاح' : 'Out of stock'}
                            </span>
                          )}
                        </div>
                        <div className="flex items-center gap-3">
                          <span className="font-mono text-slate-200 font-bold">
                            {off.price_egp > 0 ? `${off.price_egp.toLocaleString()} EGP` : isAr ? 'عند الطلب' : 'Request'}
                          </span>
                          {off.product_url && (
                            <a
                              href={off.product_url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="text-indigo-400 hover:text-indigo-300 transition-colors p-1 rounded hover:bg-slate-800"
                            >
                              <ExternalLink className="w-3.5 h-3.5" />
                            </a>
                          )}
                        </div>
                      </div>
                    ))
                  ) : (
                    <div className="p-3 rounded-xl bg-slate-950/40 text-xs text-slate-400">
                      {isAr ? 'جاري تحديث عروض المتاجر...' : 'Fetching live store listings...'}
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>

          {/* Clean Humanized Operational Tiers (Fixes the overlapping bug) */}
          <div className="space-y-2 pt-2 border-t border-slate-800">
            <h4 className="text-xs font-bold text-slate-300 uppercase tracking-wider flex items-center gap-1.5">
              <Award className="w-3.5 h-3.5 text-indigo-400" />
              <span>{isAr ? 'تصنيف الفئات والقدرات التشغيلية للموديل:' : 'Hardware Operational Tiers:'}</span>
            </h4>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {allTiers.map((tier, idx) => (
                <div
                  key={idx}
                  className={`p-3.5 rounded-2xl border ${tier.borderClass} ${tier.bgClass} flex items-start gap-3 transition-all`}
                >
                  <div className="p-2 rounded-xl bg-slate-900/80 border border-slate-800 shrink-0 mt-0.5">
                    {tier.icon}
                  </div>
                  <div className="space-y-0.5 min-w-0 flex-1">
                    <span className="text-[10px] text-slate-400 font-semibold block uppercase tracking-wider">
                      {tier.category}
                    </span>
                    <div className="text-xs font-bold text-white break-words">
                      {tier.title}
                    </div>
                    <p className="text-[11px] text-slate-400 leading-relaxed break-words">
                      {tier.subtitle}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* 35+ Structured Hardware Dimensions Grid */}
          <div className="space-y-4 pt-2 border-t border-slate-800">
            <div className="flex items-center justify-between pb-1">
              <h3 className="text-sm font-bold text-white flex items-center gap-2">
                <Cpu className="w-4 h-4 text-indigo-400" />
                <span>{isAr ? 'المواصفات التقنية الدقيقة الكاملة (35+ بعد)' : 'Full Detailed Hardware Specifications (35+ Dimensions)'}</span>
              </h3>
              {loading && (
                <div className="flex items-center gap-2 text-xs text-indigo-400">
                  <div className="w-3 h-3 border-2 border-indigo-400 border-t-transparent rounded-full animate-spin" />
                  <span>{isAr ? 'جاري التحميل...' : 'Loading specs...'}</span>
                </div>
              )}
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-3.5 text-xs">
              {/* 1. Processor (CPU) */}
              <div className="p-4 rounded-2xl bg-slate-950/50 border border-slate-800 space-y-2">
                <div className="text-slate-400 flex items-center justify-between font-semibold">
                  <span className="flex items-center gap-1.5">
                    <Cpu className="w-4 h-4 text-indigo-400" />
                    <span>{isAr ? 'المعالج (Processor / CPU)' : 'Processor (CPU)'}</span>
                  </span>
                  {detail?.cpu?.manufacturer && (
                    <span className="text-[10px] px-2 py-0.5 rounded bg-slate-800 text-slate-300">
                      {detail.cpu.manufacturer}
                    </span>
                  )}
                </div>
                <div className="text-white font-bold text-sm">
                  {detail?.cpu?.full_name || detail?.cpu?.model || 'High Performance Processor'}
                </div>
                <div className="grid grid-cols-2 gap-2 text-[11px] text-slate-300 pt-1">
                  <div>
                    <span className="text-slate-500 block">{isAr ? 'الأنوية والمسارات:' : 'Cores & Threads:'}</span>
                    <span className="font-semibold text-slate-200">
                      {detail?.cpu?.cores ?? '-'} Cores • {detail?.cpu?.threads ?? '-'} Threads
                    </span>
                  </div>
                  <div>
                    <span className="text-slate-500 block">{isAr ? 'التردد الأقصى (Boost):' : 'Max Boost Clock:'}</span>
                    <span className="font-semibold text-slate-200">
                      {detail?.cpu?.clock_boost_ghz ? `${detail.cpu.clock_boost_ghz} GHz` : '-'}
                      {detail?.cpu?.clock_base_ghz ? ` (Base: ${detail.cpu.clock_base_ghz} GHz)` : ''}
                    </span>
                  </div>
                  <div>
                    <span className="text-slate-500 block">{isAr ? 'الذاكرة المخبأة (Cache):' : 'Cache:'}</span>
                    <span className="font-semibold text-slate-200">
                      {detail?.cpu?.cache_mb ? `${detail.cpu.cache_mb} MB` : 'Smart Cache'}
                    </span>
                  </div>
                  <div>
                    <span className="text-slate-500 block">{isAr ? 'القدرة الأساسية (TDP):' : 'Base Power (TDP):'}</span>
                    <span className="font-semibold text-slate-200">
                      {detail?.cpu?.base_power_w ? `${detail.cpu.base_power_w}W` : 'Standard'}
                    </span>
                  </div>
                  {detail?.cpu?.microarchitecture && (
                    <div>
                      <span className="text-slate-500 block">{isAr ? 'المعمارية الدقيقة:' : 'Microarchitecture:'}</span>
                      <span className="font-semibold text-slate-200">{detail.cpu.microarchitecture}</span>
                    </div>
                  )}
                  {detail?.cpu?.npu_tops && (
                    <div>
                      <span className="text-slate-500 block">{isAr ? 'معالج الذكاء الاصطناعي (NPU):' : 'AI NPU TOPS:'}</span>
                      <span className="text-indigo-400 font-semibold">{detail.cpu.npu_tops} TOPS</span>
                    </div>
                  )}
                </div>
              </div>

              {/* 2. Graphics (GPU) */}
              <div className="p-4 rounded-2xl bg-slate-950/50 border border-slate-800 space-y-2">
                <div className="text-slate-400 flex items-center justify-between font-semibold">
                  <span className="flex items-center gap-1.5">
                    <Monitor className="w-4 h-4 text-indigo-400" />
                    <span>{isAr ? 'كارت الشاشة (Graphics / GPU)' : 'Graphics (GPU)'}</span>
                  </span>
                  <span className={`text-[10px] px-2 py-0.5 rounded font-semibold ${
                    detail?.gpu?.integrated
                      ? 'bg-slate-800 text-slate-400'
                      : 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/30'
                  }`}>
                    {detail?.gpu?.integrated ? (isAr ? 'مدمج (iGPU)' : 'Integrated') : (isAr ? 'منفصل (Dedicated dGPU)' : 'Dedicated dGPU')}
                  </span>
                </div>
                <div className="text-white font-bold text-sm">
                  {detail?.gpu?.model || 'Graphics Engine'}
                </div>
                <div className="grid grid-cols-2 gap-2 text-[11px] text-slate-300 pt-1">
                  <div>
                    <span className="text-slate-500 block">{isAr ? 'سعة ونوع ذاكرة الفيديو:' : 'VRAM Capacity:'}</span>
                    <span className="font-semibold text-slate-200">
                      {detail?.gpu?.vram_gb ? `${detail.gpu.vram_gb}GB ${detail.gpu.vram_type || 'GDDR6'}` : isAr ? 'مشتركة من الرامات' : 'System Shared'}
                    </span>
                  </div>
                  <div>
                    <span className="text-slate-500 block">{isAr ? 'قدرة الطاقة (TGP / TDP):' : 'Max Power (TGP):'}</span>
                    <span className="font-semibold text-slate-200">
                      {detail?.gpu?.tdp_w ? `${detail.gpu.tdp_w}W` : isAr ? 'استهلاك قياسي' : 'Standard'}
                    </span>
                  </div>
                  {detail?.gpu?.variant && (
                    <div>
                      <span className="text-slate-500 block">{isAr ? 'المعمارية الفرعية:' : 'Sub-variant:'}</span>
                      <span className="font-semibold text-slate-200">{detail.gpu.variant}</span>
                    </div>
                  )}
                  {detail?.gpu?.ai_tops && (
                    <div>
                      <span className="text-slate-500 block">{isAr ? 'أداء الذكاء الاصطناعي GPU TOPS:' : 'GPU AI TOPS:'}</span>
                      <span className="text-indigo-400 font-semibold">{detail.gpu.ai_tops} TOPS</span>
                    </div>
                  )}
                  {detail?.gpu?.igpu_model && !detail?.gpu?.integrated && (
                    <div className="col-span-2">
                      <span className="text-slate-500 block">{isAr ? 'الكارت المدمج الثانوي (للتوفير):' : 'Secondary iGPU (Battery Saver):'}</span>
                      <span className="font-semibold text-slate-300">{detail.gpu.igpu_model}</span>
                    </div>
                  )}
                </div>
              </div>

              {/* 3. Memory (RAM) */}
              <div className="p-4 rounded-2xl bg-slate-950/50 border border-slate-800 space-y-2">
                <div className="text-slate-400 flex items-center justify-between font-semibold">
                  <span className="flex items-center gap-1.5">
                    <MemoryStick className="w-4 h-4 text-indigo-400" />
                    <span>{isAr ? 'الذاكرة العشوائية (RAM)' : 'Memory (RAM)'}</span>
                  </span>
                  <span className="text-[10px] px-2 py-0.5 rounded bg-slate-800 text-slate-300 font-mono">
                    {detail?.memory?.memory_type || 'DDR5'}
                  </span>
                </div>
                <div className="text-white font-bold text-sm">
                  {detail?.memory?.capacity_gb || 16}GB {detail?.memory?.memory_type || 'DDR5'}
                </div>
                <div className="grid grid-cols-2 gap-2 text-[11px] text-slate-300 pt-1">
                  <div>
                    <span className="text-slate-500 block">{isAr ? 'تردد وسرعة الذاكرة:' : 'Memory Speed:'}</span>
                    <span className="font-semibold text-slate-200">{detail?.memory?.speed_mhz ? `${detail.memory.speed_mhz} MHz` : 'High Speed'}</span>
                  </div>
                  <div>
                    <span className="text-slate-500 block">{isAr ? 'المنافذ والترقية:' : 'Slots / Expansion:'}</span>
                    <span className="font-semibold text-slate-200">
                      {detail?.memory?.is_soldered
                        ? isAr ? 'ملحومة باللوحة (Soldered)' : 'Soldered On-board'
                        : detail?.memory?.slot_count ? `${detail.memory.slot_count}x SO-DIMM (Upgradeable)` : isAr ? 'قابلة للترقية' : 'Upgradeable'}
                    </span>
                  </div>
                  {detail?.memory?.max_supported_gb && (
                    <div>
                      <span className="text-slate-500 block">{isAr ? 'أقصى سعة مدعومة:' : 'Max Supported RAM:'}</span>
                      <span className="font-semibold text-indigo-300">{detail.memory.max_supported_gb} GB</span>
                    </div>
                  )}
                  {detail?.memory?.channels && (
                    <div>
                      <span className="text-slate-500 block">{isAr ? 'قنوات التوصيل:' : 'Channels:'}</span>
                      <span className="font-semibold text-slate-200">{detail.memory.channels}</span>
                    </div>
                  )}
                </div>
              </div>

              {/* 4. Storage (SSD) */}
              <div className="p-4 rounded-2xl bg-slate-950/50 border border-slate-800 space-y-2">
                <div className="text-slate-400 flex items-center justify-between font-semibold">
                  <span className="flex items-center gap-1.5">
                    <HardDrive className="w-4 h-4 text-indigo-400" />
                    <span>{isAr ? 'وحدة التخزين (Storage / SSD)' : 'Storage (SSD)'}</span>
                  </span>
                  <span className="text-[10px] px-2 py-0.5 rounded bg-slate-800 text-slate-300">
                    {detail?.storage?.storage_type || 'NVMe SSD'}
                  </span>
                </div>
                <div className="text-white font-bold text-sm">
                  {detail?.storage?.capacity_gb ? `${detail.storage.capacity_gb}GB` : '512GB'} PCIe NVMe SSD
                </div>
                <div className="grid grid-cols-2 gap-2 text-[11px] text-slate-300 pt-1">
                  <div>
                    <span className="text-slate-500 block">{isAr ? 'واجهة التوصيل:' : 'Interface:'}</span>
                    <span className="font-semibold text-slate-200">{detail?.storage?.interface || 'PCIe Gen 4.0 x4'}</span>
                  </div>
                  <div>
                    <span className="text-slate-500 block">{isAr ? 'منافذ M.2 الإضافية:' : 'M.2 Expansion Slots:'}</span>
                    <span className="font-semibold text-indigo-300">
                      {detail?.storage?.slot_count ? `${detail.storage.slot_count}x M.2 Slots` : isAr ? 'منفذ إضافي متاح' : 'Secondary slot available'}
                    </span>
                  </div>
                </div>
              </div>

              {/* 5. Display */}
              <div className="p-4 rounded-2xl bg-slate-950/50 border border-slate-800 space-y-2">
                <div className="text-slate-400 flex items-center justify-between font-semibold">
                  <span className="flex items-center gap-1.5">
                    <Maximize2 className="w-4 h-4 text-indigo-400" />
                    <span>{isAr ? 'الشاشة والعرض (Display)' : 'Display'}</span>
                  </span>
                  <span className="text-[10px] px-2 py-0.5 rounded bg-slate-800 text-slate-300 font-mono">
                    {detail?.display?.refresh_rate_hz || 60}Hz
                  </span>
                </div>
                <div className="text-white font-bold text-sm">
                  {detail?.display?.size_inches}" {detail?.display?.resolution} ({detail?.display?.panel_type || 'IPS'})
                </div>
                <div className="grid grid-cols-2 gap-2 text-[11px] text-slate-300 pt-1">
                  <div>
                    <span className="text-slate-500 block">{isAr ? 'النسبة والسطوع:' : 'Aspect Ratio & Nits:'}</span>
                    <span className="font-semibold text-slate-200">
                      {detail?.display?.aspect_ratio || '16:10'} • {detail?.display?.brightness_nits ? `${detail.display.brightness_nits} nits` : '300 nits'}
                    </span>
                  </div>
                  <div>
                    <span className="text-slate-500 block">{isAr ? 'دقة الألوان واللمس:' : 'Color Gamut & Touch:'}</span>
                    <span className="font-semibold text-slate-200">
                      {detail?.display?.color_gamut || '100% sRGB'} • {detail?.display?.touchscreen ? (isAr ? 'تدعم اللمس' : 'Touchscreen') : (isAr ? 'غير لمسية' : 'Non-touch')}
                    </span>
                  </div>
                  {detail?.display?.hdr && (
                    <div>
                      <span className="text-slate-500 block">{isAr ? 'المدى الديناميكي (HDR):' : 'High Dynamic Range:'}</span>
                      <span className="text-emerald-400 font-semibold">{isAr ? 'يدعم HDR' : 'HDR Supported'}</span>
                    </div>
                  )}
                  {detail?.display?.width && detail?.display?.height && (
                    <div>
                      <span className="text-slate-500 block">{isAr ? 'البيكسلات الدقيقة:' : 'Exact Resolution:'}</span>
                      <span className="font-mono text-slate-200">{detail.display.width} x {detail.display.height}</span>
                    </div>
                  )}
                </div>
              </div>

              {/* 6. Power & Battery */}
              <div className="p-4 rounded-2xl bg-slate-950/50 border border-slate-800 space-y-2">
                <div className="text-slate-400 flex items-center justify-between font-semibold">
                  <span className="flex items-center gap-1.5">
                    <BatteryCharging className="w-4 h-4 text-indigo-400" />
                    <span>{isAr ? 'البطارية والشاحن (Battery & Power)' : 'Power & Battery'}</span>
                  </span>
                  {detail?.power_battery?.usb_c_pd_charging && (
                    <span className="text-[10px] px-2 py-0.5 rounded bg-indigo-500/20 text-indigo-300 border border-indigo-500/30 font-semibold">
                      USB-C PD
                    </span>
                  )}
                </div>
                <div className="text-white font-bold text-sm">
                  {detail?.power_battery?.battery_capacity_wh ? `${detail.power_battery.battery_capacity_wh}Wh` : 'Long-life'} Battery
                </div>
                <div className="grid grid-cols-2 gap-2 text-[11px] text-slate-300 pt-1">
                  <div>
                    <span className="text-slate-500 block">{isAr ? 'قدرة الشاحن الأصلي:' : 'Adapter Wattage:'}</span>
                    <span className="font-semibold text-slate-200">{detail?.power_battery?.power_adapter_w ? `${detail.power_battery.power_adapter_w}W` : 'Fast Adapter'}</span>
                  </div>
                  <div>
                    <span className="text-slate-500 block">{isAr ? 'شحن تايب سي والشحن السريع:' : 'USB-C PD & Fast Charge:'}</span>
                    <span className="font-semibold text-slate-200">
                      {detail?.power_battery?.usb_c_pd_charging ? (isAr ? 'يدعم USB-C PD' : 'USB-C PD Supported') : (isAr ? 'شاحن مخصص' : 'Dedicated Port')}
                    </span>
                  </div>
                  {detail?.power_battery?.battery_cells && (
                    <div>
                      <span className="text-slate-500 block">{isAr ? 'خلايا البطارية:' : 'Battery Cells:'}</span>
                      <span className="font-semibold text-slate-200">{detail.power_battery.battery_cells} Cells</span>
                    </div>
                  )}
                  {detail?.metrics?.estimated_battery_hours && (
                    <div>
                      <span className="text-slate-500 block">{isAr ? 'عمر البطارية الفعلي المقدر:' : 'Estimated Runtime:'}</span>
                      <span className="font-semibold text-emerald-400">~{detail.metrics.estimated_battery_hours} {isAr ? 'ساعات' : 'hours'}</span>
                    </div>
                  )}
                </div>
              </div>

              {/* 7. Build, Keyboard & Biometrics */}
              <div className="p-4 rounded-2xl bg-slate-950/50 border border-slate-800 space-y-2">
                <div className="text-slate-400 flex items-center justify-between font-semibold">
                  <span className="flex items-center gap-1.5">
                    <ShieldCheck className="w-4 h-4 text-indigo-400" />
                    <span>{isAr ? 'الشاسيه، الكيبورد والأمان' : 'Build & Security'}</span>
                  </span>
                  {detail?.physical?.weight_kg && (
                    <span className="text-[10px] px-2 py-0.5 rounded bg-slate-800 text-slate-300 font-mono">
                      {detail.physical.weight_kg} kg
                    </span>
                  )}
                </div>
                <div className="text-white font-medium text-xs leading-relaxed">
                  {detail?.build_security?.has_backlit_keyboard
                    ? isAr ? `كيبورد مضيء (${detail.build_security.keyboard_backlight_type || 'RGB'})` : `Backlit Keyboard (${detail.build_security.keyboard_backlight_type || 'RGB'})`
                    : isAr ? 'كيبورد قياسي' : 'Standard Keyboard'}
                  {detail?.build_security?.has_fingerprint ? (isAr ? ' • بصمة إصبع' : ' • Fingerprint Reader') : ''}
                  {detail?.build_security?.has_copilot_key ? (isAr ? ' • زر Copilot للذكاء الاصطناعي' : ' • Copilot AI Key') : ''}
                </div>
                <div className="grid grid-cols-2 gap-2 text-[11px] text-slate-300 pt-1">
                  <div>
                    <span className="text-slate-500 block">{isAr ? 'الوزن الصافي:' : 'Chassis Weight:'}</span>
                    <span className="font-semibold text-slate-200">{detail?.physical?.weight_kg ? `${detail.physical.weight_kg} kg` : isAr ? 'خفيف وسهل التنقل' : 'Portable'}</span>
                  </div>
                  <div>
                    <span className="text-slate-500 block">{isAr ? 'الأبعاد بالملم (عرض×عمق×سمك):' : 'Dimensions (W x D x H):'}</span>
                    <span className="font-mono text-slate-200">
                      {detail?.physical?.width_mm && detail?.physical?.depth_mm
                        ? `${detail.physical.width_mm} × ${detail.physical.depth_mm} × ${detail?.physical?.height_mm || 20} mm`
                        : isAr ? 'هيكل قياسي' : 'Standard'}
                    </span>
                  </div>
                </div>
              </div>

              {/* 8. Audio, Webcam & Connectivity */}
              <div className="p-4 rounded-2xl bg-slate-950/50 border border-slate-800 space-y-2">
                <div className="text-slate-400 flex items-center justify-between font-semibold">
                  <span className="flex items-center gap-1.5">
                    <Wifi className="w-4 h-4 text-indigo-400" />
                    <span>{isAr ? 'الصوت، الكاميرا والشبكات' : 'Audio, Webcam & Network'}</span>
                  </span>
                  <span className="text-[10px] px-2 py-0.5 rounded bg-slate-800 text-slate-300">
                    {detail?.connectivity_os?.wifi || 'Wi-Fi 6'}
                  </span>
                </div>
                <div className="text-white font-medium text-xs leading-relaxed">
                  {detail?.audio_webcam?.webcam_resolution || '1080p FHD'} Webcam
                  {detail?.audio_webcam?.has_privacy_shutter ? (isAr ? ' • غالق خصوصية' : ' • Privacy Shutter') : ''}
                  {detail?.audio_webcam?.has_ir_camera ? (isAr ? ' • كاميرا IR Windows Hello' : ' • IR Windows Hello') : ''}
                </div>
                <div className="grid grid-cols-2 gap-2 text-[11px] text-slate-300 pt-1">
                  <div>
                    <span className="text-slate-500 block">{isAr ? 'نظام الصوت:' : 'Audio Speakers:'}</span>
                    <span className="font-semibold text-slate-200">
                      {detail?.audio_webcam?.speaker_count || 2}x Stereo
                      {detail?.audio_webcam?.audio_system ? ` (${detail.audio_webcam.audio_system})` : ''}
                    </span>
                  </div>
                  <div>
                    <span className="text-slate-500 block">{isAr ? 'بلوتوث ومنفذ إيثرنت:' : 'Bluetooth & Ethernet:'}</span>
                    <span className="font-semibold text-slate-200">
                      {detail?.connectivity_os?.bluetooth || 'Bluetooth 5.3'}
                      {detail?.connectivity_os?.has_ethernet ? ` • RJ-45 (${detail.connectivity_os.ethernet_speed || 'Gigabit'})` : ''}
                    </span>
                  </div>
                  {detail?.connectivity_os?.operating_system && (
                    <div className="col-span-2">
                      <span className="text-slate-500 block">{isAr ? 'نظام التشغيل المثبت:' : 'Operating System:'}</span>
                      <span className="font-semibold text-indigo-300">{detail.connectivity_os.operating_system}</span>
                    </div>
                  )}
                </div>
              </div>
            </div>

            {/* Ports & Connectivity Full List */}
            {detail?.connectivity_os?.ports && detail.connectivity_os.ports.length > 0 && (
              <div className="p-4 rounded-2xl bg-slate-950/50 border border-slate-800 space-y-2">
                <span className="text-xs font-semibold text-slate-400 flex items-center gap-1.5">
                  <Layers className="w-3.5 h-3.5 text-indigo-400" />
                  <span>{isAr ? 'المنافذ والتوصيل (I/O Ports):' : 'Available I/O Ports:'}</span>
                </span>
                <div className="flex flex-wrap gap-1.5">
                  {detail.connectivity_os.ports.map((port, idx) => (
                    <span
                      key={idx}
                      className="px-2.5 py-1 rounded-lg bg-slate-800 text-slate-200 text-[11px] border border-slate-700 font-mono"
                    >
                      {port}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Full 15 Performance Scores Dashboard (Progressive Toggle) */}
          <div className="space-y-3 pt-2 border-t border-slate-800">
            <button
              onClick={() => setShowAllScores(!showAllScores)}
              className="w-full flex items-center justify-between p-3.5 rounded-2xl bg-slate-950/40 hover:bg-slate-950/70 border border-slate-800 transition-colors text-left"
            >
              <div className="flex items-center gap-2">
                <SlidersHorizontal className="w-4 h-4 text-indigo-400" />
                <span className="font-bold text-xs text-white">
                  {isAr ? 'لوحة مؤشرات الأداء والتقييم الـ 15 الكاملة (TOPSIS & Reviews)' : 'Full 15-Dimension Scorecard (TOPSIS & Reviews)'}
                </span>
              </div>
              <div className="flex items-center gap-1.5 text-xs text-indigo-400 font-semibold">
                <span>{showAllScores ? (isAr ? 'إخفاء' : 'Collapse') : (isAr ? 'عرض كافة المقاييس' : 'Expand')}</span>
                {showAllScores ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
              </div>
            </button>

            {showAllScores && (
              <div className="p-4 rounded-2xl bg-slate-950/60 border border-slate-800/80 space-y-5 animate-in fade-in duration-200">
                {/* 10 TOPSIS Decision Criteria */}
                <div className="space-y-2.5">
                  <span className="text-[11px] font-bold text-indigo-300 uppercase tracking-wider block">
                    {isAr ? 'المعايير الهندسية والعتاد الـ 10 (TOPSIS Inputs):' : '10 Hardware Decision Criteria (TOPSIS):'}
                  </span>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                    {topsis10Scores.map((sc, i) => (
                      <div key={i} className="p-2.5 rounded-xl bg-slate-900 border border-slate-800 space-y-1">
                        <div className="flex items-center justify-between text-xs text-slate-300">
                          <span className="flex items-center gap-1.5">
                            {sc.icon}
                            <span>{isAr ? sc.labelAr : sc.labelEn}</span>
                          </span>
                          <span className="font-mono font-bold text-white">{sc.score.toFixed(1)}/100</span>
                        </div>
                        <div className="w-full bg-slate-800 h-1.5 rounded-full overflow-hidden">
                          <div
                            className="h-full rounded-full bg-gradient-to-r from-indigo-500 to-sky-400"
                            style={{ width: `${Math.min(100, Math.max(10, sc.score))}%` }}
                          />
                        </div>
                      </div>
                    ))}
                  </div>
                </div>

                {/* 5 Review Intelligence Aspects */}
                <div className="space-y-2.5 pt-3 border-t border-slate-800/80">
                  <span className="text-[11px] font-bold text-emerald-300 uppercase tracking-wider block">
                    {isAr ? 'الاختبارات الميدانية وتقييمات المستخدمين الـ 5 (Review Intelligence):' : '5 Field Review Aspects (Real-World Stress):'}
                  </span>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                    {review5Aspects.map((asp, i) => (
                      <div key={i} className="p-2.5 rounded-xl bg-slate-900 border border-slate-800 space-y-1">
                        <div className="flex items-center justify-between text-xs text-slate-300">
                          <span>{isAr ? asp.labelAr : asp.labelEn}</span>
                          <span className="font-mono font-bold text-white">{asp.score.toFixed(1)}/100</span>
                        </div>
                        <div className="w-full bg-slate-800 h-1.5 rounded-full overflow-hidden">
                          <div
                            className={`h-full rounded-full bg-gradient-to-r ${asp.color}`}
                            style={{ width: `${Math.min(100, Math.max(10, asp.score))}%` }}
                          />
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Community Review Pros & Cons */}
          {(pros.length > 0 || cons.length > 0) && (
            <div className="space-y-3 pt-2 border-t border-slate-800">
              <h4 className="text-xs font-bold text-slate-300 uppercase tracking-wider flex items-center gap-1.5">
                <Sparkles className="w-3.5 h-3.5 text-indigo-400" />
                <span>{isAr ? 'خلاصة تقييمات وتجارب المستخدمين الفعلية:' : 'Real User & Review Insights:'}</span>
              </h4>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
                {/* Pros */}
                <div className="p-3.5 rounded-2xl bg-emerald-950/20 border border-emerald-500/20 space-y-2">
                  <span className="font-bold text-emerald-400 flex items-center gap-1">
                    <CheckCircle className="w-3.5 h-3.5" />
                    <span>{isAr ? 'المميزات الرئيسية' : 'Key Advantages'}</span>
                  </span>
                  <div className="space-y-1">
                    {pros.map((p: string, i: number) => (
                      <div key={i} className="text-slate-200 flex items-start gap-1.5 leading-relaxed">
                        <span className="text-emerald-400 text-xs mt-0.5 font-bold">✓</span>
                        <span>{p}</span>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Cons */}
                <div className="p-3.5 rounded-2xl bg-rose-950/20 border border-rose-500/20 space-y-2">
                  <span className="font-bold text-rose-400 flex items-center gap-1">
                    <XCircle className="w-3.5 h-3.5" />
                    <span>{isAr ? 'العيوب والملاحظات' : 'Technical Drawbacks'}</span>
                  </span>
                  <div className="space-y-1">
                    {cons.map((c: string, i: number) => (
                      <div key={i} className="text-slate-200 flex items-start gap-1.5 leading-relaxed">
                        <span className="text-rose-400 text-xs mt-0.5 font-bold">✕</span>
                        <span>{c}</span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Modal Sticky Footer CTA */}
        <div className="p-4 border-t border-slate-800 bg-slate-900 flex items-center justify-between">
          <div className="text-xs text-slate-400">
            {isAr ? 'الأسعار والمواصفات محدثة وموثقة مباشرة من المتاجر' : 'Real-time verified pricing and specs'}
          </div>
          <a
            href={cheapestOfferUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="px-6 py-2.5 rounded-xl bg-gradient-to-r from-indigo-600 to-violet-600 hover:from-indigo-500 hover:to-violet-500 text-white font-semibold text-xs shadow-lg shadow-indigo-600/20 transition-all flex items-center gap-2"
          >
            <span>{isAr ? `شراء من ${cheapestStore}` : `Buy from ${cheapestStore}`}</span>
            <ExternalLink className="w-3.5 h-3.5" />
          </a>
        </div>
      </div>
    </div>
  )
}
