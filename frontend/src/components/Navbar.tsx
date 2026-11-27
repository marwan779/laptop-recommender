import React from 'react'
import { Laptop, Languages, Moon, Sun, Heart, Bell, LogIn, LogOut } from 'lucide-react'
import { useUserSession } from '../context/UserSessionContext'

interface NavbarProps {
  currentTab: 'recommend' | 'catalog'
  onTabChange: (tab: 'recommend' | 'catalog') => void
  lang: 'ar' | 'en'
  onToggleLang: () => void
  theme: 'light' | 'dark'
  onToggleTheme: () => void
}

export const Navbar: React.FC<NavbarProps> = ({
  currentTab,
  onTabChange,
  lang,
  onToggleLang,
  theme,
  onToggleTheme,
}) => {
  const isAr = lang === 'ar'
  const isDark = theme === 'dark'
  const {
    user,
    wishlistItems,
    unreadCount,
    setAuthModalOpen,
    setWishlistDrawerOpen,
    setNotificationsOpen,
    logout,
  } = useUserSession()

  return (
    <header className="nav">
      <div className="nav-inner">
        <div className="nav-brand">
          <div className="nav-logo" aria-hidden="true">
            <Laptop className="w-4.5 h-4.5" strokeWidth={1.8} />
          </div>
          <div className="min-w-0">
            <h1 className="nav-title">
              <span>{isAr ? 'دليل اللابتوب' : 'Laptop Guide EG'}</span>
            </h1>
            <p className="nav-sub">
              {isAr
                ? 'مقارنة أسعار مصر + مراجعات حقيقية'
                : 'Egypt live prices · Verified real reviews'}
            </p>
          </div>
        </div>

        <div className="nav-actions">
          <nav className="nav-tabs" aria-label={isAr ? 'التنقل الرئيسي' : 'Primary navigation'}>
            <button
              type="button"
              aria-pressed={currentTab === 'recommend'}
              onClick={() => onTabChange('recommend')}
              className="nav-tab"
            >
              <span>{isAr ? 'ترشيح ذكي' : 'Find My Laptop'}</span>
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

          <div className="flex items-center gap-2">
            {user ? (
              <>
                <button
                  type="button"
                  onClick={() => setWishlistDrawerOpen(true)}
                  className="lang-btn relative"
                  aria-label={isAr ? 'قائمة المفضلة' : 'Watchlist'}
                  title={isAr ? 'قائمة المفضلة' : 'Watchlist'}
                >
                  <Heart className="w-4 h-4 text-[var(--gold)]" strokeWidth={1.8} />
                  <span>{isAr ? 'المفضلة' : 'Watchlist'}</span>
                  {wishlistItems.length > 0 && (
                    <span className="rounded-full bg-[var(--gold-dim)] border border-[var(--gold)] px-1.5 py-0.2 text-[10px] font-mono font-bold text-[var(--gold-bright)] num">
                      {wishlistItems.length}
                    </span>
                  )}
                </button>

                <button
                  type="button"
                  onClick={() => setNotificationsOpen(true)}
                  className="lang-btn relative"
                  aria-label={isAr ? 'التنبيهات' : 'Notifications'}
                  title={isAr ? 'التنبيهات' : 'Notifications'}
                >
                  <Bell className="w-4 h-4" strokeWidth={1.8} />
                  {unreadCount > 0 && (
                    <span className="rounded-full bg-[var(--gold)] px-1.5 py-0.2 text-[10px] font-mono font-bold text-[#0A0E13] num">
                      {unreadCount}
                    </span>
                  )}
                </button>

                <button
                  type="button"
                  onClick={() => void logout()}
                  className="lang-btn"
                  aria-label={isAr ? 'تسجيل الخروج' : 'Sign out'}
                  title={`${user.fullName} (${user.email})`}
                >
                  <LogOut className="w-4 h-4" strokeWidth={1.8} />
                  <span className="hidden sm:inline">{isAr ? 'خروج' : 'Sign out'}</span>
                </button>
              </>
            ) : (
              <button
                type="button"
                onClick={() => setAuthModalOpen(true)}
                className="lang-btn border-[var(--gold)] text-[var(--gold-bright)]"
                aria-label={isAr ? 'تسجيل الدخول' : 'Sign in'}
              >
                <LogIn className="w-4 h-4" strokeWidth={1.8} />
                <span>{isAr ? 'دخول' : 'Sign in'}</span>
              </button>
            )}

            <button
              type="button"
              onClick={onToggleTheme}
              className="lang-btn"
              aria-label={isDark ? (isAr ? 'التبديل للوضع النهاري' : 'Switch to light mode') : isAr ? 'التبديل للوضع الليلي' : 'Switch to dark mode'}
              title={isDark ? (isAr ? 'وضع نهاري' : 'Light mode') : isAr ? 'وضع ليلي' : 'Dark mode'}
            >
              {isDark ? (
                <Sun className="w-4 h-4" strokeWidth={1.8} />
              ) : (
                <Moon className="w-4 h-4" strokeWidth={1.8} />
              )}
              <span>{isDark ? (isAr ? 'نهاري' : 'Light') : isAr ? 'ليلي' : 'Dark'}</span>
            </button>

            <button
              type="button"
              onClick={onToggleLang}
              className="lang-btn"
              aria-label={isAr ? 'Switch to English' : 'التحويل إلى العربية'}
              title={isAr ? 'Switch to English' : 'التحويل إلى العربية'}
            >
              <Languages className="w-4 h-4" strokeWidth={1.8} />
              <span>{isAr ? 'English' : 'عربي'}</span>
            </button>
          </div>
        </div>
      </div>
    </header>
  )
}
