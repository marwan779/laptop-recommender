import React, { useEffect, useState } from 'react'
import {
  Filter,
  ChevronLeft,
  ChevronRight,
  ChevronDown,
  ChevronUp,
  Search,
  X,
  RotateCcw,
  SlidersHorizontal,
  Check,
  Scale,
} from 'lucide-react'
import type { CatalogListItem, CatalogListResponse, MetricFilterKey } from '../types/api'
import type { CompareEntry } from '../types/compare'
import { fetchCatalog } from '../services/api'
import {
  EMPTY_METRIC_FILTERS,
  METRIC_FILTER_DEFS,
  toMetricQuery,
} from '../config/metricFilters'
import { MetricSlider } from './MetricSlider'
import { WishlistButton } from './WishlistButton'
import { formatCardTitle } from '../utils/laptopSummary'
import { getAvailabilityState, isValidDisplayPrice } from '../utils/availability'

interface CatalogBrowserProps {
  lang: 'ar' | 'en'
  onSelectLaptop?: (item: CatalogListItem) => void
  compareIds?: string[]
  compareDisabled?: boolean
  onToggleCompare?: (entry: CompareEntry) => void
}

const BRANDS = ['All', 'Lenovo', 'ASUS', 'HP', 'Dell', 'Apple', 'Acer', 'MSI', 'Gigabyte']


