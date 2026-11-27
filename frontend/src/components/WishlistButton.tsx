import React, { useEffect, useRef, useState } from 'react'
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

const SPARKS = [
  { tx: '-18px', ty: '-16px', color: '#E9B949' },
  { tx: '0px', ty: '-22px', color: '#34D399' },
  { tx: '18px', ty: '-16px', color: '#F5C95C' },
  { tx: '20px', ty: '8px', color: '#22D3EE' },
  { tx: '-20px', ty: '8px', color: '#E9B949' },
  { tx: '0px', ty: '20px', color: '#34D399' },
] as const

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
  const [bursting, setBursting] = useState(false)
  const isSaved = wishlistIds.has(canonicalId)
  const prevSavedRef = useRef(isSaved)
  const isAr = lang === 'ar'

  useEffect(() => {
    if (!prevSavedRef.current && isSaved) {
      setBursting(true)
      const timer = window.setTimeout(() => setBursting(false), 700)
      prevSavedRef.current = isSaved
      return () => window.clearTimeout(timer)
    }
    prevSavedRef.current = isSaved
  }, [isSaved])

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
      className={`relative overflow-visible btn btn-sm min-h-[38px] transition-all duration-200 ${
        isSaved
          ? 'border border-[var(--gold)] bg-[var(--gold-dim)] text-[var(--gold-bright)]'
          : 'btn-secondary'
      } ${bursting ? 'wl-btn-burst' : ''} ${className}`}
    >
      <span className="relative inline-flex items-center justify-center">
        <Heart
          className={`w-3.5 h-3.5 transition-transform duration-200 ${
            isSaved ? 'fill-current' : ''
          } ${bursting ? 'wl-heart-pop' : ''}`}
          strokeWidth={2}
        />
        {bursting && (
          <>
            <span className="wl-ring-burst" aria-hidden="true" />
            {SPARKS.map((spark, idx) => (
              <span
                key={idx}
                className="wl-spark"
                aria-hidden="true"
                style={
                  {
                    backgroundColor: spark.color,
                    '--tx': spark.tx,
                    '--ty': spark.ty,
                  } as React.CSSProperties
                }
              />
            ))}
          </>
        )}
      </span>
      {!compact && (
        <span>
          {isSaved ? (isAr ? 'متابع' : 'Watching') : isAr ? 'تابع السعر' : 'Watch'}
        </span>
      )}
    </button>
  )
}
