import React from 'react'
import { Laptop, Languages } from 'lucide-react'

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
    <header className="nav">
      <div className="nav-inner">
        {/* Brand */}
        <div className="nav-brand">
          <div className="nav-logo">
            <Laptop className="w-4.5 h-4.5" strokeWidth={1.8} />
          </div>
          <div className="min-w-0">
            <h1 className="nav-title">
              <span>{isAr ? 'مرشح اللابتوبات الذكي' : 'Smart Laptop Recommender'}</span>
            </h1>
            <p className="nav-sub">
              {isAr
                ? 'أسعار حية من المتاجر المصرية + ترتيب TOPSIS'
                : 'Live Egyptian retailer prices · Vector TOPSIS ranking'}
            </p>
          </div>
        </div>

        {/* Navigation Tabs & Actions */}
        <div className="nav-actions">
          <nav className="nav-tabs" aria-label={isAr ? 'التنقل الرئيسي' : 'Primary navigation'}>
            <button
              type="button"
              aria-pressed={currentTab === 'recommend'}
              onClick={() => onTabChange('recommend')}
              className="nav-tab"
            >
              <span>{isAr ? 'ترشيح ذكي' : 'AI Recommender'}</span>
            </button>
            <button
              type="button"
              aria-pressed={currentTab === 'catalog'}
              onClick={() => onTabChange('catalog')}
              className="nav-tab"
            >
              <span>{isAr ? 'تصفح الكتالوج' : 'Browse Catalog'}</span>
            </button>
          </nav>

          {/* Language Toggle */}
          <button
            type="button"
            onClick={onToggleLang}
            className="lang-btn"
            title={isAr ? 'Switch to English' : 'التحويل إلى العربية'}
          >
            <Languages className="w-3.5 h-3.5" strokeWidth={1.8} />
            <span>{isAr ? 'English' : 'عربي'}</span>
          </button>
        </div>
      </div>
    </header>
  )
}
