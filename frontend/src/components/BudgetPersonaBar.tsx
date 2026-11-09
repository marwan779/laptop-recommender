import React from 'react'
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
} from 'lucide-react'
import type { PersonaType } from '../types/api'

interface BudgetPersonaBarProps {
  budget: number
  onBudgetChange: (val: number) => void
  selectedPersona: PersonaType
  onPersonaChange: (p: PersonaType) => void
  promptText: string
  onPromptChange: (text: string) => void
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
    id: 'software_engineering',
    icon: <Code2 className="w-4 h-4" />,
    labelAr: 'برمجة وتطوير',
    labelEn: 'Engineering & Code',
    descAr: 'معالج قوي، رامات 16GB+ وكيبورد مريح',
    descEn: 'Heavy CPU, 16GB+ RAM & great keyboard',
  },
  {
    id: 'content_creation',
    icon: <Palette className="w-4 h-4" />,
    labelAr: 'صناعة محتوى',
    labelEn: 'Creator & Video',
    descAr: 'شاشة دقيقة الألوان (100% sRGB/DCI-P3) وأداء متوازن',
    descEn: 'Color-accurate creator screen & power',
  },
  {
    id: 'data_science',
    icon: <BarChart3 className="w-4 h-4" />,
    labelAr: 'داتا وذكاء اصطناعي',
    labelEn: 'Data Science & AI',
    descAr: 'أنوية معالج عالية، كارت CUDA، ورامات قابلة للزيادة',
    descEn: 'High CPU cores, CUDA GPU & RAM expansion',
  },
  {
    id: 'business_mobility',
    icon: <Briefcase className="w-4 h-4" />,
    labelAr: 'بيزنس وتنقل',
    labelEn: 'Business & Ultra-thin',
    descAr: 'بطارية تدوم طويلاً، وزن خفيف < 1.7kg، وشاسيه متين',
    descEn: 'All-day battery, under 1.7kg & sleek build',
  },
  {
    id: 'student_budget',
    icon: <GraduationCap className="w-4 h-4" />,
    labelAr: 'طلاب واقتصادي',
    labelEn: 'Student & Value',
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

export const BudgetPersonaBar: React.FC<BudgetPersonaBarProps> = ({
  budget,
  onBudgetChange,
  selectedPersona,
  onPersonaChange,
  promptText,
  onPromptChange,
  onSubmit,
  isLoading,
  lang,
}) => {
  const isAr = lang === 'ar'

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      onSubmit()
    }
  }

  return (
    <div className="bg-slate-900/90 border border-slate-800 rounded-3xl p-6 shadow-2xl backdrop-blur-xl relative overflow-hidden">
      {/* Decorative gradient glow */}
      <div className="absolute -top-24 -right-24 w-72 h-72 bg-indigo-500/10 rounded-full blur-3xl pointer-events-none" />
      <div className="absolute -bottom-24 -left-24 w-72 h-72 bg-violet-500/10 rounded-full blur-3xl pointer-events-none" />

      {/* 1. Header & Budget Section */}
      <div className="space-y-4 mb-6">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
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

          {/* Current Budget Display */}
          <div className="flex items-baseline gap-2 bg-slate-800/80 px-4 py-2 rounded-2xl border border-slate-700">
            <span className="text-xs text-slate-400">{isAr ? 'الميزانية القصوى:' : 'Max Budget:'}</span>
            <span className="text-xl font-extrabold text-transparent bg-clip-text bg-gradient-to-r from-indigo-400 to-violet-300">
              {budget.toLocaleString()}
            </span>
            <span className="text-xs font-semibold text-slate-400">{isAr ? 'ج.م' : 'EGP'}</span>
          </div>
        </div>

        {/* Budget Slider */}
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

      {/* 2. Persona Selector */}
      <div className="space-y-2 mb-6">
        <label className="text-xs font-semibold text-slate-300 uppercase tracking-wider flex items-center gap-1.5">
          <Filter className="w-3.5 h-3.5 text-indigo-400" />
          <span>{isAr ? 'نوع الاستخدام الأساسي (البرسونا)' : 'Primary Usage Persona'}</span>
        </label>
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-7 gap-2.5">
          {PERSONAS.map((p) => {
            const isSelected = selectedPersona === p.id
            return (
              <button
                key={p.id}
                onClick={() => onPersonaChange(p.id)}
                className={`p-3 rounded-2xl border text-left flex flex-col justify-between transition-all relative overflow-hidden group ${
                  isSelected
                    ? 'bg-indigo-600/20 border-indigo-500 shadow-lg shadow-indigo-500/10 text-white'
                    : 'bg-slate-800/50 border-slate-800 hover:border-slate-700 text-slate-300 hover:text-white'
                }`}
              >
                {isSelected && (
                  <div className="absolute top-0 right-0 w-8 h-8 bg-indigo-500/20 rounded-bl-full pointer-events-none" />
                )}
                <div className={`p-2 rounded-xl w-fit mb-2 ${isSelected ? 'bg-indigo-600 text-white' : 'bg-slate-800 text-slate-400 group-hover:text-white'}`}>
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

      {/* 3. Bilingual Free-Text Prompt & Search Action */}
      <div className="space-y-2">
        <label className="text-xs font-semibold text-slate-300 uppercase tracking-wider flex items-center gap-1.5">
          <Search className="w-3.5 h-3.5 text-indigo-400" />
          <span>{isAr ? 'مواصفات أو ألعاب أو طلبات خاصة (عربي أو إنجليزي)' : 'Specific Games, Software, or Demands (AR / EN)'}</span>
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
              className="w-full px-4 py-3.5 pl-11 bg-slate-950/70 border border-slate-700/80 rounded-2xl text-sm text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-all"
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
