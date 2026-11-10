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
  Search,
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
    icon: <Gamepad2 className="w-4 h-4" />,
    labelAr: 'ألعاب ثقيلة',
    labelEn: 'Heavy Gaming',
    descAr: 'كارت شاشة منفصل قوي وشاشة سريعة 144Hz+',
    descEn: 'Dedicated dGPU & 144Hz+ display',
  },
  {
    id: 'programming',
    icon: <Code2 className="w-4 h-4" />,
    labelAr: 'برمجة وتطوير',
    labelEn: 'Software Engineering',
    descAr: 'معالج قوي، رامات 16GB+ وكيبورد مريح',
    descEn: 'Heavy CPU, 16GB+ RAM & great keyboard',
  },
  {
    id: 'content_creation',
    icon: <Palette className="w-4 h-4" />,
    labelAr: 'صناعة محتوى',
    labelEn: 'Content Creation',
    descAr: 'شاشة دقيقة الألوان (100% sRGB/DCI-P3) وأداء متوازن',
    descEn: 'Color-accurate creator screen & power',
  },
  {
    id: 'ai_and_game_dev',
    icon: <BarChart3 className="w-4 h-4" />,
    labelAr: 'ذكاء اصطناعي وتطوير ألعاب',
    labelEn: 'AI & Game Dev',
    descAr: 'أنوية معالج عالية، كارت CUDA، ورامات قابلة للزيادة',
    descEn: 'High CPU cores, CUDA GPU & RAM expansion',
  },
  {
    id: 'business_and_mobility',
    icon: <Briefcase className="w-4 h-4" />,
    labelAr: 'بيزنس وتنقل',
    labelEn: 'Business & Ultra-thin',
    descAr: 'بطارية تدوم طويلاً، وزن خفيف < 1.7kg، وشاسيه متين',
    descEn: 'All-day battery, under 1.7kg & sleek build',
  },
  {
    id: 'student_and_office',
    icon: <GraduationCap className="w-4 h-4" />,
    labelAr: 'دراسة وأوفيس',
    labelEn: 'Student & Office',
    descAr: 'أفضل قيمة مقابل السعر للدراسة والأوفيس والمحاضرات',
    descEn: 'Best price-to-performance for studies & daily use',
  },
  {
    id: 'balanced',
    icon: <Scale className="w-4 h-4" />,
    labelAr: 'استخدام متوازن',
    labelEn: 'Balanced All-Rounder',
    descAr: 'توازن ذكي بين الأداء والسعر والاعتمادية',
    descEn: 'Smart balance of power, durability & price',
  },
]

