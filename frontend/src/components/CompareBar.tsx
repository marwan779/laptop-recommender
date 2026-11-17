import React from 'react'
import { Scale, X } from 'lucide-react'
import type { CompareEntry } from '../types/compare'

interface CompareBarProps {
  entries: CompareEntry[]
  lang: 'ar' | 'en'
  onRemove: (id: string) => void
  onClear: () => void
  onOpen: () => void
}

export const CompareBar: React.FC<CompareBarProps> = ({
  entries,
  lang,
  onRemove,
  onClear,
  onOpen,
}) => {
  const isAr = lang === 'ar'
  if (entries.length === 0) return null

  return (
    <div className="fixed inset-x-0 bottom-0 z-40 px-3 pb-3 pointer-events-none">
      <div className="pointer-events-auto mx-auto max-w-3xl rounded-[14px] border border-[var(--border-strong)] bg-[var(--bg-overlay)] shadow-[var(--shadow-2)] px-3 py-2.5">
        <div className="flex items-center gap-2.5 flex-wrap">
          <div className="flex items-center gap-1.5 min-w-0 flex-1 flex-wrap">
            {entries.map((entry) => (
              <div
                key={entry.id}
                className="relative flex items-center gap-1.5 rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-raised)] ps-1 pe-6 py-1 min-w-0 max-w-[150px]"
              >
                <div className="w-7 h-7 rounded-[5px] overflow-hidden bg-[var(--studio-well)] shrink-0">
                  <img src={entry.thumbnail_url} alt="" className="w-full h-full object-contain" />
                </div>
                <span dir="auto" className="text-[11px] font-medium text-[var(--text-primary)] truncate">
                  {entry.title}
                </span>
                <button
                  type="button"
                  onClick={() => onRemove(entry.id)}
                  aria-label={isAr ? `إزالة ${entry.title}` : `Remove ${entry.title}`}
                  className="absolute end-1 top-1/2 -translate-y-1/2 p-0.5 rounded text-[var(--text-muted)] hover:text-[var(--danger)]"
                >
                  <X className="w-3 h-3" strokeWidth={2.5} />
                </button>
              </div>
            ))}
          </div>

          <div className="flex items-center gap-2 shrink-0">
            <button
              type="button"
              onClick={onClear}
              className="btn-ghost !h-9"
            >
              {isAr ? 'مسح الكل' : 'Clear all'}
            </button>
            <button
              type="button"
              onClick={onOpen}
              disabled={entries.length < 2}
              className="btn btn-primary btn-sm !h-9"
              title={
                entries.length < 2
                  ? isAr
                    ? 'اختر جهازين على الأقل'
                    : 'Select at least two laptops'
                  : undefined
              }
            >
              <Scale className="w-3.5 h-3.5" strokeWidth={2} />
              <span>
                {isAr ? `قارن الآن (${entries.length})` : `Compare now (${entries.length})`}
              </span>
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
