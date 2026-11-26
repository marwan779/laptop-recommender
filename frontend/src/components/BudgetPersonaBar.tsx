import React, { useState } from 'react'
import {
  Gamepad2,
  Code2,
  Palette,
  GraduationCap,
  Scale,
  Filter,
  Check,
  SlidersHorizontal,
  ChevronDown,
  ChevronUp,
  Cpu,
  HardDrive,
  Monitor,
  RotateCcw,
  ShieldCheck,
  Search,
  Sun,
  BatteryFull,
  Thermometer,
  Keyboard,
} from 'lucide-react'
import type { MetricFilterKey, PersonaType } from '../types/api'
import { METRIC_FILTER_DEFS } from '../config/metricFilters'
import {
  PERSONA_CATEGORIES,
  findCategoryForPersona,
  type PersonaCategoryId,
} from '../config/personas'
import { MetricSlider } from './MetricSlider'

interface BudgetPersonaBarProps {
  budget: number
  onBudgetChange: (val: number) => void
  selectedPersona: PersonaType
  onSelectPersona: (p: PersonaType) => void
  promptText: string
  onPromptChange: (text: string) => void
  minRam: number | null
  onMinRamChange: (ram: number | null) => void
  minStorage: number | null
  onMinStorageChange: (ssd: number | null) => void
  requireDgpu: boolean | null
  onRequireDgpuChange: (dgpu: boolean | null) => void
  selectedBrands: string[]
  onToggleBrand: (brand: string) => void
  metricFilters: Record<MetricFilterKey, number | null>
  onMetricChange: (key: MetricFilterKey, value: number | null) => void
  topK: number
  onTopKChange: (k: number) => void
  onResetAdvancedFilters: () => void
  onSubmit: () => void
  isLoading: boolean
  lang: 'ar' | 'en'
  mode?: 'initial' | 'edit'
  onCancel?: () => void
}

const CATEGORY_ICONS: Record<PersonaCategoryId, React.ReactNode> = {
  balanced: <Scale className="w-5 h-5" strokeWidth={1.8} />,
  daily: <GraduationCap className="w-5 h-5" strokeWidth={1.8} />,
  tech: <Code2 className="w-5 h-5" strokeWidth={1.8} />,
  gaming: <Gamepad2 className="w-5 h-5" strokeWidth={1.8} />,
  creative: <Palette className="w-5 h-5" strokeWidth={1.8} />,
}

const BUDGET_PRESETS = [25000, 35000, 50000, 70000, 100000]
const AVAILABLE_BRANDS = ['ASUS', 'Lenovo', 'HP', 'Dell', 'Apple', 'Acer', 'MSI', 'Gigabyte']
const TOP_K_OPTIONS = [3, 5, 8, 12, 15]

const RAM_OPTIONS = [
  { val: null as number | null, labelAr: 'الكل', labelEn: 'Any' },
  { val: 8, labelAr: '8GB+', labelEn: '8GB+' },
  { val: 16, labelAr: '16GB+', labelEn: '16GB+' },
  { val: 32, labelAr: '32GB+', labelEn: '32GB+' },
]
const STORAGE_OPTIONS = [
  { val: null as number | null, labelAr: 'الكل', labelEn: 'Any' },
  { val: 512, labelAr: '512GB+', labelEn: '512GB+' },
  { val: 1024, labelAr: '1TB+', labelEn: '1TB+' },
]
const GPU_OPTIONS = [
  { val: null as boolean | null, labelAr: 'الكل', labelEn: 'Any' },
  { val: true, labelAr: 'منفصل', labelEn: 'Dedicated' },
  { val: false, labelAr: 'مدمج', labelEn: 'Integrated' },
]

