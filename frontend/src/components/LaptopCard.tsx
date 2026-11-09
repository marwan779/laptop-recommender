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
    { key: 'cpu', labelAr: 'قوة المعالج (CPU)', labelEn: 'CPU Benchmark', score: topsis?.cpu_score ?? 70, icon: <Cpu className="w-3.5 h-3.5 text-indigo-400" /> },
    { key: 'gpu', labelAr: 'أداء الجرافيكس (GPU)', labelEn: 'GPU 3D Power', score: topsis?.gpu_score ?? 65, icon: <Monitor className="w-3.5 h-3.5 text-violet-400" /> },
    { key: 'display', labelAr: 'الشاشة والسرعة', labelEn: 'Display Quality', score: topsis?.display_score ?? 72, icon: <Maximize2 className="w-3.5 h-3.5 text-sky-400" /> },
    { key: 'value', labelAr: 'القيمة مقابل السعر', labelEn: 'Value for Money', score: topsis?.value_score ?? 85, icon: <Sparkles className="w-3.5 h-3.5 text-emerald-400" /> },
    { key: 'power_therm', labelAr: 'استقرار الطاقة والتبريد', labelEn: 'Sustained Power & Thermals', score: topsis?.power_therm_score ?? 80, icon: <Zap className="w-3.5 h-3.5 text-rose-400" /> },
    { key: 'mobility', labelAr: 'سهولة التنقل والوزن', labelEn: 'Mobility & Battery', score: topsis?.mobility_score ?? 60, icon: <Feather className="w-3.5 h-3.5 text-teal-400" /> },
    { key: 'connectivity', labelAr: 'المنافذ والاتصال', labelEn: 'I/O & Connectivity', score: topsis?.connectivity_score ?? 75, icon: <Layers className="w-3.5 h-3.5 text-blue-400" /> },
    { key: 'longevity', labelAr: 'عمر الشاسيه والترقية', labelEn: 'Chassis & Expansion', score: topsis?.longevity_score ?? 78, icon: <ShieldCheck className="w-3.5 h-3.5 text-amber-400" /> },
    { key: 'ergonomics', labelAr: 'الراحة والكيبورد', labelEn: 'Ergonomics & Typing', score: topsis?.ergonomics_score ?? 74, icon: <Keyboard className="w-3.5 h-3.5 text-indigo-300" /> },
    { key: 'community_nlp', labelAr: 'رضا المستخدمين', labelEn: 'Community Sentiment', score: topsis?.community_nlp_score ?? 79, icon: <Award className="w-3.5 h-3.5 text-emerald-300" /> },
  ]

  // 5 Review Intelligence Aspects
  const aspects = [
    {
      key: 'thermals',
      labelAr: 'التبريد تحت الضغط',
      labelEn: 'Thermals Under Stress',
      score: laptop.aspect_scores?.thermals_score || 75,
      icon: <Thermometer className="w-3 h-3 text-rose-400" />,
      color: 'from-rose-500 to-orange-400',
    },
    {
      key: 'acoustics',
      labelAr: 'الهدوء وصوت المراوح',
      labelEn: 'Fan Acoustics',
      score: laptop.aspect_scores?.acoustics_score || 75,
      icon: <Volume2 className="w-3 h-3 text-cyan-400" />,
      color: 'from-cyan-500 to-sky-400',
    },
    {
      key: 'build',
      labelAr: 'متانة الشاسيه والمفصلات',
      labelEn: 'Chassis & Hinges',
      score: laptop.aspect_scores?.build_and_hinges_score || 75,
      icon: <ShieldCheck className="w-3 h-3 text-emerald-400" />,
      color: 'from-emerald-500 to-teal-400',
    },
    {
      key: 'keyboard',
      labelAr: 'استجابة الكيبورد',
      labelEn: 'Keyboard & Trackpad',
      score: laptop.aspect_scores?.keyboard_and_trackpad_score || 75,
      icon: <Keyboard className="w-3 h-3 text-amber-400" />,
      color: 'from-amber-500 to-yellow-400',
    },
    {
      key: 'battery',
      labelAr: 'عمر البطارية الحقيقي',
      labelEn: 'Real Battery Life',
      score: laptop.aspect_scores?.real_battery_and_reliability_score || 75,
      icon: <BatteryCharging className="w-3 h-3 text-blue-400" />,
      color: 'from-indigo-500 to-violet-400',
    },
  ]

  const getScoreColor = (score: number) => {
    if (score >= 80) return 'from-emerald-500 to-teal-400'
    if (score >= 65) return 'from-indigo-500 to-sky-400'
    return 'from-amber-500 to-orange-400'
  }

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-3xl p-5 sm:p-6 shadow-xl hover:border-slate-700 transition-all flex flex-col justify-between group relative overflow-hidden">
      {/* Top row: Rank, Match Score, Brand */}
      <div className="flex items-start justify-between gap-4 mb-4">
        <div className="flex items-center gap-2.5">
          <span className="w-7 h-7 rounded-xl bg-slate-800 text-indigo-400 font-mono font-bold text-xs flex items-center justify-center border border-slate-700 shrink-0">
            #{laptop.rank}
          </span>
          <div>
            <span className="text-xs font-bold text-indigo-400 uppercase tracking-wider">
              {laptop.brand}
            </span>
            <h3 className="font-bold text-white text-base group-hover:text-indigo-300 transition-colors line-clamp-1">
              {laptop.laptop_family} {laptop.laptop_model}
            </h3>
          </div>
        </div>

        {/* Match Score Badge */}
        <div className="flex flex-col items-end shrink-0">
          <div className="px-3 py-1.5 rounded-xl bg-gradient-to-r from-indigo-500/20 to-violet-500/20 border border-indigo-500/40 text-indigo-300 font-extrabold text-sm flex items-center gap-1.5 shadow-sm">
            <span>{laptop.topsis_match_score.toFixed(1)}%</span>
            <span className="text-[10px] font-normal text-slate-400">
              {isAr ? 'تطابق TOPSIS' : 'TOPSIS Match'}
            </span>
          </div>
        </div>
      </div>

      {/* Middle row: Thumbnail & Headline */}
      <div className="grid grid-cols-1 md:grid-cols-12 gap-6 mb-5">
        {/* Thumbnail - Clean white retail display */}
        <div className="md:col-span-4 flex items-center justify-center bg-white rounded-2xl p-4 border border-slate-700/40 h-56 sm:h-64 relative overflow-hidden shadow-inner group-hover:shadow-indigo-500/10 transition-all">
          <img
            src={laptop.thumbnail_url}
            alt={laptop.title}
            className="w-full h-full max-h-52 object-contain group-hover:scale-105 transition-transform duration-300"
            onError={(e) => {
              ;(e.target as HTMLElement).style.display = 'none'
            }}
          />
        </div>

        {/* Core specs & Why Recommended */}
        <div className="md:col-span-8 flex flex-col justify-between space-y-3">
          <p className="text-xs text-slate-300 leading-relaxed line-clamp-2">
            {laptop.title}
          </p>

          {/* Why Recommended Bullets */}
          {whyList && whyList.length > 0 && (
            <div className="space-y-1.5 bg-slate-950/40 p-3 rounded-xl border border-slate-800/60">
              {whyList.slice(0, 3).map((item, idx) => (
                <div key={idx} className="flex items-start gap-2 text-xs text-slate-300">
                  <span className="text-indigo-400 mt-0.5">•</span>
                  <span className="line-clamp-1">{item}</span>
                </div>
              ))}
            </div>
          )}

          {/* Multi-Store Comparison Pills */}
          <div className="flex flex-wrap items-center gap-2 pt-1">
            <span className="text-[11px] text-slate-500 flex items-center gap-1">
              <Store className="w-3 h-3" />
              {isAr ? 'الأسعار في المتاجر:' : 'Stores:'}
            </span>
            {Object.entries(laptop.prices_by_store || {}).map(([store, price]) => {
              const isCheapest = store.toLowerCase() === laptop.cheapest_store.toLowerCase()
              return (
                <span
                  key={store}
                  className={`text-[11px] px-2.5 py-0.5 rounded-lg border font-mono ${
                    isCheapest
                      ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400 font-semibold'
                      : 'bg-slate-800/60 border-slate-700/60 text-slate-400'
                  }`}
                >
                  {store}: {price.toLocaleString()} EGP
                </span>
              )
            })}
          </div>
        </div>
      </div>

      {/* Community Pros & Cons (1:1 Aligned) */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-4 pt-3 border-t border-slate-800/80">
        {/* Pros */}
        <div className="space-y-1.5">
          <span className="text-[11px] font-bold text-emerald-400 flex items-center gap-1">
            <CheckCircle className="w-3 h-3" />
            <span>{isAr ? 'نقاط القوة حسب تقييمات المستخدمين' : 'Community Pros'}</span>
          </span>
          <div className="space-y-1">
            {(pros || []).slice(0, 2).map((pro, i) => (
              <div key={i} className="text-xs text-slate-300 flex items-start gap-1.5">
                <span className="text-emerald-500 text-[10px] mt-0.5 font-bold">✓</span>
                <span className="line-clamp-2 text-slate-300/90">{pro}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Cons */}
        <div className="space-y-1.5">
          <span className="text-[11px] font-bold text-rose-400 flex items-center gap-1">
            <XCircle className="w-3 h-3" />
            <span>{isAr ? 'العيوب والملاحظات الفنية' : 'Community Cons'}</span>
          </span>
          <div className="space-y-1">
            {(cons || []).slice(0, 2).map((con, i) => (
              <div key={i} className="text-xs text-slate-300 flex items-start gap-1.5">
                <span className="text-rose-500 text-[10px] mt-0.5 font-bold">✕</span>
                <span className="line-clamp-2 text-slate-300/90">{con}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Progressive Disclosure Section: 15 Total Metrics */}
      <div className="space-y-2 mb-4 bg-slate-950/40 p-3.5 rounded-2xl border border-slate-800/60">
        {/* Default Compact 5 Aspect Bars */}
        <div className="flex items-center justify-between text-[11px] text-slate-400 font-semibold mb-1">
          <span>{isAr ? 'مؤشرات التقييم الميداني (من 100):' : 'Community Aspect Scores (out of 100):'}</span>
          <span className="text-[10px] font-normal text-slate-400">
            {laptop.reviews_evidence_count > 0
              ? isAr
                ? `مبني على ${laptop.reviews_evidence_count} مراجعة موثقة`
                : `Based on ${laptop.reviews_evidence_count} verified reviews`
              : isAr
              ? 'تقديرات الخبراء'
              : 'Benchmark estimate'}
          </span>
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-5 gap-2.5">
          {aspects.map((asp) => (
            <div key={asp.key} className="space-y-1">
              <div className="flex items-center justify-between text-[10px] text-slate-400">
                <span className="flex items-center gap-1">
                  {asp.icon}
                  {isAr ? asp.labelAr : asp.labelEn}
                </span>
                <span className="font-mono font-bold text-slate-300">{asp.score.toFixed(0)}</span>
              </div>
              <div className="w-full bg-slate-800 h-1.5 rounded-full overflow-hidden">
                <div
                  className={`h-full rounded-full bg-gradient-to-r ${getScoreColor(asp.score)}`}
                  style={{ width: `${Math.min(100, Math.max(10, asp.score))}%` }}
                />
              </div>
            </div>
          ))}
        </div>

        {/* Interactive Expander for all 15 dimensions */}
        <div className="pt-2 border-t border-slate-800/60">
          <button
            type="button"
            onClick={() => setShowAllScores(!showAllScores)}
            className="w-full flex items-center justify-between text-xs text-indigo-400 hover:text-indigo-300 font-medium py-1 transition-colors"
          >
            <div className="flex items-center gap-1.5">
              <SlidersHorizontal className="w-3.5 h-3.5" />
              <span>
                {showAllScores
                  ? isAr ? 'إخفاء المعايير التفصيلية' : 'Hide detailed criteria'
                  : isAr ? 'عرض كافة مؤشرات الأداء والعتاد الـ 15 (TOPSIS)' : 'View All 15 Dimension Scores (TOPSIS)'}
              </span>
            </div>
            {showAllScores ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
          </button>

          {showAllScores && (
            <div className="pt-3 space-y-4 animate-in fade-in duration-200">
              {/* 10 TOPSIS Hardware Benchmark Scores */}
              <div className="space-y-2">
                <span className="text-[10px] font-bold text-indigo-300 uppercase tracking-wider block">
                  {isAr ? 'المعايير الهندسية والعتاد الـ 10 (TOPSIS):' : '10 Hardware Decision Criteria (TOPSIS):'}
                </span>
                <div className="grid grid-cols-2 sm:grid-cols-5 gap-2">
                  {topsis10Scores.map((sc) => (
                    <div key={sc.key} className="p-2 rounded-xl bg-slate-900 border border-slate-800 space-y-1">
                      <div className="flex items-center justify-between text-[10px] text-slate-300">
                        <span className="flex items-center gap-1 truncate">
                          {sc.icon}
                          <span className="truncate">{isAr ? sc.labelAr : sc.labelEn}</span>
                        </span>
                        <span className="font-mono font-bold text-indigo-300">{sc.score.toFixed(0)}</span>
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
            </div>
          )}
        </div>
      </div>

      {/* Bottom Pricing & CTAs */}
      <div className="flex flex-col sm:flex-row items-center justify-between gap-4 pt-4 border-t border-slate-800">
        <div>
          <span className="text-[11px] text-slate-400 block">
            {isAr ? 'أفضل سعر مسجل:' : 'Cheapest Recorded Price:'}
          </span>
          <div className="flex items-baseline gap-2">
            <span className="text-2xl font-extrabold text-white font-mono">
              {laptop.effective_price_egp.toLocaleString()}
            </span>
            <span className="text-xs font-semibold text-slate-400">{isAr ? 'ج.م' : 'EGP'}</span>
            <span className="text-xs text-emerald-400 font-medium">
              ({isAr ? 'متوفر لدى' : 'via'} {laptop.cheapest_store})
            </span>
          </div>
        </div>

        <div className="flex items-center gap-2.5 w-full sm:w-auto">
          {/* View Details Modal Trigger */}
          <button
            onClick={() => onSelect(laptop)}
            className="flex-1 sm:flex-none px-4 py-2.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-semibold border border-slate-700 hover:text-white transition-all flex items-center justify-center gap-1.5"
          >
            <span>{isAr ? 'المواصفات الكاملة' : 'Full Specs'}</span>
            <ChevronRight className="w-3.5 h-3.5" />
          </button>

          {/* Direct Store Link */}
          <a
            href={laptop.cheapest_offer_url}
            target="_blank"
            rel="noopener noreferrer"
            className="flex-1 sm:flex-none px-5 py-2.5 rounded-xl bg-gradient-to-r from-indigo-600 to-violet-600 hover:from-indigo-500 hover:to-violet-500 text-white text-xs font-semibold shadow-lg shadow-indigo-600/20 transition-all flex items-center justify-center gap-1.5"
          >
            <span>{isAr ? 'شراء من المتجر' : 'Visit Store'}</span>
            <ExternalLink className="w-3.5 h-3.5" />
          </a>
        </div>
      </div>
    </div>
  )
}
