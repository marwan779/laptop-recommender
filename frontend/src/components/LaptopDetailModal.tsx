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
  Tag,
  Layers,
  Award,
  Zap,
  Feather,
  Gauge,
  SlidersHorizontal,
  ChevronDown,
  ChevronUp,
  Video,
  MessageSquare,
  FileText,
  Play,
} from 'lucide-react'
import type {
  FullLaptopDetailResponse,
  RankedLaptop,
  CatalogListItem,
  ReviewSourceDetail,
} from '../types/api'
import { fetchLaptopDetail } from '../services/api'
import {
  getDisplayTierInfo,
  getPortabilityTierInfo,
  getSiliconTierInfo,
  getUpgradeabilityTierInfo,
  type TierInfo,
} from '../utils/hardwareTiers'
import { PriceHistoryChart } from './PriceHistoryChart'

interface LaptopDetailModalProps {
  laptop: RankedLaptop | CatalogListItem | null
  onClose: () => void
  lang: 'ar' | 'en'
}

function formatVerificationTime(isoStr: string | null | undefined, isAr: boolean): string {
  if (!isoStr) return isAr ? 'غير محدد' : 'Unverified'
  try {
    const d = new Date(isoStr)
    if (isNaN(d.getTime())) return isAr ? 'غير محدد' : 'Unverified'
    return d.toLocaleString(isAr ? 'ar-EG' : 'en-US', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return isAr ? 'غير محدد' : 'Unverified'
  }
}

function safeHttpUrl(raw: string | null | undefined): string | null {
  if (!raw) return null
  const trimmed = raw.trim()
  const low = trimmed.toLowerCase()
  if (low.startsWith('https://') || low.startsWith('http://')) {
    return trimmed
  }
  return null
}

function formatCompactCount(val: number): string {
  if (val >= 1_000_000) return `${(val / 1_000_000).toFixed(1)}M`
  if (val >= 1_000) return `${(val / 1_000).toFixed(1)}K`
  return String(val)
}

function formatPlatformLabel(platform: string, sourceType: string): string {
  const normalized = (platform || sourceType || 'review').trim().toLowerCase()
  const labels: Record<string, string> = {
    youtube: 'YouTube',
    reddit: 'Reddit',
    level1techs: 'Level1Techs',
    arabhardware: 'ArabHardware',
    laptopmag: 'LaptopMag',
    notebookcheck: 'Notebookcheck',
  }
  return labels[normalized] || platform.trim()
}

function extractYouTubeVideoId(rawUrl: string): string | null {
  try {
    const url = new URL(rawUrl)
    const host = url.hostname.toLowerCase()
    let candidate: string | null = null

    if (host === 'youtu.be') {
      const segment = url.pathname.split('/').filter(Boolean)[0] ?? ''
      candidate = segment || null
    } else if (host.endsWith('youtube.com') || host.endsWith('youtube-nocookie.com')) {
      candidate = url.searchParams.get('v')
      if (!candidate) {
        const match = url.pathname.match(/^\/(?:shorts|embed|live)\/([^/?#]+)/)
        candidate = match ? match[1] : null
      }
    }

    if (!candidate) return null
    return /^[A-Za-z0-9_-]{11}$/.test(candidate) ? candidate : null
  } catch {
    return null
  }
}

function getYouTubeThumbnailUrl(rawUrl: string): string | null {
  const videoId = extractYouTubeVideoId(rawUrl)
  // mqdefault is a native 320x180 (16:9) frame, so no black letterbox bars.
  return videoId ? `https://i.ytimg.com/vi/${videoId}/mqdefault.jpg` : null
}

function extractDisplayHost(rawUrl: string): string | null {
  try {
    const host = new URL(rawUrl).hostname.toLowerCase()
    return host.replace(/^www\./, '') || null
  } catch {
    return null
  }
}

function formatSourceMetric(src: ReviewSourceDetail, isAr: boolean): string | null {
  if (src.source_type === 'editorial' && src.rating != null) {
    return `${Number(src.rating).toFixed(1)}/100`
  }
  if (src.source_type === 'youtube' && src.score_or_views != null && src.score_or_views > 0) {
    const formatted = formatCompactCount(src.score_or_views)
    return isAr ? `${formatted} مشاهدة` : `${formatted} views`
  }
  if (src.score_or_views != null && src.score_or_views > 0) {
    const formatted = formatCompactCount(src.score_or_views)
    return isAr ? `${formatted} تفاعل` : `${formatted} pts`
  }
  return null
}

function getSourceIcon(sourceType: string): React.ReactNode {
  if (sourceType === 'youtube') {
    return <Video className="w-3.5 h-3.5 shrink-0" strokeWidth={1.8} />
  }
  if (sourceType === 'editorial') {
    return <FileText className="w-3.5 h-3.5 shrink-0" strokeWidth={1.8} />
  }
  return <MessageSquare className="w-3.5 h-3.5 shrink-0" strokeWidth={1.8} />
}

interface ReviewSourceCardProps {
  src: ReviewSourceDetail
  href: string
  isAr: boolean
}

function ReviewSourceCard({ src, href, isAr }: ReviewSourceCardProps) {
  const thumbUrl = src.source_type === 'youtube' ? getYouTubeThumbnailUrl(href) : null
  const [thumbFailed, setThumbFailed] = useState(false)

  useEffect(() => {
    setThumbFailed(false)
  }, [thumbUrl])

  const showThumbnail = Boolean(thumbUrl && !thumbFailed)
  const metricLabel = formatSourceMetric(src, isAr)
  const hostLabel = extractDisplayHost(href)

  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="group flex items-stretch gap-3 rounded-[10px] border border-[var(--border-subtle)] bg-[var(--bg-raised)] p-2.5 transition-colors hover:border-[var(--gold)] hover:bg-[var(--gold-dim)]"
    >
      {/* Media slot: compact 16:9 thumbnail or an identical-height icon fallback */}
      <div className="w-[112px] aspect-video shrink-0 rounded-[6px] overflow-hidden border border-[var(--border-subtle)] bg-[var(--bg-input)] relative flex items-center justify-center">
        {showThumbnail ? (
          <>
            <img
              src={thumbUrl!}
              alt={src.title}
              loading="lazy"
              decoding="async"
              referrerPolicy="no-referrer"
              onError={() => setThumbFailed(true)}
              className="w-full h-full object-cover transition-transform duration-200 group-hover:scale-[1.03]"
            />
            <div className="pointer-events-none absolute inset-0 flex items-center justify-center bg-[#0A0E13]/25">
              <span className="w-7 h-7 rounded-full bg-[#0A0E13]/80 border border-white/15 flex items-center justify-center text-white group-hover:border-[var(--gold)] group-hover:text-[var(--gold-bright)]">
                <Play className="w-3.5 h-3.5 fill-current ms-0.5" />
              </span>
            </div>
          </>
        ) : (
          <div className="flex flex-col items-center justify-center gap-1 px-1.5 text-center">
            <span className="text-[var(--text-secondary)] group-hover:text-[var(--gold-bright)]">
              {getSourceIcon(src.source_type)}
            </span>
            {hostLabel && (
              <span
                dir="ltr"
                className="text-[12px] text-[var(--text-muted)] truncate max-w-full px-1.5"
                style={{ fontFamily: 'var(--font-mono)' }}
              >
                {hostLabel}
              </span>
            )}
          </div>
        )}
      </div>

      {/* Text column */}
      <div className="flex-1 min-w-0 flex flex-col justify-between gap-1">
        <div className="flex items-center justify-between gap-2">
          <span className="inline-flex items-center gap-1.5 min-w-0 text-[12px] font-semibold uppercase tracking-[0.06em] text-[var(--text-secondary)] group-hover:text-[var(--text-primary)]">
            {getSourceIcon(src.source_type)}
            <span className="truncate">{formatPlatformLabel(src.platform, src.source_type)}</span>
          </span>
          <div className="flex items-center gap-2 shrink-0">
            {metricLabel && (
              <span
                className="text-[12px] font-medium text-[var(--text-muted)] tabular-nums"
                style={{ fontFamily: 'var(--font-mono)' }}
              >
                {metricLabel}
              </span>
            )}
            <ExternalLink
              className="w-3.5 h-3.5 text-[var(--text-muted)] group-hover:text-[var(--gold-bright)]"
              strokeWidth={1.8}
            />
          </div>
        </div>

        <div
          dir="auto"
          className="text-[13px] font-medium leading-[1.4] text-[var(--text-primary)] line-clamp-2"
        >
          {src.title}
        </div>

        {src.author_or_channel && (
          <div
            dir="auto"
            className="text-[12px] text-[var(--text-muted)] truncate"
          >
            {src.author_or_channel}
          </div>
        )}
      </div>
    </a>
  )
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
  const [expandedSourcesForId, setExpandedSourcesForId] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState<'prices' | 'reviews' | 'specs' | 'score'>('prices')
  const laptopId = laptop?.canonical_id

  useEffect(() => {
    if (!laptopId) return
    setLoading(true)
    setDetail(null)
    fetchLaptopDetail(laptopId)
      .then((data) => setDetail(data))
      .catch((err) => console.error('Error fetching detail:', err))
      .finally(() => setLoading(false))
  }, [laptopId])

  useEffect(() => {
    if (!laptopId) return
    setActiveTab('prices')
    setExpandedSourcesForId(null)
  }, [laptopId])

  useEffect(() => {
    if (!laptop) return
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [laptop, onClose])

  if (!laptop) return null

  const title = detail?.title || laptop.title
  const brand = detail?.brand || laptop.brand
  const family = detail?.laptop_family || (laptop as any).laptop_family || ''
  const mpn = detail?.mpn || (laptop as any).mpn || ''
  const effectivePrice = detail?.min_price_egp || (laptop as any).effective_price_egp || (laptop as any).min_price_egp || 0
  const cheapestStore =
    detail?.cheapest_store ||
    (laptop as any).cheapest_store ||
    (isAr ? 'متجر معتمد' : 'Authorized Store')
  const rawCheapestOfferUrl =
    detail?.cheapest_offer_url ||
    (laptop as any).cheapest_offer_url ||
    (laptop as any).urls_by_store?.[cheapestStore] ||
    null
  const cheapestOfferUrl =
    rawCheapestOfferUrl && rawCheapestOfferUrl !== '#' ? rawCheapestOfferUrl : null
  const priceSpread = detail?.price_spread_egp || (laptop as any).price_spread_egp || 0

  // Freshness & Verification Timestamp
  const cheapestOffer = detail?.offers?.find((o) => o.is_cheapest) || detail?.offers?.[0]
  const lastCheckedAt = cheapestOffer?.last_checked_at || (detail as any)?.price_checked_at || (detail as any)?.price_updated_at

  const pros = isAr ? detail?.pros_ar || (laptop as any).pros_ar || [] : detail?.pros_en || (laptop as any).pros_en || []
  const cons = isAr ? detail?.cons_ar || (laptop as any).cons_ar || [] : detail?.cons_en || (laptop as any).cons_en || []
  const reviewSources = (detail?.review_sources || []).filter((src) => Boolean(safeHttpUrl(src.url)))
  const showAllSources = expandedSourcesForId === laptop.canonical_id
  const visibleReviewSources = showAllSources ? reviewSources : reviewSources.slice(0, 6)
  const hasVerifiedReviews = Boolean(
    detail?.has_reviews ||
      (detail?.reviews_evidence_count ?? 0) > 0 ||
      pros.length > 0 ||
      cons.length > 0 ||
      reviewSources.length > 0
  )

  // Operational Tiers with Human Mappings
  const siliconTier = getSiliconTierInfo(detail?.metrics?.silicon_tier, isAr)
  const displayTier = getDisplayTierInfo(detail?.metrics?.display_tier, isAr)
  const portabilityTier = getPortabilityTierInfo(detail?.metrics?.portability_tier, isAr)
  const upgradeTier = getUpgradeabilityTierInfo(detail?.metrics?.upgradeability_tier, isAr)

  const activeTiers = [siliconTier, displayTier, portabilityTier, upgradeTier].filter(
    (tier): tier is TierInfo => tier !== null
  )

  // All 15 Normalized Scores
  const m = detail?.metrics
  const topsis10Scores = [
    { labelAr: 'قوة المعالج (CPU)', labelEn: 'CPU Benchmark', score: m?.cpu_score != null ? Number(m.cpu_score) : null, icon: <Cpu className="w-3.5 h-3.5" strokeWidth={1.8} /> },
    { labelAr: 'أداء الجرافيكس (GPU)', labelEn: 'GPU 3D Gaming', score: m?.gpu_score != null ? Number(m.gpu_score) : null, icon: <Monitor className="w-3.5 h-3.5" strokeWidth={1.8} /> },
    { labelAr: 'جودة وسرعة الشاشة', labelEn: 'Display Quality', score: m?.display_score != null ? Number(m.display_score) : null, icon: <Maximize2 className="w-3.5 h-3.5" strokeWidth={1.8} /> },
    { labelAr: 'القيمة مقابل السعر', labelEn: 'Value for Money', score: m?.value_score != null ? Number(m.value_score) : null, icon: <Tag className="w-3.5 h-3.5" strokeWidth={1.8} /> },
    { labelAr: 'استقرار الطاقة والتبريد', labelEn: 'Sustained Power & Thermals', score: m?.power_therm_score != null ? Number(m.power_therm_score) : null, icon: <Zap className="w-3.5 h-3.5" strokeWidth={1.8} /> },
    { labelAr: 'سهولة التنقل والوزن', labelEn: 'Mobility & Battery Wh', score: m?.mobility_score != null ? Number(m.mobility_score) : null, icon: <Feather className="w-3.5 h-3.5" strokeWidth={1.8} /> },
    { labelAr: 'المنافذ والاتصال', labelEn: 'I/O & Connectivity', score: m?.connectivity_score != null ? Number(m.connectivity_score) : null, icon: <Layers className="w-3.5 h-3.5" strokeWidth={1.8} /> },
    { labelAr: 'عمر الشاسيه وقابلية الترقية', labelEn: 'Chassis Longevity', score: m?.longevity_score != null ? Number(m.longevity_score) : null, icon: <ShieldCheck className="w-3.5 h-3.5" strokeWidth={1.8} /> },
    { labelAr: 'الراحة والكيبورد (Ergonomics)', labelEn: 'Ergonomics & Typing', score: m?.ergonomics_score != null ? Number(m.ergonomics_score) : null, icon: <Gauge className="w-3.5 h-3.5" strokeWidth={1.8} /> },
    { labelAr: 'تجارب المستخدمين الفعلية', labelEn: 'Real Owner Sentiment', score: m?.community_nlp_score != null ? Number(m.community_nlp_score) : null, icon: <Award className="w-3.5 h-3.5" strokeWidth={1.8} /> },
  ]

  const review5Aspects = [
    { labelAr: 'التبريد تحت الضغط الصيفي', labelEn: 'Cooling under Stress', score: m?.thermals_score != null ? Number(m.thermals_score) : null },
    { labelAr: 'هدوء المراوح والصوت', labelEn: 'Fan Acoustics & Quietness', score: m?.acoustics_score != null ? Number(m.acoustics_score) : null },
    { labelAr: 'متانة الشاسيه والمفصلات', labelEn: 'Chassis & Hinge Durability', score: m?.build_and_hinges_score != null ? Number(m.build_and_hinges_score) : null },
    { labelAr: 'استجابة الكيبورد والتراك باد', labelEn: 'Keyboard & Trackpad Precision', score: m?.keyboard_and_trackpad_score != null ? Number(m.keyboard_and_trackpad_score) : null },
    { labelAr: 'عمر البطارية الحقيقي', labelEn: 'Real Battery Run-Time', score: m?.real_battery_and_reliability_score != null ? Number(m.real_battery_and_reliability_score) : null },
  ]

  const scoreTone = (score: number) =>
    score >= 85 ? 't-gold' : score < 50 ? 't-danger' : 't-primary'

  return (
    <div
      className="modal-backdrop"
      role="dialog"
      aria-modal="true"
      aria-label={title}
      onClick={onClose}
    >
      <div className="modal-frame max-h-[92vh] sm:max-h-[88vh]" onClick={(event) => event.stopPropagation()}>
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
            <h2 dir="auto" className="font-display text-[17px] sm:text-[19px] font-semibold text-[var(--text-primary)] leading-snug line-clamp-2">
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

        {/* Workbench tabs */}
        <div className="modal-tabs" role="tablist" aria-label={isAr ? 'أقسام التفاصيل' : 'Detail sections'}>
          {(
            [
              { key: 'prices', ar: 'الأسعار والمتاجر', en: 'Prices & stores', shortAr: 'الأسعار', shortEn: 'Prices' },
              { key: 'reviews', ar: 'المراجعات والتنازلات', en: 'Reviews & tradeoffs', shortAr: 'المراجعات', shortEn: 'Reviews' },
              { key: 'specs', ar: 'المواصفات الكاملة', en: 'Full specs', shortAr: 'المواصفات', shortEn: 'Specs' },
              { key: 'score', ar: 'تحليل التقييم', en: 'Score breakdown', shortAr: 'التقييم', shortEn: 'Score' },
            ] as const
          ).map((tabDef) => (
            <button
              key={tabDef.key}
              type="button"
              role="tab"
              aria-selected={activeTab === tabDef.key}
              aria-label={isAr ? tabDef.ar : tabDef.en}
              title={isAr ? tabDef.ar : tabDef.en}
              onClick={() => setActiveTab(tabDef.key)}
              className="modal-tab"
            >
              {isAr ? tabDef.shortAr : tabDef.shortEn}
            </button>
          ))}
        </div>

        {/* Scrollable content */}
        <div className="modal-body">
          {activeTab === 'prices' && (
            <>
          {/* Top grid: studio well & pricing comparison */}
          <div className="grid grid-cols-1 sm:grid-cols-12 gap-5">
            <div className="sm:col-span-5 studio-well w-full">
              {(detail?.thumbnail_url || laptop.thumbnail_url) && (
                <img
                  src={detail?.thumbnail_url || laptop.thumbnail_url}
                  alt={title}
                  onError={(e) => {
                    ;(e.target as HTMLElement).style.display = 'none'
                  }}
                />
              )}
            </div>

            <div className="sm:col-span-7 flex flex-col justify-between gap-4 min-w-0">
              <div>
                <span className="micro block">
                  {isAr ? 'أقل سعر متاح في السوق المصري' : 'Lowest Available Market Price'}
                </span>
                <div className="flex items-baseline gap-2 flex-wrap mt-1">
                  <span className="font-display font-bold text-[28px] leading-tight text-[var(--gold-bright)] num">
                    {effectivePrice > 0
                      ? effectivePrice.toLocaleString('en-US')
                      : isAr
                      ? 'السعر عند الطلب'
                      : 'Price on request'}
                  </span>
                  {effectivePrice > 0 && (
                    <span className="text-[13px] font-semibold text-[var(--text-muted)]">
                      {isAr ? 'ج.م' : 'EGP'}
                    </span>
                  )}
                </div>
                {cheapestStore && (
                  <p className="text-[12px] font-medium text-[var(--text-secondary)] mt-0.5">
                    {isAr ? 'أقل سعر في:' : 'Lowest at:'}{' '}
                    <strong className="text-[var(--text-primary)]">{cheapestStore}</strong>
                  </p>
                )}

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
                        ? `وفر ${priceSpread.toLocaleString('en-US')} ج.م مقارنة بأعلى متجر`
                        : `Save ${priceSpread.toLocaleString('en-US')} EGP vs highest store`}
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
                            ? `${off.price_egp.toLocaleString('en-US')} `
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

          {/* Multi-store price history telemetry */}
          <div className="tile-block">
            <PriceHistoryChart laptopId={laptop.canonical_id} lang={lang} />
          </div>
            </>
          )}

          {activeTab === 'specs' && (
            <>
          {/* Operational tiers — omitted entirely when no tier is classified */}
          {activeTiers.length > 0 && (
            <div className="tile-block space-y-3">
              <h4 className="label flex items-center gap-1.5">
                <Award className="w-3.5 h-3.5 text-[var(--cyan)]" strokeWidth={1.8} />
                <span>
                  {isAr ? 'تصنيف الفئات والقدرات التشغيلية للموديل' : 'Hardware Operational Tiers'}
                </span>
              </h4>
              <div className="tier-grid">
                {activeTiers.map((tier, idx) => (
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
          )}


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
                  {detail?.cpu?.full_name || detail?.cpu?.model || '-'}
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
                      {detail?.cpu?.cache_mb ? `${detail.cpu.cache_mb} MB` : '-'}
                    </span>
                  </div>
                  <div>
                    <span className="fl">{isAr ? 'القدرة الأساسية (TDP):' : 'Base Power (TDP):'}</span>
                    <span className="fv num">
                      {detail?.cpu?.base_power_w ? `${detail.cpu.base_power_w}W` : '-'}
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
                    detail?.gpu?.integrated === false
                      ? 'green'
                      : detail?.gpu?.integrated === true
                      ? ''
                      : '!text-[var(--text-muted)]'
                  }`}>
                    {detail?.gpu?.integrated === true
                      ? (isAr ? 'مدمج (iGPU)' : 'Integrated iGPU')
                      : detail?.gpu?.integrated === false
                      ? (isAr ? 'منفصل (Dedicated dGPU)' : 'Dedicated dGPU')
                      : '-'}
                  </span>
                </div>
                <div className="big">
                  {detail?.gpu?.model || '-'}
                </div>
                <div className="spec-fields">
                  <div>
                    <span className="fl">{isAr ? 'سعة ونوع ذاكرة الفيديو:' : 'VRAM Capacity:'}</span>
                    <span className="fv num">
                      {detail?.gpu?.vram_gb
                        ? `${detail.gpu.vram_gb}GB ${detail.gpu.vram_type || ''}`.trim()
                        : detail?.gpu?.integrated === true
                        ? isAr
                          ? 'مشتركة'
                          : 'Shared'
                        : '-'}
                    </span>
                  </div>
                  <div>
                    <span className="fl">{isAr ? 'قدرة الطاقة (TGP / TDP):' : 'Max Power (TGP):'}</span>
                    <span className="fv num">
                      {detail?.gpu?.tdp_w ? `${detail.gpu.tdp_w}W` : '-'}
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
                    {detail?.memory?.memory_type || '-'}
                  </span>
                </div>
                <div className="big">
                  {detail?.memory?.capacity_gb
                    ? `${detail.memory.capacity_gb}GB ${detail.memory.memory_type || ''}`.trim()
                    : '-'}
                </div>
                <div className="spec-fields">
                  <div>
                    <span className="fl">{isAr ? 'تردد وسرعة الذاكرة:' : 'Memory Speed:'}</span>
                    <span className="fv num">{detail?.memory?.speed_mhz ? `${detail.memory.speed_mhz} MHz` : '-'}</span>
                  </div>
                  <div>
                    <span className="fl">{isAr ? 'المنافذ والترقية:' : 'Slots / Expansion:'}</span>
                    <span className="fv num">
                      {detail?.memory?.is_soldered
                        ? isAr ? 'ملحومة باللوحة (Soldered)' : 'Soldered On-board'
                        : detail?.memory?.slot_count ? `${detail.memory.slot_count}x Slots` : '-'}
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
                    {detail?.storage?.storage_type || '-'}
                  </span>
                </div>
                <div className="big">
                  {detail?.storage?.capacity_gb
                    ? `${detail.storage.capacity_gb}GB ${detail.storage.storage_type || 'SSD'}`
                    : '-'}
                </div>
                <div className="spec-fields">
                  <div>
                    <span className="fl">{isAr ? 'واجهة التوصيل:' : 'Interface:'}</span>
                    <span className="fv num">{detail?.storage?.interface || '-'}</span>
                  </div>
                  <div>
                    <span className="fl">{isAr ? 'منافذ M.2 الإضافية:' : 'M.2 Expansion Slots:'}</span>
                    <span className="fv indigo num">
                      {detail?.storage?.slot_count ? `${detail.storage.slot_count}x M.2 Slots` : '-'}
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
                    {detail?.display?.refresh_rate_hz ? `${detail.display.refresh_rate_hz}Hz` : '-'}
                  </span>
                </div>
                <div className="big">
                  {`${detail?.display?.size_inches ? `${detail.display.size_inches}"` : ''} ${
                    detail?.display?.resolution || ''
                  } (${detail?.display?.panel_type || '-'})`.trim()}
                </div>
                <div className="spec-fields">
                  <div>
                    <span className="fl">{isAr ? 'النسبة والسطوع:' : 'Aspect Ratio & Nits:'}</span>
                    <span className="fv num">
                      {detail?.display?.aspect_ratio || '-'} •{' '}
                      {detail?.display?.brightness_nits
                        ? `${detail.display.brightness_nits} nits`
                        : '-'}
                    </span>
                  </div>
                  <div>
                    <span className="fl">{isAr ? 'دقة الألوان واللمس:' : 'Color Gamut & Touch:'}</span>
                    <span className="fv num">
                      {detail?.display?.color_gamut || '-'} •{' '}
                      {detail?.display?.touchscreen === true
                        ? isAr ? 'تدعم اللمس' : 'Touchscreen'
                        : detail?.display?.touchscreen === false
                        ? isAr ? 'غير لمسية' : 'Non-touch'
                        : '-'}
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
                  {detail?.power_battery?.battery_capacity_wh
                    ? `${detail.power_battery.battery_capacity_wh} Wh`
                    : '-'}
                </div>
                <div className="spec-fields">
                  <div>
                    <span className="fl">{isAr ? 'قدرة الشاحن الأصلي:' : 'Adapter Wattage:'}</span>
                    <span className="fv num">{detail?.power_battery?.power_adapter_w ? `${detail.power_battery.power_adapter_w}W` : '-'}</span>
                  </div>
                  <div>
                    <span className="fl">{isAr ? 'شحن تايب سي والشحن السريع:' : 'USB-C PD & Fast Charge:'}</span>
                    <span className="fv num">
                      {detail?.power_battery?.usb_c_pd_charging === true
                        ? isAr ? 'يدعم USB-C PD' : 'USB-C PD Supported'
                        : detail?.power_battery?.usb_c_pd_charging === false
                        ? isAr ? 'منفذ مخصص' : 'Dedicated Port'
                        : '-'}
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
                    ? isAr
                      ? `كيبورد مضيء${detail.build_security.keyboard_backlight_type ? ` (${detail.build_security.keyboard_backlight_type})` : ''}`
                      : `Backlit Keyboard${detail.build_security.keyboard_backlight_type ? ` (${detail.build_security.keyboard_backlight_type})` : ''}`
                    : detail?.build_security?.has_backlit_keyboard === false
                    ? isAr ? 'كيبورد قياسي' : 'Standard Keyboard'
                    : '-'}
                  {detail?.build_security?.has_fingerprint ? (isAr ? ' • بصمة إصبع' : ' • Fingerprint Reader') : ''}
                  {detail?.build_security?.has_copilot_key ? (isAr ? ' • زر Copilot للذكاء الاصطناعي' : ' • Copilot AI Key') : ''}
                </div>
                <div className="spec-fields">
                  <div>
                    <span className="fl">{isAr ? 'الوزن الصافي:' : 'Chassis Weight:'}</span>
                    <span className="fv num">{detail?.physical?.weight_kg ? `${detail.physical.weight_kg} kg` : '-'}</span>
                  </div>
                  <div>
                    <span className="fl">{isAr ? 'الأبعاد بالملم (عرض×عمق×سمك):' : 'Dimensions (W x D x H):'}</span>
                    <span className="fv num">
                      {detail?.physical?.width_mm && detail?.physical?.depth_mm
                        ? `${detail.physical.width_mm} × ${detail.physical.depth_mm}${
                            detail.physical.height_mm ? ` × ${detail.physical.height_mm}` : ''
                          } mm`
                        : '-'}
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
                    {detail?.connectivity_os?.wifi || '-'}
                  </span>
                </div>
                <div className="text-[var(--text-primary)] font-medium text-[13px] leading-relaxed">
                  {detail?.audio_webcam?.webcam_resolution
                    ? `${detail.audio_webcam.webcam_resolution} Webcam`
                    : '-'}
                  {detail?.audio_webcam?.has_privacy_shutter ? (isAr ? ' • غالق خصوصية' : ' • Privacy Shutter') : ''}
                  {detail?.audio_webcam?.has_ir_camera ? (isAr ? ' • كاميرا IR Windows Hello' : ' • IR Windows Hello') : ''}
                </div>
                <div className="spec-fields">
                  <div>
                    <span className="fl">{isAr ? 'نظام الصوت:' : 'Audio Speakers:'}</span>
                    <span className="fv num">
                      {detail?.audio_webcam?.speaker_count
                        ? `${detail.audio_webcam.speaker_count}x Stereo`
                        : '-'}
                      {detail?.audio_webcam?.audio_system ? ` (${detail.audio_webcam.audio_system})` : ''}
                    </span>
                  </div>
                  <div>
                    <span className="fl">{isAr ? 'بلوتوث ومنفذ إيثرنت:' : 'Bluetooth & Ethernet:'}</span>
                    <span className="fv num">
                      {detail?.connectivity_os?.bluetooth || '-'}
                      {detail?.connectivity_os?.has_ethernet === true
                        ? ` • RJ-45${
                            detail.connectivity_os.ethernet_speed
                              ? ` (${detail.connectivity_os.ethernet_speed})`
                              : ''
                          }`
                        : ''}
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

            </>
          )}

          {activeTab === 'score' && (
            <>
          {/* Score breakdown explanation */}
          <div className="tile-block space-y-1.5">
            <h4 className="label">{isAr ? 'إزاي بنحسب نسبة التطابق؟' : 'How is the match score calculated?'}</h4>
            <p dir="auto" className="text-[12.5px] leading-[1.7] text-[var(--text-secondary)]">
              {isAr
                ? 'كل جهاز بياخد درجة من 100 في 10 معايير: المعالج، كارت الشاشة، التبريد والطاقة، الشاشة، سهولة التنقل، عمر الشاسيه والترقية، الراحة والكيبورد، المنافذ، تجارب المستخدمين، والقيمة مقابل السعر. بعدين بنوزن المعايير حسب الاستخدام اللي اخترته — مثلاً الألعاب بتدي وزن أكبر لكارت الشاشة والتبريد، والدراسة بتدي وزن أكبر للبطارية والسعر. النسبة النهائية هي مدى قرب الجهاز من أفضل خيار ممكن داخل ميزانيتك.'
                : 'Every laptop receives 0–100 scores across 10 inputs: CPU, GPU, sustained power & thermals, display, mobility, chassis longevity & upgradability, ergonomics, connectivity, real owner sentiment, and value for money. Those inputs are weighted by the use cases you picked — gaming leans on GPU and thermals, study leans on battery and price. The final percentage reflects how close the laptop sits to the best possible package inside your budget.'}
            </p>
          </div>

          {/* Full 15 performance scores (benchmarks + reviews) */}
          <div className="tile-block space-y-3">
            <button
              type="button"
              onClick={() => setShowAllScores(!showAllScores)}
              className="collapse-toggle"
              aria-expanded={showAllScores || activeTab === 'score'}
            >
              <span className="ct-left">
                <SlidersHorizontal className="w-3.5 h-3.5" strokeWidth={1.8} />
                <span>
                  {isAr
                    ? 'كل معايير التقييم الـ 15 (أداء + مراجعات)'
                    : 'All 15 scoring dimensions (benchmarks + reviews)'}
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

            {(showAllScores || activeTab === 'score') && (
              <div className="space-y-5">
                {/* 10 TOPSIS decision criteria */}
                <div>
                  <span className="micro block mb-2.5">
                    {isAr
                      ? 'المعايير الـ 10 اللي بتحدد نسبة التطابق'
                      : 'The 10 inputs behind your match score'}
                  </span>
                  <div className="criteria-grid">
                    {topsis10Scores.map((sc, i) => (
                      <div key={i} className="crit-tile">
                        <div className="clabel">
                          {sc.icon}
                          <span>{isAr ? sc.labelAr : sc.labelEn}</span>
                        </div>
                        {sc.score != null ? (
                          <>
                            <div className={`cnum num ${scoreTone(sc.score)}`}>
                              {sc.score.toFixed(1)}
                            </div>
                            <div className="mini-track">
                              <div
                                className="mini-fill"
                                style={{ width: `${Math.min(100, Math.max(0, sc.score))}%` }}
                              />
                            </div>
                          </>
                        ) : (
                          <>
                            <div className="cnum num text-[var(--text-muted)]">-</div>
                            <div className="mini-track">
                              <div className="mini-fill" style={{ width: '0%' }} />
                            </div>
                            <span className="text-[10.5px] text-[var(--text-muted)]">
                              {isAr ? 'غير مقيّم' : 'Unrated'}
                            </span>
                          </>
                        )}
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
                          {asp.score != null ? (
                            <span className={`bval num ${scoreTone(asp.score)}`}>
                              {asp.score.toFixed(1)}
                              <small>/100</small>
                            </span>
                          ) : (
                            <span className="bval num text-[var(--text-muted)]">
                              -
                            </span>
                          )}
                        </div>
                        <div className="bar-track">
                          <span className="tick" style={{ left: '50%' }} />
                          <span className="tick" style={{ left: '80%' }} />
                          <div
                            className="bar-fill"
                            style={{
                              width:
                                asp.score != null
                                  ? `${Math.min(100, Math.max(0, asp.score))}%`
                                  : '0%',
                            }}
                          />
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}
          </div>

            </>
          )}

          {activeTab === 'reviews' && (
            <>
          {/* 5 real-world review aspects */}
          <div className="tile-block space-y-3">
            <h4 className="label flex items-center gap-1.5">
              <Video className="w-3.5 h-3.5 text-[var(--text-secondary)]" strokeWidth={1.8} />
              <span>{isAr ? 'تجارب المستخدمين الحقيقية (من 100)' : 'Real-world owner experience (out of 100)'}</span>
            </h4>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-5 gap-y-3">
              {review5Aspects.map((asp, i) => (
                <div key={i} className="bar-row">
                  <div className="bar-head">
                    <span className="blabel truncate">
                      <span className="truncate">{isAr ? asp.labelAr : asp.labelEn}</span>
                    </span>
                    {asp.score != null ? (
                      <span className={`bval num ${scoreTone(asp.score)}`}>
                        {asp.score.toFixed(0)}
                        <small>/100</small>
                      </span>
                    ) : (
                      <span className="bval num text-[var(--text-muted)]">-</span>
                    )}
                  </div>
                  <div className="bar-track">
                    <span className="tick" style={{ left: '50%' }} />
                    <span className="tick" style={{ left: '80%' }} />
                    <div
                      className="bar-fill"
                      style={{ width: asp.score != null ? `${Math.min(100, Math.max(0, asp.score))}%` : '0%' }}
                    />
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Pro & cons */}
          {(pros.length > 0 || cons.length > 0) && (
            <div className="tile-block space-y-3">
              <h4 className="label flex items-center gap-1.5">
                <MessageSquare className="w-3.5 h-3.5 text-[var(--cyan)]" strokeWidth={1.8} />
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

          {/* Honest empty state when zero verified community reviews exist yet */}
          {detail && !loading && !hasVerifiedReviews && (
            <div className="tile-block">
              <div className="rounded-[10px] border border-[var(--border-subtle)] bg-[var(--bg-raised)] px-4 py-3.5 space-y-1.5">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-1.5 text-[13px] font-semibold text-[var(--text-primary)]">
                    <MessageSquare className="w-3.5 h-3.5 text-[var(--text-secondary)]" strokeWidth={1.8} />
                    <span>
                      {isAr ? 'بانتظار مراجعات المستخدمين الموثقة' : 'Pending Verified Community Reviews'}
                    </span>
                  </div>
                  <span className="ai-chip tabular-nums">
                    {isAr ? 'خط أساس محايد • 75.0' : 'Neutral Baseline • 75.0'}
                  </span>
                </div>
                <p dir="auto" className="text-[12.5px] leading-[1.6] text-[var(--text-secondary)]">
                  {isAr
                    ? 'لم يتم العثور على مراجعات يوتيوب أو منتديات موثوقة لهذا الشاسيه حتى الآن. يتم التقييم مؤقتاً على خط أساس محايد (75.0) دون توليد مميزات أو عيوب مصطنعة حتى تتوفر تجارب حقيقية.'
                    : 'No verified YouTube, forum, or editorial reviews have been collected for this chassis yet. Scoring uses a neutral 75.0 baseline without fabricated pros or cons until real owner evidence is available.'}
                </p>
              </div>
            </div>
          )}

          {/* Verified External Review Sources */}
          {reviewSources.length > 0 && (
            <div className="tile-block space-y-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h4 className="label flex items-center gap-1.5">
                  <Video className="w-3.5 h-3.5 text-[var(--text-secondary)]" strokeWidth={1.8} />
                  <span>
                    {isAr ? 'مصادر المراجعات والفيديوهات' : 'Verified Review Sources'}
                  </span>
                </h4>
                <span className="ai-chip tabular-nums">
                  {isAr
                    ? `${reviewSources.length} مصادر موثقة`
                    : `${reviewSources.length} verified sources`}
                </span>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                {visibleReviewSources.map((src, idx) => {
                  const href = safeHttpUrl(src.url)
                  if (!href) return null
                  return (
                    <ReviewSourceCard key={`${href}-${idx}`} src={src} href={href} isAr={isAr} />
                  )
                })}
              </div>

              {reviewSources.length > 6 && (
                <button
                  type="button"
                  onClick={() =>
                    setExpandedSourcesForId(showAllSources ? null : laptop.canonical_id)
                  }
                  className="collapse-toggle"
                  aria-expanded={showAllSources}
                >
                  <span className="ct-left">
                    <MessageSquare className="w-3.5 h-3.5" strokeWidth={1.8} />
                    <span>
                      {showAllSources
                        ? isAr
                          ? 'عرض مصادر أقل'
                          : 'Show fewer review sources'
                        : isAr
                        ? `عرض كل المصادر (${reviewSources.length})`
                        : `Show all ${reviewSources.length} review sources`}
                    </span>
                  </span>
                  <span className="ct-state">
                    {showAllSources ? (
                      <ChevronUp className="w-3.5 h-3.5" />
                    ) : (
                      <ChevronDown className="w-3.5 h-3.5" />
                    )}
                  </span>
                </button>
              )}
            </div>
          )}
            </>
          )}
        </div>

        {/* Modal sticky footer CTA */}
        <div className="modal-footer">
          <div className="text-[12px] text-[var(--text-muted)]">
            {isAr
              ? 'الأسعار والمواصفات محدثة وموثقة مباشرة من المتاجر'
              : 'Real-time verified pricing and specs'}
          </div>
          {cheapestOfferUrl ? (
            <a
              href={cheapestOfferUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="btn btn-primary btn-sm w-full sm:w-auto"
            >
              <span>
                {isAr ? `شوف العرض في ${cheapestStore}` : `View offer at ${cheapestStore}`}
              </span>
              <ExternalLink className="w-3.5 h-3.5" strokeWidth={2} />
            </a>
          ) : (
            <button type="button" disabled className="btn btn-primary btn-sm w-full sm:w-auto">
              <span>{isAr ? 'رابط المتجر غير متاح' : 'Store link unavailable'}</span>
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
