import React, { useEffect, useState } from 'react'
import {
  Filter,
  ChevronLeft,
  ChevronRight,
  ChevronDown,
  ChevronUp,
  Eye,
  Search,
  X,
  RotateCcw,
  SlidersHorizontal,
} from 'lucide-react'
import type { CatalogListItem, CatalogListResponse, MetricFilterKey } from '../types/api'
import { fetchCatalog } from '../services/api'
import {
  EMPTY_METRIC_FILTERS,
  METRIC_FILTER_DEFS,
  toMetricQuery,
} from '../config/metricFilters'
import { MetricSlider } from './MetricSlider'

interface CatalogBrowserProps {
  lang: 'ar' | 'en'
  onSelectLaptop?: (item: CatalogListItem) => void
}

const BRANDS = ['All', 'Lenovo', 'ASUS', 'HP', 'Dell', 'Apple', 'Acer', 'MSI', 'Gigabyte']


export const CatalogBrowser: React.FC<CatalogBrowserProps> = ({ lang, onSelectLaptop }) => {
  const isAr = lang === 'ar'
  const [data, setData] = useState<CatalogListResponse | null>(null)
  const [loading, setLoading] = useState(false)
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
      .catch((err) => console.error(err))
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
    <div className="space-y-6">
      {/* 1. Universal Search Bar & Fast Filters */}
      <div className="bg-slate-900 border border-slate-800 rounded-3xl p-5 sm:p-6 shadow-xl space-y-4">
        {/* Search Input Box */}
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
              className="w-full px-4 py-3 pl-11 pr-10 bg-slate-950/80 border border-slate-700/80 rounded-2xl text-sm text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-all shadow-inner"
            />
            <Search className="w-4 h-4 text-indigo-400 absolute left-4 top-1/2 -translate-y-1/2 pointer-events-none" />
            {searchTerm && (
              <button
                type="button"
                onClick={() => setSearchTerm('')}
                className="absolute right-3 top-1/2 -translate-y-1/2 p-1 text-slate-400 hover:text-white rounded-lg hover:bg-slate-800 transition-colors"
              >
                <X className="w-4 h-4" />
              </button>
            )}
          </div>

          <div className="flex items-center justify-between sm:justify-end gap-3 shrink-0">
            {/* In-Stock Toggle */}
            <label className="flex items-center gap-2 cursor-pointer text-xs text-slate-300 bg-slate-800/60 px-3.5 py-3 rounded-2xl border border-slate-700/60 hover:bg-slate-800 transition-colors">
              <input
                type="checkbox"
                checked={inStockOnly}
                onChange={(e) => {
                  setInStockOnly(e.target.checked)
                  resetPagination()
                }}
                className="rounded bg-slate-900 border-slate-700 text-indigo-600 focus:ring-0 focus:ring-offset-0 cursor-pointer"
              />
              <span className="whitespace-nowrap">{isAr ? 'المتاح للشراء فقط' : 'In-Stock Only'}</span>
            </label>

            {/* Total Results Count */}
            <div className="text-xs text-slate-400 bg-slate-800/40 px-3.5 py-3 rounded-2xl border border-slate-800 whitespace-nowrap font-medium">
              <span>{isAr ? 'النتائج:' : 'Matches:'} </span>
              <strong className="text-white font-mono">{data?.total ?? 0}</strong>
            </div>
          </div>
        </div>

        {/* Brand Filter Pills */}
        <div className="flex flex-wrap items-center gap-2 pt-1 border-t border-slate-800/80">
          <span className="text-xs text-slate-400 font-semibold uppercase tracking-wider flex items-center gap-1.5 mr-2">
            <Filter className="w-3.5 h-3.5 text-indigo-400" />
            <span>{isAr ? 'الماركة:' : 'Brand:'}</span>
          </span>
          {BRANDS.map((b) => (
            <button
              key={b}
              type="button"
              onClick={() => {
                setBrand(b)
                resetPagination()
              }}
              className={`px-3 py-1.5 rounded-xl text-xs font-medium transition-all ${
                brand === b
                  ? 'bg-indigo-600 text-white shadow-md shadow-indigo-600/20'
                  : 'bg-slate-800/70 text-slate-400 hover:text-white hover:bg-slate-800'
              }`}
            >
              {b}
            </button>
          ))}
        </div>

        {/* Optional Real-World Experience & Performance Metric Drawer */}
        <div className="border-t border-slate-800/80 pt-3">
          <button
            type="button"
            onClick={() => setShowMetrics((prev) => !prev)}
            className="w-full flex items-center justify-between p-3 rounded-2xl bg-slate-950/60 hover:bg-slate-950/80 border border-slate-800 transition-colors text-left"
          >
            <div className="flex items-center gap-2">
              <SlidersHorizontal className="w-4 h-4 text-indigo-400" />
              <span className="text-xs font-bold text-white">
                {isAr
                  ? 'معايير التجربة الميدانية والأداء (اختياري)'
                  : 'Real-World Experience & Performance (Optional)'}
              </span>
              {activeMetricDefs.length > 0 && (
                <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-indigo-600 text-white font-mono">
                  {isAr
                    ? `${activeMetricDefs.length} فلاتر نشطة`
                    : `${activeMetricDefs.length} active`}
                </span>
              )}
            </div>
            <div className="flex items-center gap-1.5 text-xs text-indigo-400 font-semibold">
              <span>{showMetrics ? (isAr ? 'إخفاء' : 'Collapse') : isAr ? 'تخصيص' : 'Customize'}</span>
              {showMetrics ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
            </div>
          </button>

          {showMetrics && (
            <div className="mt-2.5 p-4 rounded-2xl bg-slate-950/80 border border-slate-800/80 space-y-4">
              <div className="flex items-center justify-between">
                <span className="text-[11px] text-slate-400">
                  {isAr
                    ? 'كل المعايير من 100 وتُطبق فقط عند اختيارها.'
                    : 'All scores are 0-100 and apply only when selected.'}
                </span>
                {activeMetricDefs.length > 0 && (
                  <button
                    type="button"
                    onClick={handleResetMetrics}
                    className="text-[11px] text-slate-400 hover:text-rose-400 transition-colors inline-flex items-center gap-1"
                  >
                    <RotateCcw className="w-3 h-3" />
                    <span>{isAr ? 'إعادة ضبط الكل' : 'Reset All Metrics'}</span>
                  </button>
                )}
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="space-y-3">
                  <div className="flex items-center gap-2">
                    <span className="w-1.5 h-4 rounded-full bg-emerald-400" />
                    <h4 className="text-[11px] font-bold uppercase tracking-wider text-emerald-300">
                      {isAr
                        ? 'تجربة الاستخدام الميدانية (Review Intelligence)'
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

                <div className="space-y-3">
                  <div className="flex items-center gap-2">
                    <span className="w-1.5 h-4 rounded-full bg-sky-400" />
                    <h4 className="text-[11px] font-bold uppercase tracking-wider text-sky-300">
                      {isAr
                        ? 'قوة العتاد والأداء (Hardware Benchmarks)'
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

      {/* 2. Grid of Laptops */}
      {loading ? (
        <div className="py-20 flex flex-col items-center justify-center gap-3">
          <div className="w-8 h-8 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin" />
          <p className="text-xs text-slate-400 font-medium">
            {isAr ? 'جاري البحث والتحميل...' : 'Searching and loading catalog...'}
          </p>
        </div>
      ) : data?.items && data.items.length > 0 ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {data.items.map((item) => {
            const hasValidPrice = item.min_price_egp && item.min_price_egp > 0

            return (
              <div
                key={item.id}
                onClick={() => onSelectLaptop && onSelectLaptop(item)}
                className="bg-slate-900 border border-slate-800 rounded-2xl p-4 shadow-lg hover:border-slate-700 transition-all flex flex-col justify-between group cursor-pointer"
              >
                <div className="space-y-3">
                  {/* Clean white retail thumbnail container */}
                  <div className="bg-white rounded-xl p-3 flex items-center justify-center h-44 border border-slate-700/40 relative overflow-hidden shadow-inner group-hover:shadow-indigo-500/10 transition-all">
                    <img
                      src={item.thumbnail_url}
                      alt={item.title}
                      className="w-full h-full max-h-36 object-contain group-hover:scale-105 transition-transform duration-300"
                      onError={(e) => {
                        ;(e.target as HTMLElement).style.display = 'none'
                      }}
                    />
                  </div>
                  <div>
                    <span className="text-[10px] font-bold text-indigo-400 uppercase tracking-wider">
                      {item.brand}
                    </span>
                    <h4 className="font-bold text-xs text-white line-clamp-2 leading-tight group-hover:text-indigo-300 transition-colors">
                      {item.title}
                    </h4>
                  </div>

                  <div className="text-[11px] text-slate-400 space-y-0.5">
                    <div className="line-clamp-1">CPU: {item.cpu_model}</div>
                    <div className="line-clamp-1">GPU: {item.gpu_model}</div>
                    <div>
                      RAM: {item.ram_capacity_gb}GB • SSD: {item.storage_capacity_gb}GB
                    </div>
                  </div>

                  {activeMetricDefs.length > 0 && (
                    <div className="flex flex-wrap gap-1">
                      {activeMetricDefs.map((def) => {
                        const score = item.metric_scores?.[def.scoreKey]
                        if (score == null) return null
                        return (
                          <span
                            key={def.key}
                            className="text-[10px] px-1.5 py-0.5 rounded-md bg-emerald-500/10 text-emerald-300 border border-emerald-500/30 font-mono"
                          >
                            🟢 {Math.round(score)}/100 {isAr ? def.labelAr : def.labelEn}
                          </span>
                        )
                      })}
                    </div>
                  )}
                </div>

                <div className="pt-3 border-t border-slate-800/80 mt-3 flex items-baseline justify-between">
                  <div>
                    <span className="text-[10px] text-slate-400 block">
                      {isAr ? 'يبدأ من:' : 'From:'}
                    </span>
                    {hasValidPrice ? (
                      <span className="font-extrabold text-sm text-white font-mono">
                        {item.min_price_egp.toLocaleString()} EGP
                      </span>
                    ) : (
                      <span className="text-amber-400 font-semibold text-xs">
                        {isAr ? 'السعر عند الطلب' : 'Price on request'}
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-1.5">
                    <span className="text-[10px] px-2 py-0.5 rounded bg-slate-800 text-slate-300 border border-slate-700 font-mono">
                      {item.cheapest_store}
                    </span>
                    <span className="p-1 rounded bg-slate-800 text-slate-400 group-hover:text-white transition-colors">
                      <Eye className="w-3 h-3" />
                    </span>
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      ) : (
        /* Empty State */
        <div className="py-16 px-4 text-center bg-slate-900/60 border border-slate-800 rounded-3xl space-y-4">
          <div className="w-12 h-12 rounded-2xl bg-slate-800/80 text-slate-400 flex items-center justify-center mx-auto border border-slate-700">
            <Search className="w-6 h-6" />
          </div>
          <div className="space-y-1">
            <h3 className="font-bold text-white text-base">
              {isAr ? 'لم نعثر على لابتوبات مطابقة لبحثك' : 'No matching laptops found'}
            </h3>
            <p className="text-xs text-slate-400 max-w-md mx-auto">
              {isAr
                ? 'جرب البحث بكلمات أبسط، أو إزالة بعض الفلاتر، أو كتابة اسم الموديل الأساسي مثل LOQ أو TUF أو Pavilion.'
                : 'Try searching with broader keywords, clearing active filters, or typing the core model name like LOQ, TUF, or Pavilion.'}
            </p>
          </div>
          <button
            type="button"
            onClick={handleClearSearch}
            className="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-semibold border border-slate-700 transition-colors inline-flex items-center gap-2"
          >
            <RotateCcw className="w-3.5 h-3.5" />
            <span>{isAr ? 'إعادة ضبط البحث والفلاتر' : 'Reset Search & Filters'}</span>
          </button>
        </div>
      )}

      {/* 3. Cursor (Keyset) Pagination Controls */}
      {(data?.page_info?.has_previous_page || data?.page_info?.has_next_page) && (
        <div className="flex items-center justify-center gap-3 pt-4">
          <button
            type="button"
            onClick={handlePreviousPage}
            disabled={!data?.page_info?.has_previous_page}
            aria-label={isAr ? 'الصفحة السابقة' : 'Previous page'}
            className="p-2 rounded-xl bg-slate-800 text-slate-300 disabled:opacity-40 hover:bg-slate-700 transition-colors"
          >
            <ChevronLeft className="w-4 h-4" />
          </button>
          <span className="text-xs text-slate-400 font-mono">
            {isAr ? 'عرض' : 'Showing'} {data?.items.length ?? 0} / {data?.total ?? 0}
          </span>
          <button
            type="button"
            onClick={handleNextPage}
            disabled={!data?.page_info?.has_next_page}
            aria-label={isAr ? 'الصفحة التالية' : 'Next page'}
            className="p-2 rounded-xl bg-slate-800 text-slate-300 disabled:opacity-40 hover:bg-slate-700 transition-colors"
          >
            <ChevronRight className="w-4 h-4" />
          </button>
        </div>
      )}
    </div>
  )
}