const BUDGET_PRESETS = [25000, 35000, 45000, 60000, 85000, 120000]
const AVAILABLE_BRANDS = ['ASUS', 'Lenovo', 'HP', 'Dell', 'Apple', 'Acer', 'MSI', 'Gigabyte']
const TOP_K_OPTIONS = [3, 5, 8, 12, 15]

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

  return (
    <div className="bg-slate-900/90 border border-slate-800 rounded-3xl p-5 sm:p-6 shadow-2xl backdrop-blur-xl relative overflow-hidden">
      {/* Decorative gradient glow */}
      <div className="absolute -top-24 -right-24 w-72 h-72 bg-indigo-500/10 rounded-full blur-3xl pointer-events-none" />
      <div className="absolute -bottom-24 -left-24 w-72 h-72 bg-violet-500/10 rounded-full blur-3xl pointer-events-none" />

      {/* 1. Header & Budget Section */}
      <div className="space-y-4 mb-6">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div>
            <h2 className="text-lg font-bold text-white flex items-center gap-2">
              <Sparkles className="w-5 h-5 text-indigo-400" />
              <span>{isAr ? 'حدد ميزانيتك واستخدامك' : 'Set Your Budget & Usage'}</span>
            </h2>
            <p className="text-xs text-slate-400">
              {isAr
                ? 'خوارزمية TOPSIS تختار اللابتوب صاحب أعلى قيمة فعلية داخل نطاق ميزانيتك'
                : 'Vector TOPSIS ranks candidates to find the highest value within your budget'}
            </p>
          </div>

          {/* Interactive Editable Budget Input Field */}
          <div className="flex items-center gap-2 bg-slate-950/80 px-4 py-2 rounded-2xl border border-slate-700/80 focus-within:border-indigo-500 focus-within:ring-2 focus-within:ring-indigo-500/30 transition-all shadow-inner">
            <span className="text-xs text-slate-400 font-semibold whitespace-nowrap">
              {isAr ? 'الميزانية:' : 'Budget:'}
            </span>
            <input
              type="number"
              min={10000}
              max={250000}
              step={1000}
              value={budget || ''}
              onChange={handleBudgetInput}
              aria-label={isAr ? 'الميزانية القصوى بالجنيه' : 'Max budget in EGP'}
              className="w-28 sm:w-32 bg-transparent text-xl font-extrabold text-indigo-300 font-mono text-center focus:outline-none [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
            />
            <span className="text-xs font-bold text-slate-400">{isAr ? 'ج.م' : 'EGP'}</span>
          </div>
        </div>

        {/* Budget Slider & Quick Presets */}
        <div className="space-y-2">
          <input
            type="range"
            min={12000}
            max={150000}
            step={1000}
            value={budget}
            onChange={(e) => onBudgetChange(Number(e.target.value))}
            className="w-full h-2.5 bg-slate-800 rounded-lg appearance-none cursor-pointer accent-indigo-500"
          />
          <div className="flex items-center justify-between text-xs text-slate-400 font-mono">
            <span>12,000 EGP</span>
            <div className="hidden sm:flex gap-2">
              {BUDGET_PRESETS.map((preset) => (
                <button
                  key={preset}
                  type="button"
                  onClick={() => onBudgetChange(preset)}
                  className={`px-2.5 py-1 rounded-lg text-xs transition-all ${
                    budget === preset
                      ? 'bg-indigo-600 text-white font-bold'
                      : 'bg-slate-800/60 text-slate-400 hover:text-white hover:bg-slate-700/60'
                  }`}
                >
                  {(preset / 1000).toFixed(0)}k
                </button>
              ))}
            </div>
            <span>150,000+ EGP</span>
          </div>
        </div>
      </div>

      {/* 2. Persona Selector (Multi-Select Enabled) */}
      <div className="space-y-2.5 mb-5">
        <div className="flex items-center justify-between flex-wrap gap-2">
          <label className="text-xs font-semibold text-slate-300 uppercase tracking-wider flex items-center gap-1.5">
            <Filter className="w-3.5 h-3.5 text-indigo-400" />
            <span>
              {isAr
                ? 'فئات الاستخدام (يمكنك اختيار أكثر من فئة لدمجها):'
                : 'Usage Personas (Select one or multiple to blend):'}
            </span>
          </label>

          {selectedPersonas.length > 1 && (
            <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-xl bg-indigo-500/15 border border-indigo-500/30 text-indigo-300 text-[11px] font-medium">
              <Layers className="w-3.5 h-3.5 text-indigo-400" />
              <span>
                {isAr
                  ? `دمج ذكي مفعل (${selectedPersonas.length} فئات)`
                  : `Smart Blending Active (${selectedPersonas.length} personas)`}
              </span>
            </div>
          )}
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-7 gap-2.5">
          {PERSONAS.map((p) => {
            const isSelected = selectedPersonas.includes(p.id)
            return (
              <button
                key={p.id}
                type="button"
                onClick={() => onTogglePersona(p.id)}
                className={`p-3 rounded-2xl border text-left flex flex-col justify-between transition-all relative overflow-hidden group ${
                  isSelected
                    ? 'bg-indigo-600/20 border-indigo-500 shadow-lg shadow-indigo-500/20 text-white ring-1 ring-indigo-500/50'
                    : 'bg-slate-800/50 border-slate-800 hover:border-slate-700 text-slate-300 hover:text-white'
                }`}
              >
                {isSelected && (
                  <div className="absolute top-1.5 right-1.5 w-5 h-5 bg-indigo-500 rounded-full flex items-center justify-center text-white shadow-sm">
                    <Check className="w-3 h-3 stroke-[3]" />
                  </div>
                )}
                <div
                  className={`p-2 rounded-xl w-fit mb-2 ${
                    isSelected
                      ? 'bg-indigo-600 text-white'
                      : 'bg-slate-800 text-slate-400 group-hover:text-white'
                  }`}
                >
                  {p.icon}
                </div>
                <div>
                  <div className="font-semibold text-xs leading-tight">
                    {isAr ? p.labelAr : p.labelEn}
                  </div>
                  <div className="text-[10px] text-slate-400 mt-1 line-clamp-1">
                    {isAr ? p.descAr : p.descEn}
                  </div>
                </div>
              </button>
            )
          })}
        </div>
      </div>

      {/* 3. Collapsible Advanced Hardware Filters & Top K Accordion */}
      <div className="mb-5">
        <button
          type="button"
          onClick={() => setShowAdvanced(!showAdvanced)}
          className="w-full flex items-center justify-between p-3 rounded-2xl bg-slate-950/60 hover:bg-slate-950/80 border border-slate-800 transition-colors text-left"
        >
          <div className="flex items-center gap-2">
            <SlidersHorizontal className="w-4 h-4 text-indigo-400" />
            <span className="text-xs font-bold text-white">
              {isAr ? 'شروط العتاد المتقدمة (الرام، التخزين، كارت الشاشة، الماركات)' : 'Advanced Hardware Gates (RAM, Storage, GPU, Brands)'}
            </span>
            {activeFiltersCount > 0 && (
              <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-indigo-600 text-white font-mono">
                {activeFiltersCount}
              </span>
            )}
          </div>
          <div className="flex items-center gap-1.5 text-xs text-indigo-400 font-semibold">
            <span>{showAdvanced ? (isAr ? 'إخفاء' : 'Collapse') : (isAr ? 'تخصيص' : 'Customize')}</span>
            {showAdvanced ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
          </div>
        </button>

        {showAdvanced && (
          <div className="mt-2.5 p-4 rounded-2xl bg-slate-950/80 border border-slate-800/80 space-y-4 animate-in fade-in duration-200">
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
              {/* RAM Minimum Gate */}
              <div className="space-y-1.5">
                <label className="text-[11px] font-semibold text-slate-300 flex items-center gap-1">
                  <Cpu className="w-3.5 h-3.5 text-indigo-400" />
                  <span>{isAr ? 'الحد الأدنى للرام:' : 'Min RAM Capacity:'}</span>
                </label>
                <div className="flex gap-1.5">
                  {[
                    { val: null, label: isAr ? 'الكل' : 'Any' },
                    { val: 8, label: '8GB+' },
                    { val: 16, label: '16GB+' },
                    { val: 32, label: '32GB+' },
                  ].map((opt) => (
                    <button
                      key={String(opt.val)}
                      type="button"
                      onClick={() => onMinRamChange(opt.val)}
                      className={`flex-1 py-1.5 px-2 rounded-xl text-xs font-medium border transition-all ${
                        minRam === opt.val
                          ? 'bg-indigo-600 text-white border-indigo-500 shadow-md shadow-indigo-600/20 font-bold'
                          : 'bg-slate-900 border-slate-800 text-slate-400 hover:text-white'
                      }`}
                    >
                      {opt.label}
                    </button>
                  ))}
                </div>
              </div>

              {/* Storage SSD Minimum Gate */}
              <div className="space-y-1.5">
                <label className="text-[11px] font-semibold text-slate-300 flex items-center gap-1">
                  <HardDrive className="w-3.5 h-3.5 text-indigo-400" />
                  <span>{isAr ? 'الحد الأدنى للتخزين:' : 'Min SSD Storage:'}</span>
                </label>
                <div className="flex gap-1.5">
                  {[
                    { val: null, label: isAr ? 'الكل' : 'Any' },
                    { val: 512, label: '512GB+' },
                    { val: 1024, label: '1TB+' },
                  ].map((opt) => (
                    <button
                      key={String(opt.val)}
                      type="button"
                      onClick={() => onMinStorageChange(opt.val)}
                      className={`flex-1 py-1.5 px-2 rounded-xl text-xs font-medium border transition-all ${
                        minStorage === opt.val
                          ? 'bg-indigo-600 text-white border-indigo-500 shadow-md shadow-indigo-600/20 font-bold'
                          : 'bg-slate-900 border-slate-800 text-slate-400 hover:text-white'
                      }`}
                    >
                      {opt.label}
                    </button>
                  ))}
                </div>
              </div>

              {/* GPU Requirement Gate */}
              <div className="space-y-1.5">
                <label className="text-[11px] font-semibold text-slate-300 flex items-center gap-1">
                  <Monitor className="w-3.5 h-3.5 text-indigo-400" />
                  <span>{isAr ? 'نوع كارت الشاشة:' : 'GPU Requirement:'}</span>
                </label>
                <div className="flex gap-1.5">
                  {[
                    { val: null, label: isAr ? 'الكل' : 'Any' },
                    { val: true, label: isAr ? 'خارجي (dGPU)' : 'dGPU Only' },
                    { val: false, label: isAr ? 'مدمج (iGPU)' : 'iGPU Only' },
                  ].map((opt) => (
                    <button
                      key={String(opt.val)}
                      type="button"
                      onClick={() => onRequireDgpuChange(opt.val)}
                      className={`flex-1 py-1.5 px-2 rounded-xl text-xs font-medium border transition-all ${
                        requireDgpu === opt.val
                          ? 'bg-indigo-600 text-white border-indigo-500 shadow-md shadow-indigo-600/20 font-bold'
                          : 'bg-slate-900 border-slate-800 text-slate-400 hover:text-white'
                      }`}
                    >
                      {opt.label}
                    </button>
                  ))}
                </div>
              </div>

              {/* Top K Selector */}
              <div className="space-y-1.5">
                <label className="text-[11px] font-semibold text-slate-300 flex items-center gap-1">
                  <Sparkles className="w-3.5 h-3.5 text-indigo-400" />
                  <span>{isAr ? 'عدد الترشيحات المطلوبة:' : 'Max Returned Results (Top K):'}</span>
                </label>
                <div className="flex gap-1.5">
                  {TOP_K_OPTIONS.map((k) => (
                    <button
                      key={k}
                      type="button"
                      onClick={() => onTopKChange(k)}
                      className={`flex-1 py-1.5 px-2 rounded-xl text-xs font-mono font-medium border transition-all ${
                        topK === k
                          ? 'bg-indigo-600 text-white border-indigo-500 shadow-md shadow-indigo-600/20 font-bold'
                          : 'bg-slate-900 border-slate-800 text-slate-400 hover:text-white'
                      }`}
                    >
                      {k}
                    </button>
                  ))}
                </div>
              </div>
            </div>

            {/* Brand Filter Multi-Select */}
            <div className="space-y-1.5 pt-2 border-t border-slate-800/80">
              <div className="flex items-center justify-between">
                <label className="text-[11px] font-semibold text-slate-300 flex items-center gap-1">
                  <Filter className="w-3.5 h-3.5 text-indigo-400" />
                  <span>{isAr ? 'تفضيل ماركات معينة (اختياري):' : 'Preferred Brands (Optional):'}</span>
                </label>
                {activeFiltersCount > 0 && (
                  <button
                    type="button"
                    onClick={onResetAdvancedFilters}
                    className="text-[11px] text-slate-400 hover:text-rose-400 transition-colors inline-flex items-center gap-1"
                  >
                    <RotateCcw className="w-3 h-3" />
                    <span>{isAr ? 'إعادة ضبط الشروط' : 'Reset filters'}</span>
                  </button>
                )}
              </div>
              <div className="flex flex-wrap gap-1.5">
                {AVAILABLE_BRANDS.map((b) => {
                  const isChecked = selectedBrands.includes(b)
                  return (
                    <button
                      key={b}
                      type="button"
                      onClick={() => onToggleBrand(b)}
                      className={`px-3 py-1 rounded-xl text-xs font-medium border transition-all ${
                        isChecked
                          ? 'bg-indigo-600/30 border-indigo-500 text-white font-semibold ring-1 ring-indigo-500/40'
                          : 'bg-slate-900 border-slate-800 text-slate-400 hover:text-white hover:bg-slate-800'
                      }`}
                    >
                      {b}
                    </button>
                  )
                })}
              </div>
            </div>

            {/* Optional Real-World Experience & Performance Metric Gates */}
            <div className="space-y-2 pt-2 border-t border-slate-800/80">
              <div className="flex items-center justify-between">
                <label className="text-[11px] font-semibold text-slate-300 flex items-center gap-1">
                  <Sparkles className="w-3.5 h-3.5 text-indigo-400" />
                  <span>
                    {isAr
                      ? 'معايير التجربة الميدانية والأداء (اختياري):'
                      : 'Real-World Experience & Performance (Optional):'}
                  </span>
                </label>
                {activeMetricDefs.length > 0 && (
                  <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-600 text-white font-mono">
                    {isAr
                      ? `${activeMetricDefs.length} نشطة`
                      : `${activeMetricDefs.length} active`}
                  </span>
                )}
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="space-y-3">
                  <div className="flex items-center gap-2">
                    <span className="w-1.5 h-4 rounded-full bg-emerald-400" />
                    <h4 className="text-[11px] font-bold uppercase tracking-wider text-emerald-300">
                      {isAr
                        ? 'تجربة الاستخدام الميدانية (Review Intelligence)'
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

                <div className="space-y-3">
                  <div className="flex items-center gap-2">
                    <span className="w-1.5 h-4 rounded-full bg-sky-400" />
                    <h4 className="text-[11px] font-bold uppercase tracking-wider text-sky-300">
                      {isAr
                        ? 'قوة العتاد والأداء (Hardware Benchmarks)'
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

      {/* 4. Bilingual Free-Text Prompt & Search Action */}
      <div className="space-y-2">
        <label className="text-xs font-semibold text-slate-300 uppercase tracking-wider flex items-center gap-1.5">
          <Search className="w-3.5 h-3.5 text-indigo-400" />
          <span>
            {isAr
              ? 'مواصفات أو ألعاب أو طلبات خاصة (عربي أو إنجليزي)'
              : 'Specific Games, Software, or Demands (AR / EN)'}
          </span>
        </label>
        <div className="flex flex-col sm:flex-row gap-2.5">
          <div className="relative flex-1">
            <input
              type="text"
              value={promptText}
              onChange={(e) => onPromptChange(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={
                isAr
                  ? 'مثال: عايز لاب يشغل Cyberpunk على Ultra وتبريده مبيسخنش...'
                  : 'e.g. Need good battery, quiet fans, 16GB RAM for heavy coding and Docker...'
              }
              className="w-full px-4 py-3.5 pl-11 bg-slate-950/70 border border-slate-700/80 rounded-2xl text-sm text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-all shadow-inner"
            />
            <Sparkles className="w-4 h-4 text-indigo-400 absolute left-4 top-1/2 -translate-y-1/2" />
          </div>

          <button
            onClick={onSubmit}
            disabled={isLoading}
            className="px-6 py-3.5 rounded-2xl bg-gradient-to-r from-indigo-600 to-violet-600 hover:from-indigo-500 hover:to-violet-500 text-white font-semibold text-sm shadow-xl shadow-indigo-600/25 flex items-center justify-center gap-2 transition-all disabled:opacity-50 disabled:cursor-not-allowed shrink-0"
          >
            {isLoading ? (
              <>
                <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                <span>{isAr ? 'جاري التحليل...' : 'Evaluating...'}</span>
              </>
            ) : (
              <>
                <Sparkles className="w-4 h-4" />
                <span>{isAr ? 'رشح لي الأفضل' : 'Get Top Matches'}</span>
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  )
}
