import React, { useState } from 'react'
import {
  ExternalLink,
  CheckCircle,
  AlertTriangle,
  Store,
  ChevronDown,
  ChevronUp,
  Search,
  Scale,
  Check,
} from 'lucide-react'
import type { RankedLaptop } from '../types/api'
import {
  computeStoreSavings,
  extractQuickSpecs,
  formatCardTitle,
} from '../utils/laptopSummary'
import { isPlaceholderPrice, isValidDisplayPrice } from '../utils/availability'
import { ShareButton } from './ShareButton'

interface LaptopCardProps {
  laptop: RankedLaptop
  lang: 'ar' | 'en'
  onSelect: (laptop: RankedLaptop) => void
  isCompared?: boolean
  compareDisabled?: boolean
  onToggleCompare?: (laptop: RankedLaptop) => void
}

const egp = (value: number) => value.toLocaleString('en-US')

export const LaptopCard: React.FC<LaptopCardProps> = ({
  laptop,
  lang,
  onSelect,
  isCompared = false,
  compareDisabled = false,
  onToggleCompare,
}) => {
  const isAr = lang === 'ar'
  const [showStores, setShowStores] = useState(false)

  const pros = isAr ? laptop.pros_ar : laptop.pros_en
  const cons = isAr ? laptop.cons_ar : laptop.cons_en
  const whyList = isAr ? laptop.why_recommended_ar : laptop.why_recommended_en
  const quickSpecs = extractQuickSpecs(laptop.title)
  const hasValidPrice = isValidDisplayPrice(laptop.effective_price_egp)
  const isComingSoon = isPlaceholderPrice(laptop.effective_price_egp)
  const savings = computeStoreSavings(laptop)
  const showSavings = hasValidPrice && savings.storeCount >= 2 && savings.savingsEgp >= 200

  const storeEntries = Object.entries(laptop.prices_by_store || {})
    .filter(([, price]) => typeof price === 'number' && price > 0)
    .sort(([, a], [, b]) => a - b)

  return (
    <article className="result-card">
      {/* Header */}
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1 space-y-1">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="rank-chip">
              {laptop.rank === 1
                ? isAr
                  ? '#1 الأفضل لك'
                  : '#1 Best for you'
                : `#${laptop.rank}`}
            </span>
            <span className="brand-chip">{laptop.brand}</span>
            {!hasValidPrice && (
              <span
                className={`inline-flex items-center rounded-md border px-2 py-0.5 text-[12px] font-semibold ${
                  isComingSoon
                    ? 'border-[var(--warning)] bg-[var(--warning-dim)] text-[var(--warning)]'
                    : 'border-[var(--danger)] bg-[var(--danger-dim)] text-[var(--danger)]'
                }`}
              >
                {isComingSoon ? (isAr ? 'قريباً' : 'Coming soon') : isAr ? 'غير متوفر' : 'Out of stock'}
              </span>
            )}
          </div>
          <h3 dir="auto" className="model">
            {formatCardTitle(laptop.brand, laptop.laptop_family, laptop.laptop_model)}
          </h3>
        </div>

        <span className="topsis-badge shrink-0">
          <span className="pct num">{laptop.topsis_match_score.toFixed(0)}%</span>
          <span className="lbl">{isAr ? 'تطابق' : 'Fit'}</span>
        </span>
      </div>

      {/* Hero row */}
      <div className="rc-media">
        <div className="studio-well">
          <img
            src={laptop.thumbnail_url}
            alt={laptop.title}
            loading="lazy"
            onError={(e) => {
              ;(e.target as HTMLElement).style.display = 'none'
            }}
          />
        </div>

        <div className="min-w-0 space-y-2.5">
          {quickSpecs.length > 0 ? (
            <div className="flex flex-wrap gap-1.5">
              {quickSpecs.map((chip) => (
                <span
                  key={chip}
                  dir="ltr"
                  className="inline-flex items-center rounded-md border border-[var(--border-subtle)] bg-[var(--bg-input)] px-2 py-1 text-[12px] font-mono tabular-nums text-[var(--text-secondary)]"
                >
                  {chip}
                </span>
              ))}
            </div>
          ) : (
            <p dir="auto" className="text-[13px] leading-[1.6] text-[var(--text-secondary)] line-clamp-2">
              {laptop.title}
            </p>
          )}
        </div>
      </div>

      {whyList && whyList.length > 0 && (
        <ul className="spec-bullets">
          {whyList.slice(0, 2).map((item, idx) => (
            <li key={idx}>
              <span dir="auto" className="line-clamp-2">
                {item}
              </span>
            </li>
          ))}
        </ul>
      )}

      {/* Price & savings */}
      <div className="rounded-[10px] border border-[var(--border-subtle)] bg-[var(--bg-input)] px-3.5 py-3 space-y-2">
        <div className="flex flex-wrap items-end justify-between gap-x-3 gap-y-2">
          <div>
            <div className="micro">
              {hasValidPrice ? (isAr ? 'أقل سعر حالي' : 'Current lowest price') : isAr ? 'حالة التوفر' : 'Availability'}
            </div>
            {hasValidPrice ? (
              <div className="flex items-baseline gap-1.5">
                <span className="font-display text-[24px] font-bold tabular-nums text-[var(--text-primary)]">
                  {egp(laptop.effective_price_egp)}
                </span>
                <span className="text-[12px] text-[var(--text-muted)]">{isAr ? 'ج.م' : 'EGP'}</span>
              </div>
            ) : (
              <div className={`font-display text-[18px] font-bold ${isComingSoon ? 'text-[var(--warning)]' : 'text-[var(--danger)]'}`}>
                {isComingSoon
                  ? isAr
                    ? 'قريباً / السعر غير محدد'
                    : 'Coming soon'
                  : isAr
                  ? 'غير متوفر حالياً'
                  : 'Out of stock'}
              </div>
            )}
            <div className="text-[12px] text-[var(--text-secondary)]">
              {hasValidPrice ? (isAr ? 'أقل سعر في:' : 'Lowest at:') : isAr ? 'المتجر:' : 'Store:'}{' '}
              <strong className="text-[var(--text-primary)]">{laptop.cheapest_store}</strong>
            </div>
          </div>

          {showSavings && (
            <div className="space-y-1">
              <span className="inline-flex items-center gap-1.5 rounded-full border border-[var(--success)] bg-[var(--success-dim)] px-2.5 py-1 text-[12px] font-semibold text-[var(--success)]">
                {isAr ? `وفّر ${egp(savings.savingsEgp)} ج.م` : `Save ${egp(savings.savingsEgp)} EGP`}
              </span>
              <p className="text-[12px] text-[var(--text-muted)] tabular-nums">
                {isAr
                  ? `متوفر في ${savings.storeCount} متاجر (حتى ${egp(savings.maxPrice)} ج.م)`
                  : `Available at ${savings.storeCount} stores (up to ${egp(savings.maxPrice)} EGP)`}
              </p>
            </div>
          )}
        </div>

        {storeEntries.length > 1 && (
          <div>
            <button
              type="button"
              onClick={() => setShowStores(!showStores)}
              className="collapse-toggle !min-h-0 !py-1"
              aria-expanded={showStores}
            >
              <span className="ct-left">
                <Store className="w-3.5 h-3.5" strokeWidth={1.8} />
                <span>
                  {showStores
                    ? isAr
                      ? 'إخفاء أسعار المتاجر'
                      : 'Hide store prices'
                    : isAr
                    ? `كل أسعار المتاجر (${storeEntries.length})`
                    : `All store prices (${storeEntries.length})`}
                </span>
              </span>
              <span className="ct-state">
                {showStores ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
              </span>
            </button>

            {showStores && (
              <ul className="mt-1.5 space-y-1">
                {storeEntries.map(([store, price]) => {
                  const isCheapest =
                    store.toLowerCase() === (laptop.cheapest_store || '').toLowerCase()
                  return (
                    <li
                      key={store}
                      className="flex items-center justify-between gap-2 text-[12px] py-0.5"
                    >
                      <span className="flex items-center gap-1.5 text-[var(--text-secondary)]">
                        {store}
                        {isCheapest && (
                          <span className="best-chip">{isAr ? 'الأرخص' : 'Cheapest'}</span>
                        )}
                      </span>
                      <span className="font-mono tabular-nums text-[var(--text-primary)]">
                        {egp(price)} {isAr ? 'ج.م' : 'EGP'}
                      </span>
                    </li>
                  )
                })}
              </ul>
            )}
          </div>
        )}
      </div>

      {/* Honest tradeoffs */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
        <div className="pc pros">
          <h4>
            <CheckCircle className="w-3.5 h-3.5" strokeWidth={2} />
            <span>{isAr ? 'نقاط القوة' : 'Strengths'}</span>
          </h4>
          <ul>
            {(pros || []).slice(0, 2).map((pro, i) => (
              <li key={i}>
                <span className="mk">✓</span>
                <span dir="auto" className="line-clamp-2">
                  {pro}
                </span>
              </li>
            ))}
            {(pros || []).length === 0 && (
              <li>
                <span className="mk">·</span>
                <span className="text-[var(--text-muted)]">
                  {isAr ? 'لا توجد نقاط قوة مسجلة بعد' : 'No recorded strengths yet'}
                </span>
              </li>
            )}
          </ul>
        </div>

        <div className="pc cons">
          <h4>
            <AlertTriangle className="w-3.5 h-3.5" strokeWidth={2} />
            <span>{isAr ? 'خد بالك — التنازلات' : 'Watch out — tradeoffs'}</span>
          </h4>
          <ul>
            {(cons || []).slice(0, 2).map((con, i) => (
              <li key={i}>
                <span className="mk">!</span>
                <span dir="auto" className="line-clamp-2">
                  {con}
                </span>
              </li>
            ))}
            {(cons || []).length === 0 && (
              <li>
                <span className="mk">·</span>
                <span className="text-[var(--text-muted)]">
                  {isAr
                    ? 'لا توجد عيوب شائعة مسجلة في المراجعات'
                    : 'No common flaws recorded in reviews'}
                </span>
              </li>
            )}
          </ul>
        </div>
      </div>

      <p className="text-[12px] text-[var(--text-muted)]">
        {laptop.reviews_evidence_count > 0
          ? isAr
            ? `مبني على ${laptop.reviews_evidence_count.toLocaleString('en-US')} مراجعة حقيقية`
            : `Based on ${laptop.reviews_evidence_count.toLocaleString('en-US')} real reviews`
          : isAr
          ? 'بيانات مواصفات المتاجر فقط — بدون مراجعات مجتمع بعد'
          : 'Store spec data only — no community reviews yet'}
      </p>

      {/* Actions */}
      <div className="rc-foot">
        <a
          href={laptop.cheapest_offer_url}
          target="_blank"
          rel="noopener noreferrer"
          className={`btn btn-sm flex-1 min-h-[42px] ${hasValidPrice ? 'btn-primary' : 'btn-secondary'}`}
        >
          <span>
            {hasValidPrice
              ? isAr
                ? `اعرض السعر في ${laptop.cheapest_store}`
                : `View price at ${laptop.cheapest_store}`
              : isAr
              ? `تحقق في ${laptop.cheapest_store}`
              : `Check at ${laptop.cheapest_store}`}
          </span>
          <ExternalLink className="w-3.5 h-3.5" strokeWidth={2} />
        </a>

        <div className="foot-btns flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => onSelect(laptop)}
            className="btn btn-secondary btn-sm min-h-[42px]"
          >
            <Search className="w-3.5 h-3.5" strokeWidth={2} />
            <span>{isAr ? 'المواصفات والمراجعة الكاملة' : 'Full specs & reviews'}</span>
          </button>

          {onToggleCompare && (
            <button
              type="button"
              onClick={() => onToggleCompare(laptop)}
              disabled={!isCompared && compareDisabled}
              aria-pressed={isCompared}
              className={`btn btn-sm min-h-[42px] ${
                isCompared
                  ? 'border border-[var(--gold)] bg-[var(--gold-dim)] text-[var(--gold-bright)]'
                  : 'btn-secondary'
              }`}
              title={
                !isCompared && compareDisabled
                  ? isAr
                    ? 'الحد الأقصى 3 أجهزة للمقارنة'
                    : 'Compare up to 3 laptops'
                  : undefined
              }
            >
              {isCompared ? <Check className="w-3.5 h-3.5" strokeWidth={2.5} /> : <Scale className="w-3.5 h-3.5" strokeWidth={2} />}
              <span>{isAr ? 'قارن' : 'Compare'}</span>
            </button>
          )}

          <ShareButton
            canonicalId={laptop.canonical_id}
            title={formatCardTitle(laptop.brand, laptop.laptop_family, laptop.laptop_model)}
            priceEgp={laptop.effective_price_egp}
            cheapestStore={laptop.cheapest_store}
            lang={lang}
          />
        </div>
      </div>
    </article>
  )
}
