import React, { useState } from 'react'
import {
  ExternalLink,
  CheckCircle,
  XCircle,
  Thermometer,
  Volume2,
  ShieldCheck,
  Keyboard,
  BatteryCharging,
  Store,
  ChevronRight,
  Cpu,
  Monitor,
  Maximize2,
  Sparkles,
  Zap,
  Feather,
  Layers,
  Award,
  SlidersHorizontal,
  ChevronDown,
  ChevronUp,
} from 'lucide-react'
import type { RankedLaptop } from '../types/api'

interface LaptopCardProps {
  laptop: RankedLaptop
  lang: 'ar' | 'en'
  onSelect: (laptop: RankedLaptop) => void
}

export const LaptopCard: React.FC<LaptopCardProps> = ({
  laptop,
  lang,
  onSelect,
}) => {
  const isAr = lang === 'ar'
  const [showAllScores, setShowAllScores] = useState(false)

  const pros = isAr ? laptop.pros_ar : laptop.pros_en
  const cons = isAr ? laptop.cons_ar : laptop.cons_en
  const whyList = isAr ? laptop.why_recommended_ar : laptop.why_recommended_en

  // 10 TOPSIS Hardware Benchmark Scores
  const topsis = laptop.topsis_inputs
  const topsis10Scores = [
    { key: 'cpu', labelAr: 'قوة المعالج (CPU)', labelEn: 'CPU Benchmark', score: topsis?.cpu_score ?? 70, icon: <Cpu className="w-3 h-3" strokeWidth={1.8} /> },
    { key: 'gpu', labelAr: 'أداء الجرافيكس (GPU)', labelEn: 'GPU 3D Power', score: topsis?.gpu_score ?? 65, icon: <Monitor className="w-3 h-3" strokeWidth={1.8} /> },
    { key: 'display', labelAr: 'الشاشة والسرعة', labelEn: 'Display Quality', score: topsis?.display_score ?? 72, icon: <Maximize2 className="w-3 h-3" strokeWidth={1.8} /> },
    { key: 'value', labelAr: 'القيمة مقابل السعر', labelEn: 'Value for Money', score: topsis?.value_score ?? 85, icon: <Sparkles className="w-3 h-3" strokeWidth={1.8} /> },
    { key: 'power_therm', labelAr: 'استقرار الطاقة والتبريد', labelEn: 'Sustained Power & Thermal', score: topsis?.power_therm_score ?? 80, icon: <Zap className="w-3 h-3" strokeWidth={1.8} /> },
    { key: 'mobility', labelAr: 'سهولة التنقل والوزن', labelEn: 'Mobility & Battery', score: topsis?.mobility_score ?? 60, icon: <Feather className="w-3 h-3" strokeWidth={1.8} /> },
    { key: 'connectivity', labelAr: 'المنافذ والاتصال', labelEn: 'I/O & Connectivity', score: topsis?.connectivity_score ?? 75, icon: <Layers className="w-3 h-3" strokeWidth={1.8} /> },
    { key: 'longevity', labelAr: 'عمر الشاسيه والترقية', labelEn: 'Chassis & Expansion', score: topsis?.longevity_score ?? 78, icon: <ShieldCheck className="w-3 h-3" strokeWidth={1.8} /> },
    { key: 'ergonomics', labelAr: 'الراحة والكيبورد', labelEn: 'Ergonomics & Typing', score: topsis?.ergonomics_score ?? 74, icon: <Keyboard className="w-3 h-3" strokeWidth={1.8} /> },
    { key: 'community_nlp', labelAr: 'رضا المستخدمين', labelEn: 'Community Sentiment', score: topsis?.community_nlp_score ?? 79, icon: <Award className="w-3 h-3" strokeWidth={1.8} /> },
  ]

  // 5 Review Intelligence Aspects
  const aspects = [
    {
      key: 'thermals',
      labelAr: 'التبريد تحت الضغط',
      labelEn: 'Thermals Under Stress',
      score: laptop.aspect_scores?.thermals_score || 75,
      icon: <Thermometer className="w-3 h-3" strokeWidth={1.8} />,
    },
    {
      key: 'acoustics',
      labelAr: 'الهدوء وصوت المراوح',
      labelEn: 'Fan Acoustics',
      score: laptop.aspect_scores?.acoustics_score || 75,
      icon: <Volume2 className="w-3 h-3" strokeWidth={1.8} />,
    },
    {
      key: 'build',
      labelAr: 'متانة الشاسيه والمفصلات',
      labelEn: 'Chassis & Hinges',
      score: laptop.aspect_scores?.build_and_hinges_score || 75,
      icon: <ShieldCheck className="w-3 h-3" strokeWidth={1.8} />,
    },
    {
      key: 'keyboard',
      labelAr: 'استجابة الكيبورد',
      labelEn: 'Keyboard & Trackpad',
      score: laptop.aspect_scores?.keyboard_and_trackpad_score || 75,
      icon: <Keyboard className="w-3 h-3" strokeWidth={1.8} />,
    },
    {
      key: 'battery',
      labelAr: 'عمر البطارية الحقيقي',
      labelEn: 'Real Battery Life',
      score: laptop.aspect_scores?.real_battery_and_reliability_score || 75,
      icon: <BatteryCharging className="w-3 h-3" strokeWidth={1.8} />,
    },
  ]

  const scoreTone = (score: number) =>
    score >= 85
      ? 't-gold'
      : score < 50
      ? 't-danger'
      : 't-primary'

  return (
    <article className="result-card">
      {/* Head: rank, brand, model, TOPSIS badge */}
      <div className="rc-head">
        <div className="left">
          <span className="rank-chip">#{laptop.rank}</span>
          <span className="brand-chip">{laptop.brand}</span>
          <h3 className="model">
            {laptop.laptop_family} {laptop.laptop_model}
          </h3>
        </div>
        <span className="topsis-badge">
          <span className="pct num">{laptop.topsis_match_score.toFixed(1)}%</span>
          <span className="lbl">{isAr ? 'تطابق TOPSIS' : 'TOPSIS Match'}</span>
        </span>
      </div>

      {/* Media: studio well + description/bullets */}
      <div className="rc-media">
        <div className="studio-well">
          <img
            src={laptop.thumbnail_url}
            alt={laptop.title}
            onError={(e) => {
              ;(e.target as HTMLElement).style.display = 'none'
            }}
          />
        </div>

        <div className="min-w-0">
          <p className="rc-desc line-clamp-3">{laptop.title}</p>

          {whyList && whyList.length > 0 && (
            <ul className="spec-bullets">
              {whyList.slice(0, 3).map((item, idx) => (
                <li key={idx}>
                  <span className="line-clamp-2">{item}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      {/* Stores */}
      <div className="rc-stores">
        <span className="micro flex items-center gap-1.5">
          <Store className="w-3 h-3" strokeWidth={1.8} />
          {isAr ? 'المتاجر' : 'Stores'}
        </span>
        {Object.entries(laptop.prices_by_store || {}).map(([store, price]) => {
          const isCheapest = store.toLowerCase() === laptop.cheapest_store.toLowerCase()
          return (
            <span key={store} className="store-chip">
              <span className="sname">{store}:</span>
              <span className="sprice num">{price.toLocaleString()} EGP</span>
              {isCheapest && (
                <span className="best-chip">{isAr ? 'الأرخص' : 'Best Price'}</span>
              )}
            </span>
          )
        })}
      </div>

      {/* Pros & Cons */}
      <div className="proscons">
        <div className="pc pros">
          <h4>
            <CheckCircle className="w-3.5 h-3.5" strokeWidth={2} />
            <span>{isAr ? 'نقاط القوة لدى المستخدمين' : 'Community Pros'}</span>
          </h4>
          <ul>
            {(pros || []).slice(0, 2).map((pro, i) => (
              <li key={i}>
                <span className="mk">✓</span>
                <span className="line-clamp-3">{pro}</span>
              </li>
            ))}
          </ul>
        </div>

        <div className="pc cons">
          <h4>
            <XCircle className="w-3.5 h-3.5" strokeWidth={2} />
            <span>{isAr ? 'العيوب والملاحظات' : 'Community Cons'}</span>
          </h4>
          <ul>
            {(cons || []).slice(0, 2).map((con, i) => (
              <li key={i}>
                <span className="mk">✕</span>
                <span className="line-clamp-3">{con}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>

      {/* Community aspect scores */}
      <div className="mt-5">
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <span className="label">
            {isAr ? 'مؤشرات التقييم الميداني (من 100)' : 'Community Aspect Scores (out of 100)'}
          </span>
          <span className="font-mono text-[11px] text-[var(--text-muted)]">
            {laptop.reviews_evidence_count > 0
              ? isAr
                ? `${laptop.reviews_evidence_count} مراجعة موثقة`
                : `${laptop.reviews_evidence_count} verified reviews`
              : isAr
              ? 'تقديرات الخبراء'
              : 'Benchmark estimate'}
          </span>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-x-4 gap-y-3 mt-3">
          {aspects.map((asp) => (
            <div key={asp.key} className="bar-row">
              <div className="bar-head">
                <span className="blabel truncate">
                  {asp.icon}
                  <span className="truncate">{isAr ? asp.labelAr : asp.labelEn}</span>
                </span>
                <span className={`bval num ${scoreTone(asp.score)}`}>{asp.score.toFixed(0)}</span>
              </div>
              <div className="bar-track">
                <div
                  className="bar-fill"
                  style={{ width: `${Math.min(100, Math.max(0, asp.score))}%` }}
                />
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Progressive disclosure: 10 TOPSIS criteria */}
      <div className="mt-4 border-t border-[var(--border-subtle)] pt-2">
        <button
          type="button"
          onClick={() => setShowAllScores(!showAllScores)}
          className="collapse-toggle"
          aria-expanded={showAllScores}
        >
          <span className="ct-left">
            <SlidersHorizontal className="w-3.5 h-3.5" strokeWidth={1.8} />
            <span>
              {showAllScores
                ? isAr
                  ? 'إخفاء المعايير التفصيلية'
                  : 'Hide detailed criteria'
                : isAr
                ? 'عرض كافة مؤشرات الأداء والعتاد (TOPSIS)'
                : 'View detailed criteria (TOPSIS)'}
            </span>
          </span>
          <span className="ct-state">
            {showAllScores ? (
              <ChevronUp className="w-3.5 h-3.5" />
            ) : (
              <ChevronDown className="w-3.5 h-3.5" />
            )}
          </span>
        </button>

        {showAllScores && (
          <div className="pt-3 space-y-2.5">
            <span className="micro block">
              {isAr
                ? 'المعايير الهندسية والعتاد الـ 10 (TOPSIS)'
                : '10 Hardware Decision Criteria (TOPSIS)'}
            </span>
            <div className="criteria-grid">
              {topsis10Scores.map((sc) => (
                <div key={sc.key} className="crit-tile">
                  <div className="clabel">
                    {sc.icon}
                    <span>{isAr ? sc.labelAr : sc.labelEn}</span>
                  </div>
                  <div className={`cnum num ${scoreTone(sc.score)}`}>
                    {sc.score.toFixed(0)}
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
        )}
      </div>

      {/* Footer: price + CTAs */}
      <div className="rc-foot">
        <div className="price-block">
          <div className="micro">
            {isAr ? 'أفضل سعر مسجل' : 'Cheapest Recorded Price'}
          </div>
          <div className="amt">
            {laptop.effective_price_egp.toLocaleString()}{' '}
            <small>
              {isAr ? 'ج.م' : 'EGP'} ({isAr ? 'عبر' : 'via'} {laptop.cheapest_store})
            </small>
          </div>
        </div>

        <div className="foot-btns">
          <button
            type="button"
            onClick={() => onSelect(laptop)}
            className="btn btn-secondary btn-sm"
          >
            <span>{isAr ? 'المواصفات الكاملة' : 'Full Specs'}</span>
            <ChevronRight className="w-3.5 h-3.5" strokeWidth={2} />
          </button>

          <a
            href={laptop.cheapest_offer_url}
            target="_blank"
            rel="noopener noreferrer"
            className="btn btn-primary btn-sm"
          >
            <span>{isAr ? 'شراء من المتجر' : 'Visit Store'}</span>
            <ExternalLink className="w-3.5 h-3.5" strokeWidth={2} />
          </a>
        </div>
      </div>
    </article>
  )
}