export const CatalogBrowser: React.FC<CatalogBrowserProps> = ({
  lang,
  onSelectLaptop,
  compareIds = [],
  compareDisabled = false,
  onToggleCompare,
}) => {
  const isAr = lang === 'ar'
  const [data, setData] = useState<CatalogListResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [brand, setBrand] = useState('All')
  const [searchTerm, setSearchTerm] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const [inStockOnly, setInStockOnly] = useState(true)
  const [currentCursor, setCurrentCursor] = useState<string | null>(null)
  const [direction, setDirection] = useState<'next' | 'prev'>('next')
  const [showMetrics, setShowMetrics] = useState(false)
  const [metricFilters, setMetricFilters] =
    useState<Record<MetricFilterKey, number | null>>(EMPTY_METRIC_FILTERS)
  const [debouncedMetricFilters, setDebouncedMetricFilters] =
    useState<Record<MetricFilterKey, number | null>>(EMPTY_METRIC_FILTERS)
  const limit = 12

  const activeMetricDefs = METRIC_FILTER_DEFS.filter(
    (def) => metricFilters[def.key] != null
  )

  const resetPagination = () => {
    setCurrentCursor(null)
    setDirection('next')
  }

  const handleMetricChange = (key: MetricFilterKey, value: number | null) => {
    setMetricFilters((prev) => ({ ...prev, [key]: value }))
    resetPagination()
  }

  const handleResetMetrics = () => {
    setMetricFilters(EMPTY_METRIC_FILTERS)
    setDebouncedMetricFilters(EMPTY_METRIC_FILTERS)
    resetPagination()
  }

  // Debounce search input by 300ms
  useEffect(() => {
    const handler = setTimeout(() => {
      setDebouncedSearch(searchTerm.trim())
      resetPagination()
    }, 300)
    return () => clearTimeout(handler)
  }, [searchTerm])

  // Debounce slider drags by 250ms to avoid firing an API call per pixel.
  useEffect(() => {
    const handler = setTimeout(() => {
      setDebouncedMetricFilters(metricFilters)
    }, 250)
    return () => clearTimeout(handler)
  }, [metricFilters])

  const loadLaptops = () => {
    setLoading(true)
    setError(null)
    const metricQuery = toMetricQuery(debouncedMetricFilters)

    fetchCatalog({
      search: debouncedSearch || undefined,
      brand: brand === 'All' ? undefined : brand,
      in_stock_only: inStockOnly,
      cursor: currentCursor ?? undefined,
      direction,
      limit,
      ...metricQuery,
    })
      .then((res) => setData(res))
      .catch((err) => {
        console.error(err)
        setError(err instanceof Error ? err.message : 'Failed to load catalog')
      })
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    loadLaptops()
  }, [brand, debouncedSearch, inStockOnly, currentCursor, direction, debouncedMetricFilters])

  const handleClearSearch = () => {
    setSearchTerm('')
    setDebouncedSearch('')
    setBrand('All')
    setMetricFilters(EMPTY_METRIC_FILTERS)
    setDebouncedMetricFilters(EMPTY_METRIC_FILTERS)
    resetPagination()
  }

  const handlePreviousPage = () => {
    const startCursor = data?.page_info?.start_cursor
    if (!startCursor) return
    setCurrentCursor(startCursor)
    setDirection('prev')
  }

  const handleNextPage = () => {
    const endCursor = data?.page_info?.end_cursor
    if (!endCursor) return
    setCurrentCursor(endCursor)
    setDirection('next')
  }

  return (
    <div className="space-y-5">
      {/* 1. Search & filters panel */}
      <div className="panel space-y-4">
        {/* Search input */}
        <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3">
          <div className="relative flex-1">
            <input
              type="text"
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              placeholder={
                isAr
                  ? 'ابحث بالموديل، الاسم، كود MPN، كارت الشاشة أو المعالج (مثال: LOQ 15, RTX 4060, FX607)...'
                  : 'Search by model, title, MPN, SKU, GPU, or CPU (e.g. LOQ 15, RTX 4060, FX607)...'
              }
              aria-label={isAr ? 'بحث في الكتالوج' : 'Search catalog'}
              className="field field-with-icon pe-10"
            />
            <Search className="w-4 h-4 field-icon" strokeWidth={1.8} />
            {searchTerm && (
              <button
                type="button"
                onClick={() => setSearchTerm('')}
                aria-label={isAr ? 'مسح البحث' : 'Clear search'}
                className="absolute end-3 top-1/2 -translate-y-1/2 p-1 rounded text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors"
              >
                <X className="w-4 h-4" strokeWidth={2} />
              </button>
            )}
          </div>

          <div className="flex items-center justify-between sm:justify-end gap-2.5 shrink-0">
            <label className="flex items-center gap-2 cursor-pointer text-[12.5px] text-[var(--text-secondary)] bg-[var(--bg-input)] px-3.5 h-11 rounded-[10px] border border-[var(--border-subtle)] hover:border-[var(--border-strong)] transition-colors">
              <input
                type="checkbox"
                checked={inStockOnly}
                onChange={(e) => {
                  setInStockOnly(e.target.checked)
                  resetPagination()
                }}
                className="checkbox"
              />
              <span className="whitespace-nowrap">
                {isAr ? 'المتاح للشراء فقط' : 'In-Stock Only'}
              </span>
            </label>

            <div className="text-[12.5px] text-[var(--text-muted)] bg-[var(--bg-input)] px-3.5 h-11 rounded-[10px] border border-[var(--border-subtle)] flex items-center gap-1.5 whitespace-nowrap">
              <span>{isAr ? 'النتائج:' : 'Matches:'}</span>
              <strong className="text-[var(--text-primary)] font-mono num">
                {data?.total ?? 0}
              </strong>
            </div>
          </div>
        </div>

        {/* Brand pills */}
        <div className="flex flex-wrap items-center gap-2 pt-3 border-t border-[var(--border-subtle)]">
          <span className="micro flex items-center gap-1.5 me-1">
            <Filter className="w-3.5 h-3.5 text-[var(--cyan)]" strokeWidth={1.8} />
            <span>{isAr ? 'الماركة' : 'Brand'}</span>
          </span>
          {BRANDS.map((b) => (
            <button
              key={b}
              type="button"
              aria-pressed={brand === b}
              onClick={() => {
                setBrand(b)
                resetPagination()
              }}
              className={`brand-chip transition-colors ${
                brand === b
                  ? '!text-[var(--gold-bright)] !border-[rgba(233,185,73,0.45)] !bg-[var(--gold-dim)]'
                  : 'hover:!border-[var(--border-strong)] hover:!text-[var(--text-primary)]'
              }`}
            >
              {b === 'All' && isAr ? 'الكل' : b}
            </button>
          ))}
        </div>

        {/* Metric filters drawer */}
        <div className="pt-3 border-t border-[var(--border-subtle)]">
          <button
            type="button"
            onClick={() => setShowMetrics((prev) => !prev)}
            className="collapse-toggle"
            aria-expanded={showMetrics}
          >
            <span className="ct-left">
              <SlidersHorizontal className="w-3.5 h-3.5" strokeWidth={1.8} />
              <span>
                {isAr
                  ? 'معايير التجربة الميدانية والأداء (اختياري)'
                  : 'Real-World Experience & Performance (optional)'}
              </span>
              {activeMetricDefs.length > 0 && (
                <span className="count-chip">{activeMetricDefs.length}</span>
              )}
            </span>
            <span className="ct-state">
              <span>
                {showMetrics ? (isAr ? 'إخفاء' : 'Collapse') : isAr ? 'تخصيص' : 'Customize'}
              </span>
              {showMetrics ? (
                <ChevronUp className="w-3.5 h-3.5" />
              ) : (
                <ChevronDown className="w-3.5 h-3.5" />
              )}
            </span>
          </button>

          {showMetrics && (
            <div className="mt-4 space-y-4">
              <div className="flex items-center justify-between gap-3 flex-wrap">
                <span className="text-[12px] text-[var(--text-muted)]">
                  {isAr
                    ? 'كل المعايير من 100 وتُطبق فقط عند اختيارها.'
                    : 'All scores are 0–100 and apply only when selected.'}
                </span>
                {activeMetricDefs.length > 0 && (
                  <button
                    type="button"
                    onClick={handleResetMetrics}
                    className="btn-ghost inline-flex items-center gap-1 !h-auto !py-1"
                  >
                    <RotateCcw className="w-3 h-3" strokeWidth={1.8} />
                    <span>{isAr ? 'إعادة ضبط الكل' : 'Reset All Metrics'}</span>
                  </button>
                )}
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="space-y-2.5">
                  <div className="flex items-center gap-2">
                    <span className="w-1 h-3.5 rounded-full bg-[var(--cyan)]" />
                    <h4 className="micro !text-[var(--text-secondary)]">
                      {isAr
                        ? 'تجربة الاستخدام الميدانية'
                        : 'Real-World Usage (Review Intelligence)'}
                    </h4>
                  </div>
                  {METRIC_FILTER_DEFS.filter((def) => def.group === 'experience').map((def) => (
                    <MetricSlider
                      key={def.key}
                      def={def}
                      value={metricFilters[def.key]}
                      onChange={(val) => handleMetricChange(def.key, val)}
                      lang={lang}
                    />
                  ))}
                </div>

                <div className="space-y-2.5">
                  <div className="flex items-center gap-2">
                    <span className="w-1 h-3.5 rounded-full bg-[var(--cyan)]" />
                    <h4 className="micro !text-[var(--text-secondary)]">
                      {isAr
                        ? 'قوة العتاد والأداء'
                        : 'Hardware Power & Performance (Benchmarks)'}
                    </h4>
                  </div>
                  {METRIC_FILTER_DEFS.filter((def) => def.group === 'performance').map((def) => (
                    <MetricSlider
                      key={def.key}
                      def={def}
                      value={metricFilters[def.key]}
                      onChange={(val) => handleMetricChange(def.key, val)}
                      lang={lang}
                    />
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* 2. Grid of laptops */}
      {loading ? (
        <div className="py-20 flex flex-col items-center justify-center gap-3">
          <div className="spinner" />
          <p className="text-[12px] text-[var(--text-muted)]">
            {isAr ? 'جاري البحث والتحميل...' : 'Searching and loading catalog...'}
          </p>
        </div>
      ) : data?.items && data.items.length > 0 ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {data.items.map((item) => {
            const availability = getAvailabilityState(item.in_stock, item.min_price_egp)
            const isAvailable = availability === 'in_stock'
            const hasValidPrice = isValidDisplayPrice(item.min_price_egp)

            return (
              <div
                key={item.id}
                onClick={() => onSelectLaptop && onSelectLaptop(item)}
                className={`catalog-card ${!isAvailable ? 'opacity-85' : ''}`}
              >
                <div className="space-y-3 min-w-0">
                  <div className={`studio-well ${!isAvailable ? 'opacity-75' : ''}`}>
                    <img
                      src={item.thumbnail_url}
                      alt={item.title}
                      loading="lazy"
                      onError={(e) => {
                        ;(e.target as HTMLElement).style.display = 'none'
                      }}
                    />
                  </div>

                  <div className="space-y-1.5">
                    <div className="flex items-center justify-between gap-1.5 flex-wrap">
                      <span className="brand-chip !text-[12px] !py-0.5">{item.brand}</span>
                      {availability === 'out_of_stock' && (
                        <span className="inline-flex items-center rounded-md border border-[var(--danger)] bg-[var(--danger-dim)] px-2 py-0.5 text-[12px] font-semibold text-[var(--danger)]">
                          {isAr ? 'غير متوفر' : 'Out of stock'}
                        </span>
                      )}
                      {availability === 'coming_soon' && (
                        <span className="inline-flex items-center rounded-md border border-[var(--warning)] bg-[var(--warning-dim)] px-2 py-0.5 text-[12px] font-semibold text-[var(--warning)]">
                          {isAr ? 'قريباً' : 'Coming soon'}
                        </span>
                      )}
                    </div>
                    <h4 dir="auto" className="cc-title">
                      {formatCardTitle(item.brand, item.laptop_family, item.laptop_model) || item.title}
                    </h4>
                  </div>

                  <div className="flex flex-wrap gap-1.5">
                    {item.cpu_model && (
                      <span dir="ltr" className="catalog-spec-chip">{item.cpu_model}</span>
                    )}
                    {item.gpu_model && (
                      <span dir="ltr" className="catalog-spec-chip">{item.gpu_model}</span>
                    )}
                    {item.ram_capacity_gb > 0 && (
                      <span className="catalog-spec-chip tabular-nums">{item.ram_capacity_gb}GB RAM</span>
                    )}
                    {item.storage_capacity_gb > 0 && (
                      <span className="catalog-spec-chip tabular-nums">
                        {item.storage_capacity_gb >= 1024
                          ? `${item.storage_capacity_gb / 1024}TB`
                          : `${item.storage_capacity_gb}GB`}{' '}
                        SSD
                      </span>
                    )}
                    {item.display_size_inches > 0 && (
                      <span dir="ltr" className="catalog-spec-chip tabular-nums">
                        {item.display_size_inches}"
                      </span>
                    )}
                  </div>

                  {activeMetricDefs.length > 0 && (
                    <div className="flex flex-wrap gap-1">
                      {activeMetricDefs.map((def) => {
                        const score = item.metric_scores?.[def.scoreKey]
                        if (score == null) return null
                        return (
                          <span key={def.key} className="ai-chip !text-[10px] !py-0.5">
                            {Math.round(score)}/100 {isAr ? def.labelAr : def.labelEn}
                          </span>
                        )
                      })}
                    </div>
                  )}
                </div>

                <div className="cc-foot">
                  <div>
                    <span className="micro block">
                      {isAvailable ? (isAr ? 'يبدأ من' : 'From') : isAr ? 'الحالة' : 'Status'}
                    </span>
                    {isAvailable && hasValidPrice ? (
                      <span className="cc-price num">
                        {item.min_price_egp.toLocaleString('en-US')}{' '}
                        <span className="text-[12px] font-semibold text-[var(--text-muted)]">
                          {isAr ? 'ج.م' : 'EGP'}
                        </span>
                      </span>
                    ) : availability === 'coming_soon' ? (
                      <span className="text-[12.5px] font-semibold text-[var(--warning)]">
                        {isAr ? 'قريباً / السعر غير محدد' : 'Coming soon'}
                      </span>
                    ) : (
                      <span className="text-[12.5px] font-semibold text-[var(--danger)]">
                        {isAr ? 'غير متوفر حالياً' : 'Out of stock'}
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-1.5 shrink-0">
                    <span className="mpn-chip !text-[10px] !py-0.5">{item.cheapest_store}</span>
                    <span className="text-[var(--text-muted)]">
                      <ChevronRight className="w-3.5 h-3.5 rtl:rotate-180" strokeWidth={2} />
                    </span>
                  </div>
                </div>

                <div className="mt-2 flex items-center gap-2">
                  {onToggleCompare && (
                    <button
                      type="button"
                      onClick={(event) => {
                        event.stopPropagation()
                        onToggleCompare({
                          id: item.canonical_id,
                          title: `${item.brand} ${formatCardTitle(item.brand, item.laptop_family, item.laptop_model)}`,
                          brand: item.brand,
                          thumbnail_url: item.thumbnail_url,
                          price: item.min_price_egp,
                        })
                      }}
                      disabled={!compareIds.includes(item.canonical_id) && compareDisabled}
                      aria-pressed={compareIds.includes(item.canonical_id)}
                      className={`inline-flex flex-1 items-center justify-center gap-1.5 rounded-[8px] border px-3 py-2 text-[12px] font-medium transition-colors min-h-[38px] ${
                        compareIds.includes(item.canonical_id)
                          ? 'border-[var(--gold)] bg-[var(--gold-dim)] text-[var(--gold-bright)]'
                          : 'border-[var(--border-subtle)] text-[var(--text-secondary)] hover:border-[var(--border-strong)] hover:text-[var(--text-primary)]'
                      }`}
                    >
                      {compareIds.includes(item.canonical_id) ? (
                        <Check className="w-3.5 h-3.5" strokeWidth={2.5} />
                      ) : (
                        <Scale className="w-3.5 h-3.5" strokeWidth={2} />
                      )}
                      <span>{isAr ? 'قارن' : 'Compare'}</span>
                    </button>
                  )}

                  <WishlistButton
                    canonicalId={item.canonical_id}
                    titleSnapshot={formatCardTitle(item.brand, item.laptop_family, item.laptop_model)}
                    addedPriceEgp={item.min_price_egp}
                    thumbnailUrlSnapshot={item.thumbnail_url}
                    lang={lang}
                    compact
                  />
                </div>
              </div>
            )
          })}
        </div>
      ) : error ? (
        /* Error state */
        <div className="py-14 px-4 text-center panel space-y-3">
          <h3 className="text-[15px] font-semibold text-[var(--danger)]">
            {isAr ? 'تعذّر تحميل الكتالوج حالياً' : 'Could not load catalog right now'}
          </h3>
          <p className="text-[12.5px] text-[var(--text-muted)] max-w-md mx-auto">
            {isAr
              ? 'تأكد من تشغيل خدمة الكتالوج ثم أعد المحاولة.'
              : 'Please verify the catalog service is running and try again.'}
          </p>
          <button type="button" onClick={loadLaptops} className="btn btn-secondary">
            {isAr ? 'إعادة المحاولة' : 'Retry'}
          </button>
        </div>
      ) : (
        /* Empty state */
        <div className="py-16 px-4 text-center panel space-y-3">
          <div className="w-12 h-12 rounded-xl bg-[var(--bg-raised)] text-[var(--text-muted)] flex items-center justify-center mx-auto border border-[var(--border-subtle)]">
            <Search className="w-5 h-5" strokeWidth={1.8} />
          </div>
          <div className="space-y-1">
            <h3 className="text-[15px] font-semibold text-[var(--text-primary)]">
              {isAr ? 'لم نعثر على لابتوبات مطابقة لبحثك' : 'No matching laptops found'}
            </h3>
            <p className="text-[12.5px] text-[var(--text-muted)] max-w-md mx-auto leading-relaxed">
              {isAr
                ? 'جرب البحث بكلمات أبسط، أو إزالة بعض الفلاتر، أو كتابة اسم الموديل الأساسي مثل LOQ أو TUF أو Pavilion.'
                : 'Try searching with broader keywords, clearing active filters, or typing the core model name like LOQ, TUF, or Pavilion.'}
            </p>
          </div>
          <button
            type="button"
            onClick={handleClearSearch}
            className="btn btn-secondary btn-sm inline-flex"
          >
            <RotateCcw className="w-3.5 h-3.5" strokeWidth={1.8} />
            <span>{isAr ? 'إعادة ضبط البحث والفلاتر' : 'Reset Search & Filters'}</span>
          </button>
        </div>
      )}

      {/* 3. Cursor pagination */}
      {(data?.page_info?.has_previous_page || data?.page_info?.has_next_page) && (
        <div className="flex items-center justify-center gap-3 pt-2">
          <button
            type="button"
            onClick={handlePreviousPage}
            disabled={!data?.page_info?.has_previous_page}
            aria-label={isAr ? 'الصفحة السابقة' : 'Previous page'}
            className="btn btn-secondary btn-sm !px-2.5"
          >
            <ChevronLeft className="w-4 h-4" strokeWidth={2} />
          </button>
          <span className="text-[12px] text-[var(--text-muted)] font-mono num">
            {isAr ? 'عرض' : 'Showing'} {data?.items.length ?? 0} / {data?.total ?? 0}
          </span>
          <button
            type="button"
            onClick={handleNextPage}
            disabled={!data?.page_info?.has_next_page}
            aria-label={isAr ? 'الصفحة التالية' : 'Next page'}
            className="btn btn-secondary btn-sm !px-2.5"
          >
            <ChevronRight className="w-4 h-4" strokeWidth={2} />
          </button>
        </div>
      )}
    </div>
  )
}
