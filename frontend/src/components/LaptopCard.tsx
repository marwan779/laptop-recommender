import React from 'react'
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

  const pros = isAr ? laptop.pros_ar : laptop.pros_en
  const cons = isAr ? laptop.cons_ar : laptop.cons_en
  const whyList = isAr ? laptop.why_recommended_ar : laptop.why_recommended_en

  const aspects = [
    {
      key: 'thermals',
      labelAr: 'التبريد',
      labelEn: 'Thermals',
      score: laptop.aspect_scores?.thermals_score || 75,
      icon: <Thermometer className="w-3 h-3 text-rose-400" />,
    },
    {
      key: 'acoustics',
      labelAr: 'الهدوء',
      labelEn: 'Acoustics',
      score: laptop.aspect_scores?.acoustics_score || 75,
      icon: <Volume2 className="w-3 h-3 text-cyan-400" />,
    },
    {
      key: 'build',
      labelAr: 'الشاسيه',
      labelEn: 'Build/Hinges',
      score: laptop.aspect_scores?.build_and_hinges_score || 75,
      icon: <ShieldCheck className="w-3 h-3 text-emerald-400" />,
    },
    {
      key: 'keyboard',
      labelAr: 'الكيبورد',
      labelEn: 'Keyboard',
      score: laptop.aspect_scores?.keyboard_and_trackpad_score || 75,
      icon: <Keyboard className="w-3 h-3 text-amber-400" />,
    },
    {
      key: 'battery',
      labelAr: 'البطارية',
      labelEn: 'Battery',
      score: laptop.aspect_scores?.real_battery_and_reliability_score || 75,
      icon: <BatteryCharging className="w-3 h-3 text-blue-400" />,
    },
  ]

  const getScoreColor = (score: number) => {
    if (score >= 80) return 'from-emerald-500 to-teal-400'
    if (score >= 65) return 'from-indigo-500 to-sky-400'
    return 'from-amber-500 to-orange-400'
  }

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-3xl p-6 shadow-xl hover:border-slate-700 transition-all flex flex-col justify-between group relative overflow-hidden">
      {/* Top row: Rank, Match Score, Brand */}
      <div className="flex items-start justify-between gap-4 mb-4">
        <div className="flex items-center gap-2.5">
          <span className="w-7 h-7 rounded-xl bg-slate-800 text-indigo-400 font-mono font-bold text-xs flex items-center justify-center border border-slate-700">
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
        <div className="flex flex-col items-end">
          <div className="px-3 py-1 rounded-xl bg-gradient-to-r from-indigo-500/20 to-violet-500/20 border border-indigo-500/40 text-indigo-300 font-extrabold text-sm flex items-center gap-1">
            <span>{laptop.topsis_match_score.toFixed(1)}%</span>
            <span className="text-[10px] font-normal text-slate-400">
              {isAr ? 'تطابق' : 'Match'}
            </span>
          </div>
        </div>
      </div>

      {/* Middle row: Thumbnail & Headline */}
      <div className="grid grid-cols-1 md:grid-cols-12 gap-6 mb-5">
        {/* Thumbnail */}
        <div className="md:col-span-4 flex items-center justify-center bg-slate-950/60 rounded-2xl p-4 border border-slate-800/80 aspect-video md:aspect-square relative">
          <img
            src={laptop.thumbnail_url}
            alt={laptop.title}
            className="max-h-36 object-contain group-hover:scale-105 transition-transform duration-300"
            onError={(e) => {
              // fallback if thumbnail fails
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
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-5 pt-3 border-t border-slate-800/80">
        {/* Pros */}
        <div className="space-y-1.5">
          <span className="text-[11px] font-bold text-emerald-400 flex items-center gap-1">
            <CheckCircle className="w-3 h-3" />
            <span>{isAr ? 'نقاط القوة حسب تقييمات المستخدمين' : 'Community Pros'}</span>
          </span>
          <div className="space-y-1">
            {(pros || []).slice(0, 2).map((pro, i) => (
              <div key={i} className="text-xs text-slate-300 flex items-start gap-1.5">
                <span className="text-emerald-500 text-[10px] mt-0.5">✓</span>
                <span className="line-clamp-2 text-slate-300/90">{pro}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Cons */}
        <div className="space-y-1.5">
          <span className="text-[11px] font-bold text-rose-400 flex items-center gap-1">
            <XCircle className="w-3 h-3" />
            <span>{isAr ? 'عيوب ونقاط الضعف المذكورة' : 'Community Cons'}</span>
          </span>
          <div className="space-y-1">
            {(cons || []).slice(0, 2).map((con, i) => (
              <div key={i} className="text-xs text-slate-300 flex items-start gap-1.5">
                <span className="text-rose-500 text-[10px] mt-0.5">✕</span>
                <span className="line-clamp-2 text-slate-300/90">{con}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* 5-Aspect Scores Progress Bars */}
      <div className="space-y-2 mb-5 bg-slate-950/30 p-3 rounded-2xl border border-slate-800/60">
        <div className="flex items-center justify-between text-[11px] text-slate-400 font-medium">
          <span>{isAr ? 'تقييم الجوانب الخمسة (من مراجعات الهاردوير)' : 'Hardware Aspects Breakdown'}</span>
          <span className="text-[10px] text-indigo-400">
            {laptop.reviews_evidence_count} {isAr ? 'مراجعة موثقة' : 'evidence sources'}
          </span>
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-5 gap-2.5">
          {aspects.map((asp) => (
            <div key={asp.key} className="space-y-1">
              <div className="flex items-center justify-between text-[10px]">
                <span className="text-slate-400 flex items-center gap-1">
                  {asp.icon}
                  {isAr ? asp.labelAr : asp.labelEn}
                </span>
                <span className="font-mono text-slate-300 font-semibold">
                  {asp.score.toFixed(0)}
                </span>
              </div>
              <div className="w-full bg-slate-800 h-1.5 rounded-full overflow-hidden">
                <div
                  className={`h-full rounded-full bg-gradient-to-r ${getScoreColor(asp.score)}`}
                  style={{ width: `${Math.min(100, Math.max(0, asp.score))}%` }}
                />
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Bottom Bar: Lowest Price & Direct Action Buttons */}
      <div className="flex items-center justify-between pt-4 border-t border-slate-800">
        <div>
          <span className="text-[11px] text-slate-400 block">
            {isAr ? 'أفضل سعر متاح في مصر:' : 'Lowest Price in Egypt:'}
          </span>
          <div className="flex items-baseline gap-1.5">
            <span className="text-xl font-extrabold text-white font-mono">
              {laptop.effective_price_egp.toLocaleString()}
            </span>
            <span className="text-xs font-semibold text-slate-400">
              {isAr ? 'ج.م' : 'EGP'}
            </span>
            <span className="text-[10px] text-emerald-400 ml-1">
              (@ {laptop.cheapest_store})
            </span>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {/* View Full Specs Modal Trigger */}
          <button
            onClick={() => onSelect(laptop)}
            className="px-3.5 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white text-xs font-medium transition-colors flex items-center gap-1"
          >
            <span>{isAr ? 'المواصفات الكاملة' : 'Full Specs'}</span>
            <ChevronRight className="w-3.5 h-3.5" />
          </button>

          {/* Buy / View at Store */}
          <a
            href={laptop.cheapest_offer_url}
            target="_blank"
            rel="noopener noreferrer"
            className="px-4 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold shadow-md shadow-indigo-600/20 transition-all flex items-center gap-1.5"
          >
            <span>{isAr ? 'عرض في المتجر' : 'Go to Store'}</span>
            <ExternalLink className="w-3.5 h-3.5" />
          </a>
        </div>
      </div>
    </div>
  )
}
