import React from 'react'
import { AlertTriangle, Info, CheckCircle2, TrendingUp } from 'lucide-react'
import type { RecommendationResponse } from '../types/api'

interface StatusBannerProps {
  response: RecommendationResponse
  lang: 'ar' | 'en'
}

export const StatusBanner: React.FC<StatusBannerProps> = ({ response, lang }) => {
  const isAr = lang === 'ar'
  const {
    status,
    applied_budget_window_egp,
    total_candidates_before_floor,
    results,
    parsed_text_prompt,
  } = response

  const minPrice = applied_budget_window_egp?.[0] || 0
  const maxPrice = applied_budget_window_egp?.[1] || 0
  const lowestAlternativePrice = results[0]?.effective_price_egp

  if (status === 'BUDGET_TOO_LOW_FOR_CATEGORY') {
    return (
      <div className="bg-amber-950/40 border border-amber-500/40 rounded-2xl p-4 flex items-start gap-3.5 shadow-lg shadow-amber-950/20 text-amber-200">
        <div className="p-2 bg-amber-500/20 rounded-xl shrink-0 mt-0.5">
          <AlertTriangle className="w-5 h-5 text-amber-400" />
        </div>
        <div className="space-y-1">
          <h3 className="font-bold text-sm text-amber-100">
            {isAr
              ? `الميزانية (${maxPrice.toLocaleString()} ج.م) أقل من الحد الأدنى لفئة ${response.persona_label_ar}`
              : `Budget (${maxPrice.toLocaleString()} EGP) is below entry level for ${response.persona_label_en}`}
          </h3>
          <p className="text-xs text-amber-200/80 leading-relaxed">
            {isAr
              ? `لتشغيل متطلبات هذه الفئة (مثل كارت شاشة خارجي أو شاشة عالية التردد)، تبدأ أسعار أفضل الخيارات المتاحة في السوق المصري من ${lowestAlternativePrice?.toLocaleString()} ج.م. رشحنا لك أرخص 3 بدائل حقيقية تلبي متطلباتك:`
              : `To satisfy category demands (such as a discrete GPU and high-refresh panel), real options in Egypt start at ${lowestAlternativePrice?.toLocaleString()} EGP. We surfaced the 3 most affordable dedicated alternatives below:`}
          </p>
        </div>
      </div>
    )
  }

  if (status === 'GATES_RELAXED_FOR_LOW_BUDGET') {
    return (
      <div className="bg-sky-950/40 border border-sky-500/40 rounded-2xl p-4 flex items-start gap-3.5 shadow-lg shadow-sky-950/20 text-sky-200">
        <div className="p-2 bg-sky-500/20 rounded-xl shrink-0 mt-0.5">
          <Info className="w-5 h-5 text-sky-400" />
        </div>
        <div className="space-y-1">
          <h3 className="font-bold text-sm text-sky-100">
            {isAr ? 'تم تخفيف بعض الشروط الصارمة لمطابقة ميزانيتك' : 'Hardware Gates Relaxed for Your Budget'}
          </h3>
          <p className="text-xs text-sky-200/80 leading-relaxed">
            {isAr
              ? `عثرنا على خيارات ممتازة، لكن تم تخفيف بعض الشروط الثانوية لضمان تقديم أعلى قيمة وأداء متوفر داخل ميزانيتك.`
              : `We found strong options, but relaxed secondary constraints to ensure you get the absolute best hardware value within your budget.`}
          </p>
        </div>
      </div>
    )
  }

  // Normal Status "OK"
  return (
    <div className="bg-slate-900/60 border border-slate-800 rounded-2xl p-3 px-4 flex flex-wrap items-center justify-between gap-3 text-xs text-slate-300">
      <div className="flex items-center gap-2">
        <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
        <span className="flex items-center flex-wrap">
          <span>
            {isAr
              ? `تم تحليل ${total_candidates_before_floor} لابتوب في السوق المصري وتطبيق نافذة الميزانية الذكية: `
              : `Evaluated ${total_candidates_before_floor} catalog laptops. Smart Budget Window: `}
          </span>
          <strong className="text-white mx-1.5 font-mono inline-block">
            {minPrice.toLocaleString()} - {maxPrice.toLocaleString()} EGP
          </strong>
        </span>
      </div>

      {parsed_text_prompt?.extracted_filters && Object.keys(parsed_text_prompt.extracted_filters).length > 0 && (
        <div className="flex items-center gap-1.5 bg-slate-800/80 px-2.5 py-1 rounded-lg border border-slate-700">
          <TrendingUp className="w-3.5 h-3.5 text-indigo-400" />
          <span className="text-[11px] text-slate-300">
            {isAr ? 'فلاتر ذكية مستخلصة: ' : 'Applied Prompt Filters: '}
            <span className="text-indigo-300 font-medium mx-1">
              {Object.keys(parsed_text_prompt.extracted_filters).join(', ')}
            </span>
          </span>
        </div>
      )}
    </div>
  )
}
