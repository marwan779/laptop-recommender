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
  const isExperience = def.group === 'experience'
  const label = isAr ? def.labelAr : def.labelEn
  const inputId = `metric-slider-${def.key}`

  const handleChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const next = Number(event.target.value)
    onChange(next > 0 ? next : null)
  }

  return (
    <div className="space-y-2 rounded-2xl bg-slate-900/60 border border-slate-800/80 p-3">
      {/* Row 1: icon + label + live value badge + individual reset */}
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5 min-w-0">
          <span
            className={`p-1.5 rounded-lg shrink-0 ${
              isExperience
                ? 'bg-emerald-500/10 text-emerald-300'
                : 'bg-sky-500/10 text-sky-300'
            }`}
          >
            <Icon className="w-3.5 h-3.5" />
          </span>
          <label
            htmlFor={inputId}
            className="text-[11px] font-semibold text-slate-300 truncate cursor-pointer"
          >
            {label}
          </label>
        </div>

        <div className="flex items-center gap-1 shrink-0">
          <span
            className={`text-[10px] px-2 py-0.5 rounded-md border font-mono font-bold ${tier.badgeClass}`}
            title={tier.label}
          >
            {current > 0 ? `${current}+` : isAr ? 'الكل' : 'Any'}
          </span>
          {current > 0 && (
            <button
              type="button"
              onClick={() => onChange(null)}
              aria-label={isAr ? `إعادة ضبط ${label}` : `Reset ${label}`}
              title={isAr ? 'إعادة ضبط' : 'Reset'}
              className="p-1 rounded-md bg-slate-800 text-slate-400 hover:text-rose-300 hover:bg-rose-500/10 border border-slate-700 transition-colors"
            >
              <X className="w-3 h-3" />
            </button>
          )}
        </div>
      </div>

      {/* Row 2: interactive 0-100 range slider */}
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
        className={`w-full h-1.5 rounded-full bg-slate-700 cursor-pointer appearance-none ${tier.accentClass} ${tier.colorClass} [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:h-3.5 [&::-webkit-slider-thumb]:w-3.5 [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-white [&::-webkit-slider-thumb]:border-2 [&::-webkit-slider-thumb]:border-current [&::-webkit-slider-thumb]:shadow-md [&::-moz-range-thumb]:h-3.5 [&::-moz-range-thumb]:w-3.5 [&::-moz-range-thumb]:rounded-full [&::-moz-range-thumb]:bg-white [&::-moz-range-thumb]:border-2 [&::-moz-range-thumb]:border-current`}
      />

      {/* Row 3: scale markers + tier label */}
      <div className="flex items-center justify-between text-[9px] text-slate-500 font-mono">
        <span>0 ({isAr ? 'الكل' : 'Any'})</span>
        <span>50</span>
        <span>80</span>
        <span>100</span>
      </div>
      <div className={`text-[10px] font-medium ${tier.colorClass}`}>{tier.label}</div>
    </div>
  )
}

export default MetricSlider
