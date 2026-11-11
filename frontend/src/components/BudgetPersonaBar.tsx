import React, { useState } from 'react'
import {
  Gamepad2,
  Code2,
  Palette,
  BarChart3,
  Briefcase,
  GraduationCap,
  Scale,
  Sparkles,
  Filter,
  Check,
  Layers,
  SlidersHorizontal,
  ChevronDown,
  ChevronUp,
  Cpu,
  HardDrive,
  Monitor,
  RotateCcw,
} from 'lucide-react'
import type { MetricFilterKey, PersonaType } from '../types/api'
import { METRIC_FILTER_DEFS } from '../config/metricFilters'
import { MetricSlider } from './MetricSlider'

interface BudgetPersonaBarProps {
  budget: number
  onBudgetChange: (val: number) => void
  selectedPersonas: PersonaType[]
  onTogglePersona: (p: PersonaType) => void
  promptText: string
  onPromptChange: (text: string) => void
  // Hardware gate filters
  minRam: number | null
  onMinRamChange: (ram: number | null) => void
  minStorage: number | null
  onMinStorageChange: (ssd: number | null) => void
  requireDgpu: boolean | null
  onRequireDgpuChange: (dgpu: boolean | null) => void
  selectedBrands: string[]
  onToggleBrand: (brand: string) => void
  // Optional real-world experience & performance metric gates
  metricFilters: Record<MetricFilterKey, number | null>
  onMetricChange: (key: MetricFilterKey, value: number | null) => void
  // Top K selector
  topK: number
  onTopKChange: (k: number) => void
  onResetAdvancedFilters: () => void
  onSubmit: () => void
  isLoading: boolean
  lang: 'ar' | 'en'
}

interface PersonaOption {
  id: PersonaType
  icon: React.ReactNode
  labelAr: string
  labelEn: string
  descAr: string
  descEn: string
}

const PERSONAS: PersonaOption[] = [
  {
    id: 'gaming',
    icon: <Gamepad2 className="w-5 h-5" strokeWidth={1.8} />,
    labelAr: 'ألعاب ثقيلة',
    labelEn: 'Heavy Gaming',
    descAr: 'كارت شاشة منفصل قوي وشاشة سريعة 144Hz+',
    descEn: 'Dedicated dGPU & 144Hz+ display',
  },
  {
    id: 'programming',
    icon: <Code2 className="w-5 h-5" strokeWidth={1.8} />,
    labelAr: 'برمجة وتطوير',
    labelEn: 'Software Engineering',
    descAr: 'معالج قوي، رامات 16GB+ وكيبورد مريح',
    descEn: 'Heavy CPU, 16GB+ RAM & great keyboard',
  },
  {
    id: 'content_creation',
    icon: <Palette className="w-5 h-5" strokeWidth={1.8} />,
    labelAr: 'صناعة محتوى',
    labelEn: 'Content Creation',
    descAr: 'شاشة دقيقة الألوان (100% sRGB/DCI-P3) وأداء متوازن',
    descEn: 'Color-accurate creator screen & power',
  },
  {
    id: 'ai_and_game_dev',
    icon: <BarChart3 className="w-5 h-5" strokeWidth={1.8} />,
    labelAr: 'ذكاء اصطناعي وتطوير ألعاب',
    labelEn: 'AI & Game Dev',
    descAr: 'أنوية معالج عالية، كارت CUDA، ورامات قابلة للزيادة',
    descEn: 'High CPU cores, CUDA GPU & RAM expansion',
  },
  {
    id: 'business_and_mobility',
    icon: <Briefcase className="w-5 h-5" strokeWidth={1.8} />,
    labelAr: 'بيزنس وتنقل',
    labelEn: 'Business & Ultra-thin',
    descAr: 'بطارية تدوم طويلاً، وزن خفيف < 1.7kg، وشاسيه متين',
    descEn: 'All-day battery, under 1.7kg & sleek build',
  },
  {
    id: 'student_and_office',
    icon: <GraduationCap className="w-5 h-5" strokeWidth={1.8} />,
    labelAr: 'دراسة وأوفيس',
    labelEn: 'Student & Office',
    descAr: 'أفضل قيمة مقابل السعر للدراسة والأوفيس والمحاضرات',
    descEn: 'Best price-to-performance for studies & daily use',
  },
  {
    id: 'balanced',
    icon: <Scale className="w-5 h-5" strokeWidth={1.8} />,
    labelAr: 'استخدام متوازن',
    labelEn: 'Balanced All-Rounder',
    descAr: 'توازن ذكي بين الأداء والسعر والاعتمادية',
    descEn: 'Smart balance of power, durability & price',
  },
]

