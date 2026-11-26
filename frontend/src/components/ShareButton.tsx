import React, { useEffect, useState } from 'react'
import { Check, Share2 } from 'lucide-react'

interface ShareButtonProps {
  canonicalId: string
  title: string
  priceEgp: number
  cheapestStore: string
  lang: 'ar' | 'en'
  compact?: boolean
  className?: string
}

export const ShareButton: React.FC<ShareButtonProps> = ({
  canonicalId,
  title,
  priceEgp,
  cheapestStore,
  lang,
  compact = true,
  className = '',
}) => {
  const isAr = lang === 'ar'
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    if (!copied) return
    const timer = window.setTimeout(() => setCopied(false), 2000)
    return () => window.clearTimeout(timer)
  }, [copied])

  const handleShare = async (e: React.MouseEvent<HTMLButtonElement>) => {
    e.stopPropagation()
    const shareUrl = `${window.location.origin}/share/${encodeURIComponent(canonicalId)}?lang=${lang}`
    const priceText = priceEgp > 0 ? priceEgp.toLocaleString('en-US') : ''
    const shareText = priceText
      ? isAr
        ? `${title} — ${priceText} ج.م في ${cheapestStore}`
        : `${title} — ${priceText} EGP at ${cheapestStore}`
      : title

    if (typeof navigator !== 'undefined' && typeof navigator.share === 'function') {
      try {
        await navigator.share({ title, text: shareText, url: shareUrl })
        return
      } catch (err) {
        if ((err as DOMException)?.name === 'AbortError') return
      }
    }

    try {
      await navigator.clipboard.writeText(shareUrl)
      setCopied(true)
    } catch {
      const textarea = document.createElement('textarea')
      textarea.value = shareUrl
      textarea.style.position = 'fixed'
      textarea.style.opacity = '0'
      document.body.appendChild(textarea)
      textarea.select()
      document.execCommand('copy')
      document.body.removeChild(textarea)
      setCopied(true)
    }
  }

  const label = copied
    ? isAr
      ? 'تم النسخ'
      : 'Copied'
    : isAr
    ? 'مشاركة'
    : 'Share'

  return (
    <button
      type="button"
      onClick={handleShare}
      aria-label={label}
      title={label}
      className={`btn btn-sm min-h-[42px] ${
        copied
          ? 'border border-[var(--success)] bg-[var(--success-dim)] text-[var(--success)]'
          : 'btn-secondary'
      } ${compact ? '!flex-none w-[42px] !px-0' : ''} ${className}`}
    >
      {copied ? <Check className="w-3.5 h-3.5" strokeWidth={2.4} /> : <Share2 className="w-3.5 h-3.5" strokeWidth={2} />}
      {!compact && <span>{label}</span>}
    </button>
  )
}