export const BudgetPersonaBar: React.FC<BudgetPersonaBarProps> = ({
  budget,
  onBudgetChange,
  selectedPersona,
  onSelectPersona,
  promptText,
  onPromptChange,
  minRam,
  onMinRamChange,
  minStorage,
  onMinStorageChange,
  requireDgpu,
  onRequireDgpuChange,
  selectedBrands,
  onToggleBrand,
  metricFilters,
  onMetricChange,
  topK,
  onTopKChange,
  onResetAdvancedFilters,
  onSubmit,
  isLoading,
  lang,
  mode = 'initial',
  onCancel,
}) => {
  const isAr = lang === 'ar'
  const [showAdvanced, setShowAdvanced] = useState(false)

  const activeMetricDefs = METRIC_FILTER_DEFS.filter((def) => metricFilters[def.key] != null)

  const activeFiltersCount =
    (minRam ? 1 : 0) +
    (minStorage ? 1 : 0) +
    (requireDgpu !== null ? 1 : 0) +
    selectedBrands.length +
    activeMetricDefs.length +
    (topK !== 8 ? 1 : 0)

  const displayPriority = metricFilters.min_display_score === 70
  const batteryPriority = metricFilters.min_battery_score === 70
  const coolingPriority =
    metricFilters.min_thermals_score === 70 && metricFilters.min_acoustics_score === 65
  const dgpuPriority = requireDgpu === true

  const handleBudgetInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = Number(e.target.value)
    if (!Number.isNaN(val) && val >= 0) onBudgetChange(val)
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') onSubmit()
  }

  const toggleDisplay = () => onMetricChange('min_display_score', displayPriority ? null : 70)
  const toggleBattery = () => onMetricChange('min_battery_score', batteryPriority ? null : 70)
  const toggleCooling = () => {
    if (coolingPriority) {
      if (metricFilters.min_thermals_score === 70) onMetricChange('min_thermals_score', null)
      if (metricFilters.min_acoustics_score === 65) onMetricChange('min_acoustics_score', null)
    } else {
      onMetricChange('min_thermals_score', 70)
      onMetricChange('min_acoustics_score', 65)
    }
  }
  const toggleDgpu = () => onRequireDgpuChange(dgpuPriority ? null : true)

  const budgetFill = `${Math.min(
    100,
    Math.max(0, ((budget - 12000) / (150000 - 12000)) * 100),
  )}%`

  const priorities = [
    { key: 'display', active: displayPriority, icon: <Sun className="w-3.5 h-3.5" />, ar: 'شاشة ألوانها دقيقة', en: 'Colour-accurate screen', onClick: toggleDisplay },
    { key: 'battery', active: batteryPriority, icon: <BatteryFull className="w-3.5 h-3.5" />, ar: 'بطارية تطوّل بره البيت', en: 'Long battery away from home', onClick: toggleBattery },
    { key: 'cooling', active: coolingPriority, icon: <Thermometer className="w-3.5 h-3.5" />, ar: 'تبريد هادي ومبيسخنش', en: 'Quiet, cool under load', onClick: toggleCooling },
    { key: 'dgpu', active: dgpuPriority, icon: <Keyboard className="w-3.5 h-3.5" />, ar: 'كارت شاشة منفصل قوي', en: 'Strong dedicated graphics', onClick: toggleDgpu },
  ]

  return (
    <div className="panel space-y-6" id="guided-finder">
      {/* Independence trust strip */}
      <div className="flex items-start gap-2.5 rounded-[10px] border border-[var(--border-subtle)] bg-[var(--success-dim)] px-3.5 py-2.5 text-[12.5px] leading-[1.6] text-[var(--text-secondary)]">
        <ShieldCheck className="w-4 h-4 mt-0.5 shrink-0 text-[var(--success)]" strokeWidth={1.8} />
        <p dir="auto">
          {isAr
            ? 'مستقل 100% — لا نحصل على عمولات من المتاجر · هدفنا تختار الصح بأقل سعر'
            : '100% independent — we take no store commissions. Our only goal is the right laptop at the lowest price.'}
        </p>
      </div>

      {/* Step 1 — Budget */}
      <section className="space-y-3">
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <div>
            <span className="micro block">{isAr ? 'الخطوة 1' : 'STEP 1'}</span>
            <h2 className="font-display text-[18px] font-semibold text-[var(--text-primary)]">
              {isAr ? 'الميزانية' : 'Your budget'}
            </h2>
          </div>

          <div className="budget-input">
            <span className="text-[12px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)] whitespace-nowrap">
              {isAr ? 'الميزانية' : 'Budget'}
            </span>
            <input
              type="number"
              min={10000}
              max={250000}
              step={1000}
              inputMode="numeric"
              value={budget || ''}
              onChange={handleBudgetInput}
              aria-label={isAr ? 'الميزانية القصوى بالجنيه' : 'Max budget in EGP'}
              className="amt tabular-nums [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
            />
            <span className="cur">{isAr ? 'ج.م' : 'EGP'}</span>
          </div>
        </div>

        <input
          type="range"
          min={12000}
          max={150000}
          step={1000}
          value={Math.min(150000, Math.max(12000, budget))}
          onChange={(e) => onBudgetChange(Number(e.target.value))}
          aria-label={isAr ? 'الميزانية بالجنيه' : 'Budget in EGP'}
          className="tile-range budget"
          style={{ ['--fill' as string]: budgetFill }}
        />

        <div className="flex flex-wrap gap-2">
          {BUDGET_PRESETS.map((preset) => (
            <button
              key={preset}
              type="button"
              onClick={() => onBudgetChange(preset)}
              aria-pressed={budget === preset}
              className={`rounded-full border px-3.5 py-2 text-[12px] font-mono tabular-nums transition-colors ${
                budget === preset
                  ? 'border-[var(--gold)] bg-[var(--gold-dim)] text-[var(--gold-bright)]'
                  : 'border-[var(--border-subtle)] text-[var(--text-secondary)] hover:border-[var(--border-strong)] hover:text-[var(--text-primary)]'
              }`}
            >
              {(preset / 1000).toFixed(0)}K
            </button>
          ))}
        </div>
      </section>

      {/* Step 2 — Usage (2-Level Category + Sub-Persona Picker) */}
      <section className="space-y-3 pt-5 border-t border-[var(--border-subtle)]">
        <div>
          <span className="micro block">{isAr ? 'الخطوة 2' : 'STEP 2'}</span>
          <h2 className="font-display text-[18px] font-semibold text-[var(--text-primary)]">
            {isAr ? 'هتستخدمه في إيه؟' : 'What will you use it for?'}
          </h2>
        </div>

        {(() => {
          const activeCategory = findCategoryForPersona(selectedPersona)
          const activeSub = activeCategory.subOptions.find((s) => s.id === selectedPersona)
          return (
            <>
              <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-2.5">
                {PERSONA_CATEGORIES.map((cat) => {
                  const isSelected = activeCategory.id === cat.id
                  return (
                    <button
                      key={cat.id}
                      type="button"
                      aria-pressed={isSelected}
                      onClick={() => onSelectPersona(cat.defaultPersona)}
                      className={`relative text-start rounded-[10px] border p-3 min-h-[100px] transition-colors ${
                        isSelected
                          ? 'border-[var(--gold)] bg-[var(--gold-dim)]'
                          : 'border-[var(--border-subtle)] bg-[var(--bg-raised)] hover:border-[var(--border-strong)]'
                      }`}
                    >
                      <span
                        className={`inline-flex items-center justify-center w-8 h-8 rounded-[8px] mb-2 ${
                          isSelected
                            ? 'bg-[var(--gold-dim)] text-[var(--gold-bright)]'
                            : 'bg-[var(--bg-input)] text-[var(--cyan)]'
                        }`}
                      >
                        {CATEGORY_ICONS[cat.id]}
                      </span>
                      <span className="block text-[13px] font-semibold text-[var(--text-primary)]">
                        {isAr ? cat.labelAr : cat.labelEn}
                      </span>
                      <span className="block mt-0.5 text-[12px] leading-[1.45] text-[var(--text-muted)] line-clamp-2">
                        {isAr ? cat.descAr : cat.descEn}
                      </span>
                      {isSelected && (
                        <span className="absolute top-2 end-2 inline-flex items-center justify-center w-5 h-5 rounded-full bg-[var(--gold-cta)] text-[var(--text-inverse)]">
                          <Check className="w-3 h-3 stroke-[3]" />
                        </span>
                      )}
                    </button>
                  )
                })}
              </div>

              {activeCategory.subOptions.length > 0 && (
                <div className="rounded-[10px] border border-[var(--border-subtle)] bg-[var(--bg-input)] p-3 space-y-2">
                  <div className="flex items-center justify-between gap-2 flex-wrap">
                    <span className="text-[12px] font-semibold text-[var(--text-secondary)]">
                      {isAr ? 'تخصص الاستخدام:' : 'Specialize your focus:'}
                    </span>
                    {activeSub && (
                      <span dir="auto" className="text-[12px] text-[var(--text-muted)]">
                        {isAr ? activeSub.hintAr : activeSub.hintEn}
                      </span>
                    )}
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {activeCategory.subOptions.map((sub) => {
                      const isSubSelected = selectedPersona === sub.id
                      return (
                        <button
                          key={sub.id}
                          type="button"
                          aria-pressed={isSubSelected}
                          onClick={() => onSelectPersona(sub.id)}
                          className={`min-h-[40px] rounded-full border px-3.5 py-2 text-[12px] font-medium transition-colors ${
                            isSubSelected
                              ? 'border-[var(--gold)] bg-[var(--gold-dim)] text-[var(--gold-bright)] font-semibold'
                              : 'border-[var(--border-subtle)] bg-[var(--bg-surface)] text-[var(--text-secondary)] hover:border-[var(--border-strong)] hover:text-[var(--text-primary)]'
                          }`}
                        >
                          {isAr ? sub.labelAr : sub.labelEn}
                        </button>
                      )
                    })}
                  </div>
                </div>
              )}
            </>
          )
        })()}
      </section>

      {/* Step 3 — Dealbreakers & note */}
      <section className="space-y-3 pt-5 border-t border-[var(--border-subtle)]">
        <div>
          <span className="micro block">{isAr ? 'الخطوة 3' : 'STEP 3'}</span>
          <h2 className="font-display text-[18px] font-semibold text-[var(--text-primary)]">
            {isAr ? 'إيه اللي يهمك أكتر؟' : 'What matters most?'}
          </h2>
          <p className="text-[12.5px] text-[var(--text-muted)] mt-0.5">
            {isAr
              ? 'اختياري — اضغط اللي يهمك وهنفلتر على أساسه.'
              : 'Optional — tap what matters and we will filter for it.'}
          </p>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
          {priorities.map((item) => (
            <button
              key={item.key}
              type="button"
              aria-pressed={item.active}
              onClick={item.onClick}
              className={`flex items-center gap-2.5 rounded-[10px] border px-3.5 py-2.5 min-h-[44px] text-start text-[12.5px] font-medium transition-colors ${
                item.active
                  ? 'border-[var(--gold)] bg-[var(--gold-dim)] text-[var(--gold-bright)]'
                  : 'border-[var(--border-subtle)] bg-[var(--bg-raised)] text-[var(--text-secondary)] hover:border-[var(--border-strong)] hover:text-[var(--text-primary)]'
              }`}
            >
              <span className="shrink-0">{item.icon}</span>
              <span className="flex-1">{isAr ? item.ar : item.en}</span>
              {item.active && <Check className="w-3.5 h-3.5 shrink-0" strokeWidth={2.5} />}
            </button>
          ))}
        </div>

        <div className="space-y-1.5 pt-1">
          <label htmlFor="prompt-input" className="label flex items-center gap-1.5">
            <Search className="w-3.5 h-3.5 text-[var(--text-muted)]" strokeWidth={1.8} />
            <span>{isAr ? 'ملاحظة اختيارية (عربي أو إنجليزي)' : 'Optional note (AR / EN)'}</span>
          </label>
          <input
            id="prompt-input"
            type="text"
            value={promptText}
            onChange={(e) => onPromptChange(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={
              isAr
                ? 'مثال: هندسة وأوتوكاد، أو لعبة، أو وزن خفيف'
                : 'e.g. AutoCAD, gaming, or light weight'
            }
            className="field"
          />
        </div>
      </section>

      {/* Advanced accordion */}
      <section className="pt-5 border-t border-[var(--border-subtle)]">
        <button
          type="button"
          onClick={() => setShowAdvanced(!showAdvanced)}
          className="w-full flex items-center justify-between gap-3 text-start group min-h-[40px]"
          aria-expanded={showAdvanced}
        >
          <span className="flex items-center gap-2 min-w-0">
            <SlidersHorizontal className="w-4 h-4 text-[var(--text-muted)] shrink-0" strokeWidth={1.8} />
            <span className="text-[13px] font-semibold text-[var(--text-primary)]">
              {isAr ? 'فلاتر متقدمة للمتخصصين' : 'Advanced filters for enthusiasts'}
            </span>
            {activeFiltersCount > 0 && <span className="count-chip">{activeFiltersCount}</span>}
          </span>
          <span className="ct-state shrink-0">
            <span>{showAdvanced ? (isAr ? 'إخفاء' : 'Hide') : isAr ? 'تخصيص' : 'Customize'}</span>
            {showAdvanced ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
          </span>
        </button>

        {showAdvanced && (
          <div className="mt-4 space-y-4">
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
              <div className="space-y-2">
                <span className="micro flex items-center gap-1.5">
                  <Cpu className="w-3.5 h-3.5 text-[var(--cyan)]" strokeWidth={1.8} />
                  <span>{isAr ? 'الحد الأدنى للرام' : 'Min RAM'}</span>
                </span>
                <div className="seg seg-fluid">
                  {RAM_OPTIONS.map((opt) => (
                    <button
                      key={String(opt.val)}
                      type="button"
                      aria-pressed={minRam === opt.val}
                      onClick={() => onMinRamChange(opt.val)}
                    >
                      {isAr ? opt.labelAr : opt.labelEn}
                    </button>
                  ))}
                </div>
              </div>

              <div className="space-y-2">
                <span className="micro flex items-center gap-1.5">
                  <HardDrive className="w-3.5 h-3.5 text-[var(--cyan)]" strokeWidth={1.8} />
                  <span>{isAr ? 'الحد الأدنى للتخزين' : 'Min storage'}</span>
                </span>
                <div className="seg seg-fluid">
                  {STORAGE_OPTIONS.map((opt) => (
                    <button
                      key={String(opt.val)}
                      type="button"
                      aria-pressed={minStorage === opt.val}
                      onClick={() => onMinStorageChange(opt.val)}
                    >
                      {isAr ? opt.labelAr : opt.labelEn}
                    </button>
                  ))}
                </div>
              </div>

              <div className="space-y-2">
                <span className="micro flex items-center gap-1.5">
                  <Monitor className="w-3.5 h-3.5 text-[var(--cyan)]" strokeWidth={1.8} />
                  <span>{isAr ? 'كارت الشاشة' : 'Graphics'}</span>
                </span>
                <div className="seg seg-fluid">
                  {GPU_OPTIONS.map((opt) => (
                    <button
                      key={String(opt.val)}
                      type="button"
                      aria-pressed={requireDgpu === opt.val}
                      onClick={() => onRequireDgpuChange(opt.val)}
                    >
                      {isAr ? opt.labelAr : opt.labelEn}
                    </button>
                  ))}
                </div>
              </div>

              <div className="space-y-2">
                <span className="micro flex items-center gap-1.5">
                  <Filter className="w-3.5 h-3.5 text-[var(--cyan)]" strokeWidth={1.8} />
                  <span>{isAr ? 'عدد النتائج' : 'Max results'}</span>
                </span>
                <div className="seg seg-fluid">
                  {TOP_K_OPTIONS.map((k) => (
                    <button
                      key={k}
                      type="button"
                      aria-pressed={topK === k}
                      onClick={() => onTopKChange(k)}
                      className="font-mono tabular-nums"
                    >
                      {k}
                    </button>
                  ))}
                </div>
              </div>
            </div>

            <div className="space-y-2 pt-4 border-t border-[var(--border-subtle)]">
              <div className="flex items-center justify-between flex-wrap gap-2">
                <span className="micro flex items-center gap-1.5">
                  <Filter className="w-3.5 h-3.5 text-[var(--cyan)]" strokeWidth={1.8} />
                  <span>{isAr ? 'ماركات مفضلة (اختياري)' : 'Preferred brands (optional)'}</span>
                </span>
                {activeFiltersCount > 0 && (
                  <button
                    type="button"
                    onClick={onResetAdvancedFilters}
                    className="btn-ghost inline-flex items-center gap-1 !h-auto !py-1"
                  >
                    <RotateCcw className="w-3 h-3" strokeWidth={1.8} />
                    <span>{isAr ? 'إعادة ضبط الفلاتر' : 'Reset filters'}</span>
                  </button>
                )}
              </div>
              <div className="flex flex-wrap gap-2">
                {AVAILABLE_BRANDS.map((b) => {
                  const isChecked = selectedBrands.includes(b)
                  return (
                    <button
                      key={b}
                      type="button"
                      aria-pressed={isChecked}
                      onClick={() => onToggleBrand(b)}
                      className={`brand-chip transition-colors ${
                        isChecked
                          ? '!text-[var(--gold-bright)] !border-[var(--gold)] !bg-[var(--gold-dim)]'
                          : 'hover:!border-[var(--border-strong)] hover:!text-[var(--text-primary)]'
                      }`}
                    >
                      {b}
                    </button>
                  )
                })}
              </div>
            </div>

            <div className="space-y-3 pt-4 border-t border-[var(--border-subtle)]">
              <span className="micro">
                {isAr ? 'مؤشرات التجربة الحقيقية والأداء (اختياري)' : 'Real-world experience & performance (optional)'}
              </span>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="space-y-2.5">
                  <div className="flex items-center gap-2">
                    <span className="w-1 h-3.5 rounded-full bg-[var(--cyan)]" />
                    <h4 className="micro !text-[var(--text-secondary)]">
                      {isAr ? 'تجربة الاستخدام' : 'Real-world usage'}
                    </h4>
                  </div>
                  {METRIC_FILTER_DEFS.filter((def) => def.group === 'experience').map((def) => (
                    <MetricSlider
                      key={def.key}
                      def={def}
                      value={metricFilters[def.key]}
                      onChange={(val) => onMetricChange(def.key, val)}
                      lang={lang}
                    />
                  ))}
                </div>

                <div className="space-y-2.5">
                  <div className="flex items-center gap-2">
                    <span className="w-1 h-3.5 rounded-full bg-[var(--cyan)]" />
                    <h4 className="micro !text-[var(--text-secondary)]">
                      {isAr ? 'قوة العتاد' : 'Hardware power'}
                    </h4>
                  </div>
                  {METRIC_FILTER_DEFS.filter((def) => def.group === 'performance').map((def) => (
                    <MetricSlider
                      key={def.key}
                      def={def}
                      value={metricFilters[def.key]}
                      onChange={(val) => onMetricChange(def.key, val)}
                      lang={lang}
                    />
                  ))}
                </div>
              </div>
            </div>
          </div>
        )}
      </section>

      {/* Primary CTA */}
      <div className="flex flex-col sm:flex-row gap-2.5 pt-5 border-t border-[var(--border-subtle)]">
        {mode === 'edit' && onCancel && (
          <button type="button" onClick={onCancel} className="btn btn-secondary">
            <span>{isAr ? 'إلغاء' : 'Cancel'}</span>
          </button>
        )}
        <button
          type="button"
          onClick={onSubmit}
          disabled={isLoading}
          className="btn btn-primary w-full sm:flex-1 min-h-[46px]"
        >
          {isLoading ? (
            <>
              <span className="spinner spinner-sm spinner-inverse" />
              <span>{isAr ? 'جاري البحث...' : 'Finding laptops...'}</span>
            </>
          ) : (
            <>
              <Search className="w-4 h-4" strokeWidth={2} />
              <span>
                {mode === 'edit'
                  ? isAr
                    ? 'تطبيق التعديلات'
                    : 'Apply Filters'
                  : isAr
                  ? 'اعرض لي أنسب الاختيارات'
                  : 'Show My Best Matches'}
              </span>
            </>
          )}
        </button>
      </div>
    </div>
  )
}
