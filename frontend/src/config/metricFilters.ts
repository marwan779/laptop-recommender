import type { MetricFilterKey } from '../types/api'

export interface MetricFilterDef {
  key: MetricFilterKey
  scoreKey: string
  labelAr: string
  labelEn: string
  group: 'experience' | 'performance'
}

export type ScoreTier = {
  label: string
  colorClass: string
  badgeClass: string
  accentClass: string
}

/**
 * Optional 0-100 metric gates shared by the catalog browser and the
 * recommendation advanced drawer. Aspect scores come from real-world review
 * NLP; hardware scores come from benchmark modeling.
 */
export const METRIC_FILTER_DEFS: MetricFilterDef[] = [
  {
    key: 'min_acoustics_score',
    scoreKey: 'acoustics_score',
    labelAr: 'الهدوء والمراوح',
    labelEn: 'Acoustics / Fan Noise',
    group: 'experience',
  },
  {
    key: 'min_thermals_score',
    scoreKey: 'thermals_score',
    labelAr: 'التبريد تحت الحمل',
    labelEn: 'Cooling / Thermals',
    group: 'experience',
  },
  {
    key: 'min_battery_score',
    scoreKey: 'real_battery_and_reliability_score',
    labelAr: 'عمر البطارية الحقيقي',
    labelEn: 'Real Battery Life',
    group: 'experience',
  },
  {
    key: 'min_build_score',
    scoreKey: 'build_and_hinges_score',
    labelAr: 'الخامة والمفصلات',
    labelEn: 'Build & Hinges',
    group: 'experience',
  },
  {
    key: 'min_keyboard_score',
    scoreKey: 'keyboard_and_trackpad_score',
    labelAr: 'الكيبورد والتاتش باد',
    labelEn: 'Keyboard & Trackpad',
    group: 'experience',
  },
  {
    key: 'min_cpu_score',
    scoreKey: 'cpu_score',
    labelAr: 'قوة المعالج',
    labelEn: 'CPU Benchmark',
    group: 'performance',
  },
  {
    key: 'min_gpu_score',
    scoreKey: 'gpu_score',
    labelAr: 'قوة كارت الشاشة',
    labelEn: 'GPU 3D Power',
    group: 'performance',
  },
  {
    key: 'min_display_score',
    scoreKey: 'display_score',
    labelAr: 'جودة وألوان الشاشة',
    labelEn: 'Display Quality',
    group: 'performance',
  },
  {
    key: 'min_value_score',
    scoreKey: 'value_score',
    labelAr: 'القيمة مقابل السعر',
    labelEn: 'Value for Money',
    group: 'performance',
  },
]

export const EMPTY_METRIC_FILTERS: Record<MetricFilterKey, number | null> = {
  min_acoustics_score: null,
  min_thermals_score: null,
  min_battery_score: null,
  min_build_score: null,
  min_keyboard_score: null,
  min_cpu_score: null,
  min_gpu_score: null,
  min_display_score: null,
  min_value_score: null,
}

export function toMetricQuery(
  filters: Record<MetricFilterKey, number | null>
): Partial<Record<MetricFilterKey, number>> {
  const query: Partial<Record<MetricFilterKey, number>> = {}
  for (const def of METRIC_FILTER_DEFS) {
    const value = filters[def.key]
    if (value != null) query[def.key] = value
  }
  return query
}

/**
 * Map a 0-100 score to its bilingual label and color tier.
 * 0 = inactive/any, >=80 exceptional, >=60 great, otherwise acceptable.
 */
export function getScoreTier(score: number, lang: 'ar' | 'en'): ScoreTier {
  const isAr = lang === 'ar'

  if (!score || score <= 0) {
    return {
      label: isAr ? 'الكل' : 'Any',
      colorClass: 'text-slate-400',
      badgeClass: 'bg-slate-800/80 text-slate-400 border-slate-700',
      accentClass: 'accent-slate-500',
    }
  }

  if (score >= 80) {
    return {
      label: isAr ? 'فائق (+80)' : 'Exceptional (+80)',
      colorClass: 'text-emerald-300',
      badgeClass: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/40',
      accentClass: 'accent-emerald-500',
    }
  }

  if (score >= 60) {
    return {
      label: isAr ? 'جيد جداً (+60)' : 'Great (+60)',
      colorClass: 'text-indigo-300',
      badgeClass: 'bg-indigo-500/15 text-indigo-300 border-indigo-500/40',
      accentClass: 'accent-indigo-500',
    }
  }

  return {
    label: isAr ? 'مقبول' : 'Acceptable',
    colorClass: 'text-amber-300',
    badgeClass: 'bg-amber-500/15 text-amber-300 border-amber-500/40',
    accentClass: 'accent-amber-500',
  }
}
