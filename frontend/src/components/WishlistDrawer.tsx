import React, { useState } from 'react'
import { Heart, Trash2, X, Check } from 'lucide-react'
import { useUserSession } from '../context/UserSessionContext'
import type { WishlistItem } from '../types/users'

interface WishlistDrawerProps {
  lang: 'ar' | 'en'
}

const WishlistItemRow: React.FC<{
  item: WishlistItem
  lang: 'ar' | 'en'
  onSave: (
    canonicalId: string,
    prefs: {
      targetPriceEgp: number | null
      notifyOnPriceDrop: boolean
      notifyOnAnyChange: boolean
      notifyOnRestock: boolean
    },
  ) => Promise<WishlistItem>
  onRemove: (canonicalId: string) => Promise<void>
}> = ({ item, lang, onSave, onRemove }) => {
  const isAr = lang === 'ar'
  const [targetInput, setTargetInput] = useState<string>(
    item.targetPriceEgp != null ? String(item.targetPriceEgp) : '',
  )
  const [notifyDrop, setNotifyDrop] = useState<boolean>(item.notifyOnPriceDrop)
  const [notifyRestock, setNotifyRestock] = useState<boolean>(item.notifyOnRestock)
  const [notifyAny, setNotifyAny] = useState<boolean>(item.notifyOnAnyChange)
  const [saving, setSaving] = useState(false)
  const [savedFlag, setSavedFlag] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleSave = async () => {
    setError(null)
    const parsed = targetInput.trim() === '' ? null : Number(targetInput.trim())
    if (parsed !== null && (!Number.isFinite(parsed) || parsed <= 0)) {
      setError(isAr ? 'أدخل سعراً مستهدفاً صحيحاً' : 'Enter a valid target price > 0')
      return
    }
    setSaving(true)
    try {
      await onSave(item.canonicalId, {
        targetPriceEgp: parsed,
        notifyOnPriceDrop: notifyDrop,
        notifyOnAnyChange: notifyAny,
        notifyOnRestock: notifyRestock,
      })
      setSavedFlag(true)
      window.setTimeout(() => setSavedFlag(false), 1800)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="rounded-[10px] border border-[var(--border-subtle)] bg-[var(--bg-raised)] p-3.5 space-y-3">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <h4 dir="auto" className="text-[14px] font-semibold text-[var(--text-primary)] leading-snug">
            {item.titleSnapshot}
          </h4>
          <div className="mt-1 flex items-center gap-2 flex-wrap">
            <span className="font-mono text-[13px] font-bold text-[var(--gold)] num">
              {item.addedPriceEgp.toLocaleString('en-US')} {isAr ? 'ج.م' : 'EGP'}
            </span>
            <span className="text-[11px] font-mono text-[var(--text-muted)]">
              {item.canonicalId}
            </span>
          </div>
        </div>
        <button
          type="button"
          onClick={() => void onRemove(item.canonicalId)}
          className="rounded-[7px] border border-[var(--border-subtle)] p-1.5 text-[var(--text-muted)] hover:border-[var(--danger)] hover:text-[var(--danger)]"
          title={isAr ? 'إزالة من المفضلة' : 'Remove from wishlist'}
          aria-label={isAr ? 'إزالة من المفضلة' : 'Remove from wishlist'}
        >
          <Trash2 className="w-3.5 h-3.5" />
        </button>
      </div>

      <div className="space-y-2 border-t border-[var(--border-subtle)] pt-2.5">
        <div className="flex items-center gap-2">
          <label className="text-[11.5px] text-[var(--text-secondary)] shrink-0">
            {isAr ? 'السعر المستهدف (ج.م):' : 'Target price (EGP):'}
          </label>
          <input
            type="number"
            min={1}
            dir="ltr"
            value={targetInput}
            onChange={(e) => setTargetInput(e.target.value)}
            placeholder={isAr ? 'أي انخفاض' : 'Any drop'}
            className="w-full rounded-[6px] border border-[var(--border-subtle)] bg-[var(--bg-input)] px-2.5 py-1 text-[12.5px] text-[var(--text-primary)] font-mono num focus:border-[var(--gold)] focus:outline-none"
          />
        </div>

        <div className="flex flex-wrap gap-3 text-[11.5px] text-[var(--text-secondary)]">
          <label className="inline-flex items-center gap-1.5 cursor-pointer">
            <input
              type="checkbox"
              checked={notifyDrop}
              onChange={(e) => setNotifyDrop(e.target.checked)}
              className="accent-[var(--gold)]"
            />
            <span>{isAr ? 'انخفاض السعر' : 'Price drop'}</span>
          </label>
          <label className="inline-flex items-center gap-1.5 cursor-pointer">
            <input
              type="checkbox"
              checked={notifyRestock}
              onChange={(e) => setNotifyRestock(e.target.checked)}
              className="accent-[var(--gold)]"
            />
            <span>{isAr ? 'عودة التوفر' : 'Restock'}</span>
          </label>
          <label className="inline-flex items-center gap-1.5 cursor-pointer">
            <input
              type="checkbox"
              checked={notifyAny}
              onChange={(e) => setNotifyAny(e.target.checked)}
              className="accent-[var(--gold)]"
            />
            <span>{isAr ? 'أي تغيير' : 'Any change'}</span>
          </label>
        </div>

        {error && <p className="text-[11.5px] text-[var(--danger)]">{error}</p>}

        <button
          type="button"
          onClick={() => void handleSave()}
          disabled={saving}
          className="btn btn-secondary btn-sm w-full justify-center !min-h-[34px]"
        >
          {savedFlag ? (
            <>
              <Check className="w-3.5 h-3.5 text-[var(--emerald)]" />
              <span>{isAr ? 'تم الحفظ' : 'Saved'}</span>
            </>
          ) : saving ? (
            <span>{isAr ? 'جاري الحفظ...' : 'Saving...'}</span>
          ) : (
            <span>{isAr ? 'حفظ تفضيلات التنبيه' : 'Save alert settings'}</span>
          )}
        </button>
      </div>
    </div>
  )
}

export const WishlistDrawer: React.FC<WishlistDrawerProps> = ({ lang }) => {
  const {
    wishlistDrawerOpen,
    setWishlistDrawerOpen,
    wishlistItems,
    saveWishlistPreferences,
    removeWishlistItem,
  } = useUserSession()
  const isAr = lang === 'ar'

  if (!wishlistDrawerOpen) return null

  return (
    <div
      className="fixed inset-0 z-50 flex justify-end bg-black/70 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-label={isAr ? 'قائمة المفضلة' : 'Wishlist'}
      onClick={() => setWishlistDrawerOpen(false)}
    >
      <aside
        className="flex h-full w-full max-w-md flex-col border-s border-[var(--border-strong)] bg-[var(--bg-surface)] shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-[var(--border-subtle)] bg-[var(--bg-raised)] px-5 py-4">
          <div className="flex items-center gap-2">
            <Heart className="w-4 h-4 text-[var(--gold)] fill-current" />
            <h2 className="font-display text-[16px] font-bold text-[var(--text-primary)]">
              {isAr ? 'المفضلة وتنبيهات الأسعار' : 'Watchlist & Price Alerts'}
            </h2>
            <span className="rounded-full bg-[var(--bg-input)] border border-[var(--border-subtle)] px-2 py-0.5 text-[11px] font-mono text-[var(--text-secondary)] num">
              {wishlistItems.length}
            </span>
          </div>
          <button
            type="button"
            onClick={() => setWishlistDrawerOpen(false)}
            className="rounded-lg border border-[var(--border-subtle)] p-1.5 text-[var(--text-muted)] hover:border-[var(--border-strong)] hover:text-[var(--text-primary)]"
            aria-label={isAr ? 'إغلاق' : 'Close'}
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-4 space-y-3">
          {wishlistItems.length === 0 ? (
            <div className="rounded-[10px] border border-[var(--border-subtle)] bg-[var(--bg-raised)] p-8 text-center space-y-2">
              <Heart className="w-7 h-7 text-[var(--text-muted)] mx-auto" />
              <p className="text-[14px] font-semibold text-[var(--text-primary)]">
                {isAr ? 'قائمة المفضلة فارغة' : 'Your watchlist is empty'}
              </p>
              <p className="text-[12px] text-[var(--text-muted)]">
                {isAr
                  ? 'اضغط على أيقونة القلب في أي لابتوب لمتابعة أسعاره وتلقي التنبيهات.'
                  : 'Click the heart button on any laptop to track prices and get alerts.'}
              </p>
            </div>
          ) : (
            wishlistItems.map((item) => (
              <WishlistItemRow
                key={item.id}
                item={item}
                lang={lang}
                onSave={saveWishlistPreferences}
                onRemove={removeWishlistItem}
              />
            ))
          )}
        </div>
      </aside>
    </div>
  )
}