const BUDGET_PRESETS = [25000, 35000, 45000, 60000, 85000, 120000]
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
  { val: true, labelAr: 'خارجي (dGPU)', labelEn: 'dGPU Only' },
  { val: false, labelAr: 'مدمج (iGPU)', labelEn: 'iGPU Only' },
]

export const BudgetPersonaBar: React.FC<BudgetPersonaBarProps> = ({
  budget,
  onBudgetChange,
  selectedPersonas,
  onTogglePersona,
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
}) => {
  const isAr = lang === 'ar'
  const [showAdvanced, setShowAdvanced] = useState(false)

  const activeMetricDefs = METRIC_FILTER_DEFS.filter(
    (def) => metricFilters[def.key] != null
  )

  const activeFiltersCount =
    (minRam ? 1 : 0) +
    (minStorage ? 1 : 0) +
    (requireDgpu !== null ? 1 : 0) +
    selectedBrands.length +
    activeMetricDefs.length +
    (topK !== 8 ? 1 : 0)

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      onSubmit()
    }
  }

  const handleBudgetInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = Number(e.target.value)
    if (!isNaN(val) && val >= 0) {
      onBudgetChange(val)
    }
  }

  const budgetFill = `${Math.min(
    100,
    Math.max(0, ((budget - 12000) / (150000 - 12000)) * 100)
  )}%`

  return (
    <div className="panel space-y-6">
      {/* 1. Header & Budget Section */}
      <div className="space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <h2 className="font-display text-[20px] font-semibold text-[var(--text-primary)]">
              {isAr ? 'حدد ميزانيتك واستخدامك' : 'Set Your Budget & Usage'}
            </h2>
            <p className="text-[13px] text-[var(--text-muted)] mt-0.5">
              {isAr
                ? 'خوارزمية TOPSIS تختار اللابتوب صاحب أعلى قيمة فعلية داخل نطاق ميزانيتك'
                : 'Vector TOPSIS ranks candidates to find the highest value within your budget'}
            </p>
          </div>

          {/* Editable budget readout */}
          <div className="budget-input">
            <span className="text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)] whitespace-nowrap">
              {isAr ? 'الميزانية' : 'Budget'}
            </span>
            <input
              type="number"
              min={10000}
              max={250000}
              step={1000}
              value={budget || ''}
              onChange={handleBudgetInput}
              aria-label={isAr ? 'الميزانية القصوى بالجنيه' : 'Max budget in EGP'}
              className="amt [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
            />
            <span className="cur">{isAr ? 'ج.م' : 'EGP'}</span>
          </div>
        </div>

        {/* Budget slider & presets */}
        <div>
          <input
            type="range"
            min={12000}
            max={150000}
            step={1000}
            value={budget}
            onChange={(e) => onBudgetChange(Number(e.target.value))}
            aria-label={isAr ? 'الميزانية بالجنيه' : 'Budget in EGP'}
            className="tile-range budget"
            style={{ ['--fill' as string]: budgetFill }}
          />
          <div className="ticks">
            <span>{isAr ? '12,000' : '12,000'}</span>
            <div className="hidden sm:flex gap-1.5">
              {BUDGET_PRESETS.map((preset) => (
                <button
                  key={preset}
                  type="button"
                  onClick={() => onBudgetChange(preset)}
                  className={`px-2 py-0.5 rounded-md text-[11px] font-mono transition-colors ${
                    budget === preset
                      ? 'on'
                      : 'text-[var(--text-muted)] hover:text-[var(--text-primary)]'
                  }`}
                >
                  {(preset / 1000).toFixed(0)}k
                </button>
              ))}
            </div>
            <span>{isAr ? '150,000+ ج.م' : '150,000+ EGP'}</span>
          </div>
        </div>
      </div>

      {/* 2. Persona Selector (Multi-Select Enabled) */}
      <div className="space-y-2.5 pt-5 border-t border-[var(--border-subtle)]">
        <div className="flex items-center justify-between flex-wrap gap-2">
          <span className="label flex items-center gap-1.5">
            <Filter className="w-3.5 h-3.5 text-[var(--cyan)]" strokeWidth={1.8} />
            <span>
              {isAr
                ? 'فئات الاستخدام (اختر واحدة أو أكثر للدمج)'
                : 'Usage Personas (select one or multiple to blend)'}
            </span>
          </span>

          {selectedPersonas.length > 1 && (
            <span className="ai-chip">
              <Layers className="w-3 h-3" strokeWidth={1.8} />
              <span>
                {isAr
                  ? `دمج ذكي (${selectedPersonas.length} فئات)`
                  : `Blending ${selectedPersonas.length} personas`}
              </span>
            </span>
          )}
        </div>

        <div className="persona-grid">
          {PERSONAS.map((p) => {
            const isSelected = selectedPersonas.includes(p.id)
            return (
              <button
                key={p.id}
                type="button"
                aria-pressed={isSelected}
                onClick={() => onTogglePersona(p.id)}
                className="persona"
              >
                <span className="check">
                  <Check className="w-3 h-3 stroke-[3]" />
                </span>
                <span className="picon">{p.icon}</span>
                <span className="ptitle block">{isAr ? p.labelAr : p.labelEn}</span>
                <span className="pdesc block">{isAr ? p.descAr : p.descEn}</span>
              </button>
            )
          })}
        </div>
      </div>

      {/* 3. Collapsible Advanced Hardware Filters & Top K Accordion */}
      <div className="pt-5 border-t border-[var(--border-subtle)]">
        <button
          type="button"
          onClick={() => setShowAdvanced(!showAdvanced)}
          className="w-full flex items-center justify-between gap-3 text-start group"
        >
          <span className="flex items-center gap-2 min-w-0">
            <SlidersHorizontal className="w-4 h-4 text-[var(--cyan)] shrink-0" strokeWidth={1.8} />
            <span className="text-[13px] font-semibold text-[var(--text-primary)]">
              {isAr
                ? 'شروط العتاد المتقدمة (الرام، التخزين، كارت الشاشة، الماركات)'
                : 'Advanced Hardware Gates (RAM, Storage, GPU, Brands)'}
            </span>
            {activeFiltersCount > 0 && <span className="count-chip">{activeFiltersCount}</span>}
          </span>
          <span className="ct-state shrink-0">
            <span>{showAdvanced ? (isAr ? 'إخفاء' : 'Collapse') : isAr ? 'تخصيص' : 'Customize'}</span>
            {showAdvanced ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
          </span>
        </button>

        {showAdvanced && (
          <div className="mt-4 space-y-4">
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
              {/* RAM */}
              <div className="space-y-2">
                <span className="micro flex items-center gap-1.5">
                  <Cpu className="w-3.5 h-3.5 text-[var(--cyan)]" strokeWidth={1.8} />
                  <span>{isAr ? 'الحد الأدنى للرام' : 'Min RAM Capacity'}</span>
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

              {/* Storage */}
              <div className="space-y-2">
                <span className="micro flex items-center gap-1.5">
                  <HardDrive className="w-3.5 h-3.5 text-[var(--cyan)]" strokeWidth={1.8} />
                  <span>{isAr ? 'الحد الأدنى للتخزين' : 'Min SSD Storage'}</span>
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

              {/* GPU */}
              <div className="space-y-2">
                <span className="micro flex items-center gap-1.5">
                  <Monitor className="w-3.5 h-3.5 text-[var(--cyan)]" strokeWidth={1.8} />
                  <span>{isAr ? 'نوع كارت الشاشة' : 'GPU Requirement'}</span>
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

              {/* Top K */}
              <div className="space-y-2">
                <span className="micro flex items-center gap-1.5">
                  <Sparkles className="w-3.5 h-3.5 text-[var(--cyan)]" strokeWidth={1.8} />
                  <span>{isAr ? 'عدد الترشيحات (Top K)' : 'Max Results (Top K)'}</span>
                </span>
                <div className="seg seg-fluid">
                  {TOP_K_OPTIONS.map((k) => (
                    <button
                      key={k}
                      type="button"
                      aria-pressed={topK === k}
                      onClick={() => onTopKChange(k)}
                      className="font-mono"
                    >
                      {k}
                    </button>
                  ))}
                </div>
              </div>
            </div>

            {/* Brand filter multi-select */}
            <div className="space-y-2 pt-4 border-t border-[var(--border-subtle)]">
              <div className="flex items-center justify-between flex-wrap gap-2">
                <span className="micro flex items-center gap-1.5">
                  <Filter className="w-3.5 h-3.5 text-[var(--cyan)]" strokeWidth={1.8} />
                  <span>{isAr ? 'تفضيل ماركات معينة (اختياري)' : 'Preferred Brands (optional)'}</span>
                </span>
                {activeFiltersCount > 0 && (
                  <button
                    type="button"
                    onClick={onResetAdvancedFilters}
                    className="btn-ghost inline-flex items-center gap-1 !h-auto !py-1"
                  >
                    <RotateCcw className="w-3 h-3" strokeWidth={1.8} />
                    <span>{isAr ? 'إعادة ضبط الشروط' : 'Reset filters'}</span>
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
                          ? '!text-[var(--gold-bright)] !border-[rgba(233,185,73,0.45)] !bg-[var(--gold-dim)]'
                          : 'hover:!border-[var(--border-strong)] hover:!text-[var(--text-primary)]'
                      }`}
                    >
                      {b}
                    </button>
                  )
                })}
              </div>
            </div>

            {/* Optional real-world experience & performance gates */}
            <div className="space-y-3 pt-4 border-t border-[var(--border-subtle)]">
              <div className="flex items-center justify-between flex-wrap gap-2">
                <span className="micro">
                  {isAr
                    ? 'معايير التجربة الميدانية والأداء (اختياري)'
                    : 'Real-World Experience & Performance (optional)'}
                </span>
                {activeMetricDefs.length > 0 && (
                  <span className="ai-chip">
                    {isAr
                      ? `${activeMetricDefs.length} نشطة`
                      : `${activeMetricDefs.length} active`}
                  </span>
                )}
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="space-y-2.5">
                  <div className="flex items-center gap-2">
                    <span className="w-1 h-3.5 rounded-full bg-[var(--cyan)]" />
                    <h4 className="micro !text-[var(--text-secondary)]">
                      {isAr
                        ? 'تجربة الاستخدام الميدانية'
                        : 'Real-World Usage (Review Intelligence)'}
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
                      {isAr
                        ? 'قوة العتاد والأداء'
                        : 'Hardware Power & Performance (Benchmarks)'}
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
      </div>

      {/* 4. Bilingual free-text prompt & primary action */}
      <div className="space-y-2 pt-5 border-t border-[var(--border-subtle)]">
        <label
          htmlFor="prompt-input"
          className="label flex items-center gap-1.5"
        >
          <Sparkles className="w-3.5 h-3.5 text-[var(--cyan)]" strokeWidth={1.8} />
          <span>
            {isAr
              ? 'مواصفات أو ألعاب أو طلبات خاصة (عربي أو إنجليزي)'
              : 'Specific Games, Software, or Demands (AR / EN)'}
          </span>
        </label>
        <div className="flex flex-col sm:flex-row gap-2.5">
          <div className="relative flex-1">
            <input
              id="prompt-input"
              type="text"
              value={promptText}
              onChange={(e) => onPromptChange(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={
                isAr
                  ? 'مثال: عايز لاب يشغل Cyberpunk على Ultra وتبريده مبيسخنش...'
                  : 'e.g. Need good battery, quiet fans, 16GB RAM for heavy coding and Docker...'
              }
              className="field field-with-icon"
            />
            <Sparkles className="w-4 h-4 field-icon" strokeWidth={1.8} />
          </div>

          <button
            type="button"
            onClick={onSubmit}
            disabled={isLoading}
            className="btn btn-primary shrink-0"
          >
            {isLoading ? (
              <>
                <span className="spinner spinner-sm spinner-inverse" />
                <span>{isAr ? 'جاري التحليل...' : 'Evaluating...'}</span>
              </>
            ) : (
              <>
                <Sparkles className="w-4 h-4" strokeWidth={2} />
                <span>{isAr ? 'رشح لي الأفضل' : 'Get Top Matches'}</span>
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  )
}
