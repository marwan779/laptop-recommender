import React from 'react'
import {
  BatteryFull,
  Cpu,
  Flame,
  Keyboard,
  Monitor,
  Shield,
  Sun,
  Tag,
  Volume2,
  X,
  type LucideIcon,
} from 'lucide-react'
import type { MetricFilterKey } from '../types/api'
import { getScoreTier, type MetricFilterDef } from '../config/metricFilters'

interface MetricSliderProps {
  def: MetricFilterDef
  value: number | null
  onChange: (val: number | null) => void
  lang: 'ar' | 'en'
}

const METRIC_ICONS: Record<MetricFilterKey, LucideIcon> = {
  min_acoustics_score: Volume2,
  min_thermals_score: Flame,
  min_battery_score: BatteryFull,
  min_build_score: Shield,
  min_keyboard_score: Keyboard,
  min_cpu_score: Cpu,
  min_gpu_score: Monitor,
  min_display_score: Sun,
  min_value_score: Tag,
}

export const MetricSlider: React.FC<MetricSliderProps> = ({
  def,
  value,
  onChange,
  lang,
}) => {
  const isAr = lang === 'ar'
  const current = value ?? 0
  const tier = getScoreTier(current, lang)
  const Icon = METRIC_ICONS[def.key] ?? Cpu
  const label = isAr ? def.labelAr : def.labelEn
  const inputId = `metric-slider-${def.key}`

  const handleChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const next = Number(event.target.value)
    onChange(next > 0 ? next : null)
  }

  const scoreTone =
    current >= 85
      ? 'text-[var(--gold-bright)]'
      : current > 0 && current < 50
      ? 'text-[var(--danger)]'
      : 'text-[var(--text-primary)]'

  return (
    <div className="space-y-1.5">
      {/* Row 1: icon + label + live value badge + reset */}
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5 min-w-0">
          <Icon className="w-3.5 h-3.5 text-[var(--cyan)] shrink-0" strokeWidth={1.8} />
          <label
            htmlFor={inputId}
            className="text-[12.5px] font-medium text-[var(--text-primary)] truncate cursor-pointer"
          >
            {label}
          </label>
        </div>

        <div className="flex items-center gap-1 shrink-0">
          {current > 0 ? (
            <span className={`font-mono text-[12px] font-semibold num ${scoreTone}`}>
              {current}+
            </span>
          ) : (
            <span className="any-chip">{isAr ? 'الكل' : 'Any'}</span>
          )}
          {current > 0 && (
            <button
              type="button"
              onClick={() => onChange(null)}
              aria-label={isAr ? `إعادة ضبط ${label}` : `Reset ${label}`}
              title={isAr ? 'إعادة ضبط' : 'Reset'}
              className="p-0.5 rounded text-[var(--text-muted)] hover:text-[var(--danger)] transition-colors"
            >
              <X className="w-3 h-3" strokeWidth={2} />
            </button>
          )}
        </div>
      </div>

      {/* Row 2: range slider */}
      <input
        id={inputId}
        type="range"
        min={0}
        max={100}
        step={1}
        value={current}
        onChange={handleChange}
        aria-label={label}
        aria-valuetext={current > 0 ? `${current}+ ${tier.label}` : tier.label}
        className="tile-range"
        style={{ ['--fill' as string]: `${current}%` }}
      />

      {/* Row 3: scale markers */}
      <div className="flex items-center justify-between text-[10px] text-[var(--text-muted)] font-mono">
        <span>{isAr ? 'الكل' : 'Any'}</span>
        <span>50</span>
        <span>100</span>
      </div>
    </div>
  )
}

export default MetricSlider
