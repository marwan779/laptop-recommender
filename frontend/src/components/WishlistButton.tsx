import React, { useState } from 'react'
import { Heart } from 'lucide-react'
import { useUserSession } from '../context/UserSessionContext'

interface WishlistButtonProps {
  canonicalId: string
  titleSnapshot: string
  addedPriceEgp: number
  thumbnailUrlSnapshot?: string | null
  lang: 'ar' | 'en'
  className?: string
  compact?: boolean
}

export const WishlistButton: React.FC<WishlistButtonProps> = ({
  canonicalId,
  titleSnapshot,
  addedPriceEgp,
  thumbnailUrlSnapshot = null,
  lang,
  className = '',
  compact = false,
}) => {
  const { wishlistIds, toggleWishlist } = useUserSession()
  const [busy, setBusy] = useState(false)
  const isSaved = wishlistIds.has(canonicalId)
  const isAr = lang === 'ar'

  const handleClick = async (e: React.MouseEvent) => {
    e.stopPropagation()
    if (busy) return
    setBusy(true)
    try {
      await toggleWishlist({
        canonicalId,
        titleSnapshot,
        addedPriceEgp: Math.max(0, addedPriceEgp || 0),
        thumbnailUrlSnapshot,
      })
    } finally {
      setBusy(false)
    }
  }

  return (
    <button
      type="button"
      onClick={(e) => void handleClick(e)}
      disabled={busy}
      aria-pressed={isSaved}
      aria-label={isSaved ? (isAr ? 'إزالة من المفضلة' : 'Remove from watchlist') : isAr ? 'أضف للمفضلة' : 'Watch price'}
      title={isSaved ? (isAr ? 'في المفضلة' : 'Watching price') : isAr ? 'متابعة السعر' : 'Watch price'}
      className={`btn btn-sm min-h-[38px] ${
        isSaved
          ? 'border border-[var(--gold)] bg-[var(--gold-dim)] text-[var(--gold-bright)]'
          : 'btn-secondary'
      } ${className}`}
    >
      <Heart className={`w-3.5 h-3.5 ${isSaved ? 'fill-current' : ''}`} strokeWidth={2} />
      {!compact && (
        <span>
          {isSaved ? (isAr ? 'متابع' : 'Watching') : isAr ? 'تابع السعر' : 'Watch'}
        </span>
      )}
    </button>
  )
}
