import React from 'react'
import { TrendingUp } from 'lucide-react'
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
  const hasAlternatives = results.length > 0

  if (status === 'BUDGET_TOO_LOW_FOR_CATEGORY') {
    return (
      <div className="status-banner is-warning">
        <span className="sdot" />
        <div className="flex-1 min-w-0 space-y-1">
          <h3 className="sb-title">
            {isAr
              ? `الميزانية (${maxPrice.toLocaleString()} ج.م) أقل من الحد الأدنى لفئة ${response.persona_label_ar}`
              : `Budget (${maxPrice.toLocaleString()} EGP) is below entry level for ${response.persona_label_en}`}
          </h3>
          <p className="sb-copy">
            {isAr
              ? `لتشغيل متطلبات هذه الفئة (مثل كارت شاشة خارجي أو شاشة عالية التردد)، تبدأ أسعار أفضل الخيارات المتاحة في السوق المصري من ${lowestAlternativePrice ? `${lowestAlternativePrice.toLocaleString()} ج.م` : 'مستويات أعلى'}. ${hasAlternatives ? 'رشحنا لك أرخص 3 بدائل حقيقية تلبي متطلباتك:' : 'يرجى زيادة الميزانية أو تخفيف بعض الفلاتر لعرض الخيارات المتاحة.'}`
              : `To satisfy category demands (such as a discrete GPU and high-refresh panel), real options in Egypt start at ${lowestAlternativePrice ? `${lowestAlternativePrice.toLocaleString()} EGP` : 'higher price points'}. ${hasAlternatives ? 'We surfaced the 3 most affordable dedicated alternatives below:' : 'Please increase your budget or relax filters to view available options.'}`}
          </p>
        </div>
      </div>
    )
  }

  if (status === 'GATES_RELAXED_FOR_LOW_BUDGET') {
    return (
      <div className="status-banner is-info">
        <span className="sdot" />
        <div className="flex-1 min-w-0 space-y-1">
          <h3 className="sb-title">
            {isAr ? 'تم تخفيف بعض الشروط الصارمة لمطابقة ميزانيتك' : 'Hardware Gates Relaxed for Your Budget'}
          </h3>
          <p className="sb-copy">
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
    <div className="status-banner">
      <span className="sdot" />
      <span className="flex-1 min-w-0 flex flex-wrap items-center gap-x-2 gap-y-1">
        <span>
          {isAr
            ? `تم تحليل ${total_candidates_before_floor} لابتوب في السوق المصري وتطبيق نافذة الميزانية الذكية:`
            : `Evaluated ${total_candidates_before_floor} catalog laptops. Smart Budget Window:`}
        </span>
        <strong className="win num">
          {minPrice.toLocaleString()} – {maxPrice.toLocaleString()} EGP
        </strong>
      </span>

      {parsed_text_prompt?.extracted_filters && Object.keys(parsed_text_prompt.extracted_filters).length > 0 && (
        <div className="ai-chip">
          <TrendingUp className="w-3 h-3" />
          <span>
            {isAr ? 'فلاتر مستخلصة: ' : 'Prompt Filters: '}
            {Object.keys(parsed_text_prompt.extracted_filters).join(', ')}
          </span>
        </div>
      )}
    </div>
  )
}
