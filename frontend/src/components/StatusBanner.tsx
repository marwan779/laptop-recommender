import React from 'react'
import { Info, TrendingUp } from 'lucide-react'
import type { RecommendationResponse } from '../types/api'

interface StatusBannerProps {
  response: RecommendationResponse
  lang: 'ar' | 'en'
}

export const StatusBanner: React.FC<StatusBannerProps> = ({ response, lang }) => {
  const isAr = lang === 'ar'
  const { status, applied_budget_window_egp, total_candidates_before_floor, results } = response

  const hasWindow = !!applied_budget_window_egp && applied_budget_window_egp.length >= 2
  const minPrice = hasWindow ? applied_budget_window_egp[0] : 0
  const maxPrice = hasWindow ? applied_budget_window_egp[1] : 0
  const lowestAlternativePrice = results[0]?.effective_price_egp
  const hasAlternatives = results.length > 0

  if (status === 'BUDGET_TOO_LOW_FOR_CATEGORY') {
    return (
      <div className="status-banner is-warning">
        <span className="sdot" />
        <div className="flex-1 min-w-0 space-y-1">
          <h3 className="sb-title">
            {isAr
              ? 'ميزانيتك أقل من سعر البداية للاستخدام اللي اخترته'
              : 'Your budget is below the starting price for this use case'}
          </h3>
          <p className="sb-copy">
            {isAr
              ? `أرخص لابتوب حقيقي في السوق المصري بيبدأ من ${
                  lowestAlternativePrice ? `${lowestAlternativePrice.toLocaleString('en-US')} ج.م` : 'سعر أعلى'
                }. ${
                  hasAlternatives
                    ? 'عرضنا لك أقرب 3 بدائل حقيقية تحت ميزانيتك.'
                    : 'جرّب تزود الميزانية شوية أو تخفف الفلاتر.'
                }`
              : `The cheapest real option in Egypt starts at ${
                  lowestAlternativePrice ? `${lowestAlternativePrice.toLocaleString('en-US')} EGP` : 'a higher price'
                }. ${
                  hasAlternatives
                    ? 'We surfaced the closest 3 real alternatives within reach.'
                    : 'Try raising the budget slightly or relaxing the filters.'
                }`}
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
            {isAr ? 'وسّعنا بعض التفضيلات عشان نفضل جوه ميزانيتك' : 'We slightly widened secondary preferences'}
          </h3>
          <p className="sb-copy">
            {isAr
              ? 'لقينا خيارات كويسة، لكن بعض التفضيلات الثانوية اتوسّعت شوية عشان أفضل قيمة تفضل داخل ميزانيتك بالجنيه المصري.'
              : 'We found strong options, but widened a few secondary preferences so the best value stays inside your EGP budget.'}
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="status-banner">
      <span className="sdot" />
      <span className="flex-1 min-w-0 flex flex-wrap items-center gap-x-2 gap-y-1">
        <span className="inline-flex items-center gap-1.5">
          <Info className="w-3.5 h-3.5 text-[var(--text-muted)]" strokeWidth={1.8} />
          {isAr
            ? `تم فحص ${total_candidates_before_floor.toLocaleString('en-US')} لابتوب في مصر`
            : `Checked ${total_candidates_before_floor.toLocaleString('en-US')} laptops in Egypt`}
        </span>
        {hasWindow && (
          <>
            <span className="text-[var(--text-muted)]">·</span>
            <span>
              {isAr ? 'نطاق البحث:' : 'Price range:'}
            </span>
            <strong className="win num">
              {minPrice.toLocaleString('en-US')} – {maxPrice.toLocaleString('en-US')} {isAr ? 'ج.م' : 'EGP'}
            </strong>
          </>
        )}
      </span>

      {response.parsed_text_prompt?.extracted_filters &&
        Object.keys(response.parsed_text_prompt.extracted_filters).length > 0 && (
          <div className="ai-chip">
            <TrendingUp className="w-3 h-3" />
            <span>
              {isAr ? 'ملاحظاتك اتطبقت' : 'Your note was applied'}
            </span>
          </div>
        )}
    </div>
  )
}
