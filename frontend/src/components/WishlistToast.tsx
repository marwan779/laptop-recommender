import React from 'react'
import { Heart, X } from 'lucide-react'
import { useUserSession } from '../context/UserSessionContext'

interface WishlistToastProps {
  lang: 'ar' | 'en'
}

export const WishlistToast: React.FC<WishlistToastProps> = ({ lang }) => {
  const { wishlistToastTitle, dismissWishlistToast, setWishlistDrawerOpen } = useUserSession()
  const isAr = lang === 'ar'

  if (!wishlistToastTitle) return null

  return (
    <div
      className="fixed bottom-5 end-5 z-50 max-w-sm wl-toast-enter"
      role="status"
      aria-live="polite"
    >
      <div className="flex items-center gap-3 rounded-[12px] border border-[var(--gold)] bg-[var(--bg-surface)] px-4 py-3 shadow-2xl">
        <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-[var(--gold-dim)] border border-[var(--gold)] text-[var(--gold-bright)]">
          <Heart className="w-4 h-4 fill-current wl-heart-pop" strokeWidth={2} />
        </span>

        <div className="min-w-0 flex-1">
          <div className="text-[12px] font-bold text-[var(--gold-bright)]">
            {isAr ? 'تمت الإضافة إلى المفضلة' : 'Added to Watchlist'}
          </div>
          <div dir="auto" className="truncate text-[12.5px] text-[var(--text-primary)]">
            {wishlistToastTitle}
          </div>
        </div>

        <button
          type="button"
          onClick={() => {
            dismissWishlistToast()
            setWishlistDrawerOpen(true)
          }}
          className="shrink-0 rounded-[7px] border border-[var(--border-subtle)] bg-[var(--bg-raised)] px-2.5 py-1 text-[11.5px] font-semibold text-[var(--cyan)] hover:border-[var(--cyan)]"
        >
          {isAr ? 'ضبط التنبيه' : 'Set alert'}
        </button>

        <button
          type="button"
          onClick={dismissWishlistToast}
          aria-label={isAr ? 'إغلاق' : 'Dismiss'}
          className="text-[var(--text-muted)] hover:text-[var(--text-primary)]"
        >
          <X className="w-3.5 h-3.5" />
        </button>
      </div>
    </div>
  )
}
