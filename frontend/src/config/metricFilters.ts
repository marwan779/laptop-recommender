import type { MetricFilterKey } from '../types/api'

export interface MetricPreset {
  value: number
  labelAr: string
  labelEn: string
}

export interface MetricFilterDef {
  key: MetricFilterKey
  scoreKey: string
  labelAr: string
  labelEn: string
  group: 'experience' | 'performance'
  presets: MetricPreset[]
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
    labelEn: 'Acoustics',
    group: 'experience',
    presets: [
      { value: 70, labelAr: '70+ هادئ', labelEn: '70+ Quiet' },
      { value: 80, labelAr: '80+ فائق الهدوء', labelEn: '80+ Silent' },
    ],
  },
  {
    key: 'min_thermals_score',
    scoreKey: 'thermals_score',
    labelAr: 'التبريد تحت الحمل',
    labelEn: 'Thermals',
    group: 'experience',
    presets: [
      { value: 70, labelAr: '70+ مستقر', labelEn: '70+ Stable' },
      { value: 80, labelAr: '80+ ألعاب ثقيلة', labelEn: '80+ Heavy Gaming' },
    ],
  },
  {
    key: 'min_battery_score',
    scoreKey: 'real_battery_and_reliability_score',
    labelAr: 'البطارية والاعتمادية',
    labelEn: 'Battery',
    group: 'experience',
    presets: [
      { value: 70, labelAr: '70+ يوم كامل', labelEn: '70+ All-day' },
      { value: 80, labelAr: '80+ ماراثون', labelEn: '80+ Marathon' },
    ],
  },
  {
    key: 'min_build_score',
    scoreKey: 'build_and_hinges_score',
    labelAr: 'الخامة والمفصلات',
    labelEn: 'Build',
    group: 'experience',
    presets: [{ value: 75, labelAr: '75+ معدن/عسكري', labelEn: '75+ Metal / MIL-STD' }],
  },
  {
    key: 'min_keyboard_score',
    scoreKey: 'keyboard_and_trackpad_score',
    labelAr: 'الكيبورد والتاتش باد',
    labelEn: 'Keyboard',
    group: 'experience',
    presets: [{ value: 75, labelAr: '75+ مريح', labelEn: '75+ Comfortable' }],
  },
  {
    key: 'min_display_score',
    scoreKey: 'display_score',
    labelAr: 'جودة وألوان الشاشة',
    labelEn: 'Display',
    group: 'performance',
    presets: [
      { value: 70, labelAr: '70+ ألوان ممتازة', labelEn: '70+ Great Colors' },
      { value: 80, labelAr: '80+ صانعي محتوى', labelEn: '80+ Creator' },
    ],
  },
  {
    key: 'min_cpu_score',
    scoreKey: 'cpu_score',
    labelAr: 'قوة المعالج',
    labelEn: 'CPU',
    group: 'performance',
    presets: [
      { value: 70, labelAr: '70+ سريع', labelEn: '70+ Fast' },
      { value: 85, labelAr: '85+ أداء عالي', labelEn: '85+ High-end' },
    ],
  },
  {
    key: 'min_gpu_score',
    scoreKey: 'gpu_score',
    labelAr: 'قوة كارت الشاشة',
    labelEn: 'GPU',
    group: 'performance',
    presets: [
      { value: 65, labelAr: '65+ جيمنج متوسط', labelEn: '65+ Mid Gaming' },
      { value: 80, labelAr: '80+ ألعاب قوية', labelEn: '80+ AAA Gaming' },
    ],
  },
  {
    key: 'min_value_score',
    scoreKey: 'value_score',
    labelAr: 'القيمة مقابل السعر',
    labelEn: 'Value',
    group: 'performance',
    presets: [
      { value: 80, labelAr: '80+ قيمة ممتازة', labelEn: '80+ Great Value' },
      { value: 90, labelAr: '90+ أفضل شراء', labelEn: '90+ Best Buy' },
    ],
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
