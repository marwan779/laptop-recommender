import React from 'react'
import { Laptop, Sparkles, Languages, Database } from 'lucide-react'

interface NavbarProps {
  currentTab: 'recommend' | 'catalog'
  onTabChange: (tab: 'recommend' | 'catalog') => void
  lang: 'ar' | 'en'
  onToggleLang: () => void
}

export const Navbar: React.FC<NavbarProps> = ({
  currentTab,
  onTabChange,
  lang,
  onToggleLang,
}) => {
  const isAr = lang === 'ar'

  return (
    <header className="sticky top-0 z-50 backdrop-blur-md bg-slate-900/80 border-b border-slate-800">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
        {/* Brand */}
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-indigo-600 to-violet-500 flex items-center justify-center shadow-lg shadow-indigo-500/20">
            <Laptop className="w-5 h-5 text-white" />
          </div>
          <div>
            <h1 className="font-bold text-lg text-white tracking-tight flex items-center gap-1.5">
              <span>{isAr ? 'مرشح اللابتوبات الذكي' : 'Smart Laptop Recommender'}</span>
              <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-indigo-500/20 text-indigo-400 border border-indigo-500/30">
                Egypt AI
              </span>
            </h1>
            <p className="text-xs text-slate-400">
              {isAr ? 'مدعوم بالذكاء الاصطناعي وتقييمات المجتمع' : 'Dual-Impact TOPSIS + Real Community Reviews'}
            </p>
          </div>
        </div>

        {/* Navigation Tabs & Actions */}
        <div className="flex items-center gap-3">
          <nav className="flex items-center bg-slate-800/80 p-1 rounded-xl border border-slate-700/60">
            <button
              onClick={() => onTabChange('recommend')}
              className={`flex items-center gap-2 px-3.5 py-1.5 rounded-lg text-xs font-medium transition-all ${
                currentTab === 'recommend'
                  ? 'bg-indigo-600 text-white shadow-md shadow-indigo-500/25'
                  : 'text-slate-300 hover:text-white'
              }`}
            >
              <Sparkles className="w-3.5 h-3.5" />
              <span>{isAr ? 'ترشيح ذكي' : 'AI Recommender'}</span>
            </button>
            <button
              onClick={() => onTabChange('catalog')}
              className={`flex items-center gap-2 px-3.5 py-1.5 rounded-lg text-xs font-medium transition-all ${
                currentTab === 'catalog'
                  ? 'bg-indigo-600 text-white shadow-md shadow-indigo-500/25'
                  : 'text-slate-300 hover:text-white'
              }`}
            >
              <Database className="w-3.5 h-3.5" />
              <span>{isAr ? 'تصفح الكتالوج' : 'Browse Catalog'}</span>
            </button>
          </nav>

          {/* Language Toggle */}
          <button
            onClick={onToggleLang}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-slate-800 border border-slate-700 text-xs font-medium text-slate-300 hover:text-white hover:border-slate-600 transition-colors"
            title={isAr ? 'Switch to English' : 'التحويل إلى العربية'}
          >
            <Languages className="w-3.5 h-3.5 text-indigo-400" />
            <span>{isAr ? 'English' : 'عربي'}</span>
          </button>
        </div>
      </div>
    </header>
  )
}
