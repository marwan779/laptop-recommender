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
  const [offset, setOffset] = useState(0)
  const [showMetrics, setShowMetrics] = useState(false)
  const [metricFilters, setMetricFilters] =
    useState<Record<MetricFilterKey, number | null>>(EMPTY_METRIC_FILTERS)
  const limit = 12

  const activeMetricDefs = METRIC_FILTER_DEFS.filter(
    (def) => metricFilters[def.key] != null
  )

  const handleMetricChange = (key: MetricFilterKey, value: number | null) => {
    setMetricFilters((prev) => ({ ...prev, [key]: value }))
    setOffset(0)
  }

  const handleResetMetrics = () => {
    setMetricFilters(EMPTY_METRIC_FILTERS)
    setOffset(0)
  }

  // Debounce search input by 300ms
  useEffect(() => {
    const handler = setTimeout(() => {
      setDebouncedSearch(searchTerm.trim())
      setOffset(0)
    }, 300)
    return () => clearTimeout(handler)
  }, [searchTerm])

  const loadLaptops = () => {
    setLoading(true)
    const metricQuery = toMetricQuery(metricFilters)

    fetchCatalog({
      search: debouncedSearch || undefined,
      brand: brand === 'All' ? undefined : brand,
      in_stock_only: inStockOnly,
      offset,
      limit,
      ...metricQuery,
    })
      .then((res) => setData(res))
      .catch((err) => console.error(err))
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    loadLaptops()
  }, [brand, debouncedSearch, inStockOnly, offset, metricFilters])

  const totalPages = data ? Math.ceil(data.total / limit) : 0
  const currentPage = Math.floor(offset / limit) + 1

  const handleClearSearch = () => {
    setSearchTerm('')
    setDebouncedSearch('')
    setBrand('All')
    setMetricFilters(EMPTY_METRIC_FILTERS)
    setOffset(0)
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
                  ? 'Ø§Ø¨Ø­Ø« Ø¨Ø§Ù„Ù…ÙˆØ¯ÙŠÙ„ØŒ Ø§Ù„Ø§Ø³Ù…ØŒ ÙƒÙˆØ¯ MPNØŒ ÙƒØ§Ø±Øª Ø§Ù„Ø´Ø§Ø´Ø© Ø£Ùˆ Ø§Ù„Ù…Ø¹Ø§Ù„Ø¬ (Ù…Ø«Ø§Ù„: LOQ 15, RTX 4060, FX607)...'
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
                  setOffset(0)
                }}
                className="rounded bg-slate-900 border-slate-700 text-indigo-600 focus:ring-0 focus:ring-offset-0 cursor-pointer"
              />
              <span className="whitespace-nowrap">{isAr ? 'Ø§Ù„Ù…ØªØ§Ø­ Ù„Ù„Ø´Ø±Ø§Ø¡ ÙÙ‚Ø·' : 'In-Stock Only'}</span>
            </label>

            {/* Total Results Count */}
            <div className="text-xs text-slate-400 bg-slate-800/40 px-3.5 py-3 rounded-2xl border border-slate-800 whitespace-nowrap font-medium">
              <span>{isAr ? 'Ø§Ù„Ù†ØªØ§Ø¦Ø¬:' : 'Matches:'} </span>
              <strong className="text-white font-mono">{data?.total ?? 0}</strong>
            </div>
          </div>
        </div>

        {/* Brand Filter Pills */}
        <div className="flex flex-wrap items-center gap-2 pt-1 border-t border-slate-800/80">
          <span className="text-xs text-slate-400 font-semibold uppercase tracking-wider flex items-center gap-1.5 mr-2">
            <Filter className="w-3.5 h-3.5 text-indigo-400" />
            <span>{isAr ? 'Ø§Ù„Ù…Ø§Ø±ÙƒØ©:' : 'Brand:'}</span>
          </span>
          {BRANDS.map((b) => (
            <button
              key={b}
              type="button"
              onClick={() => {
                setBrand(b)
                setOffset(0)
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
                  ? 'Ù…Ø¹Ø§ÙŠÙŠØ± Ø§Ù„ØªØ¬Ø±Ø¨Ø© Ø§Ù„Ù…ÙŠØ¯Ø§Ù†ÙŠØ© ÙˆØ§Ù„Ø£Ø¯Ø§Ø¡ (Ø§Ø®ØªÙŠØ§Ø±ÙŠ)'
                  : 'Real-World Experience & Performance (Optional)'}
              </span>
              {activeMetricDefs.length > 0 && (
                <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-indigo-600 text-white font-mono">
                  {isAr
                    ? `${activeMetricDefs.length} ÙÙ„Ø§ØªØ± Ù†Ø´Ø·Ø©`
                    : `${activeMetricDefs.length} active`}
                </span>
              )}
            </div>
            <div className="flex items-center gap-1.5 text-xs text-indigo-400 font-semibold">
              <span>{showMetrics ? (isAr ? 'Ø¥Ø®ÙØ§Ø¡' : 'Collapse') : isAr ? 'ØªØ®ØµÙŠØµ' : 'Customize'}</span>
              {showMetrics ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
            </div>
          </button>

          {showMetrics && (
            <div className="mt-2.5 p-4 rounded-2xl bg-slate-950/80 border border-slate-800/80 space-y-4">
              <div className="flex items-center justify-between">
                <span className="text-[11px] text-slate-400">
                  {isAr
                    ? 'ÙƒÙ„ Ø§Ù„Ù…Ø¹Ø§ÙŠÙŠØ± Ù…Ù† 100 ÙˆØªÙØ·Ø¨Ù‚ ÙÙ‚Ø· Ø¹Ù†Ø¯ Ø§Ø®ØªÙŠØ§Ø±Ù‡Ø§.'
                    : 'All scores are 0-100 and apply only when selected.'}
                </span>
                {activeMetricDefs.length > 0 && (
                  <button
                    type="button"
                    onClick={handleResetMetrics}
                    className="text-[11px] text-slate-400 hover:text-rose-400 transition-colors inline-flex items-center gap-1"
                  >
                    <RotateCcw className="w-3 h-3" />
                    <span>{isAr ? 'Ø¥Ø¹Ø§Ø¯Ø© Ø¶Ø¨Ø· Ø§Ù„ÙƒÙ„' : 'Reset All Metrics'}</span>
                  </button>
                )}
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                {METRIC_FILTER_DEFS.map((def) => {
                  const current = metricFilters[def.key]
                  return (
                    <div key={def.key} className="space-y-1.5">
                      <label className="text-[11px] font-semibold text-slate-300 flex items-center gap-1">
                        <span>{isAr ? def.labelAr : def.labelEn}</span>
                        <span
                          className={`w-1.5 h-1.5 rounded-full ${
                            def.group === 'experience' ? 'bg-emerald-400' : 'bg-sky-400'
                          }`}
                        />
                      </label>
                      <div className="flex gap-1.5">
                        <button
                          type="button"
                          onClick={() => handleMetricChange(def.key, null)}
                          className={`flex-1 py-1.5 px-2 rounded-xl text-[11px] font-medium border transition-all ${
                            current == null
                              ? 'bg-indigo-600 text-white border-indigo-500 font-bold'
                              : 'bg-slate-900 border-slate-800 text-slate-400 hover:text-white'
                          }`}
                        >
                          {isAr ? 'Ø§Ù„ÙƒÙ„' : 'Any'}
                        </button>
                        {def.presets.map((preset) => (
                          <button
                            key={preset.value}
                            type="button"
                            onClick={() => handleMetricChange(def.key, preset.value)}
                            className={`flex-1 py-1.5 px-2 rounded-xl text-[11px] font-medium border transition-all ${
                              current === preset.value
                                ? 'bg-indigo-600 text-white border-indigo-500 font-bold'
                                : 'bg-slate-900 border-slate-800 text-slate-400 hover:text-white'
                            }`}
                          >
                            {isAr ? preset.labelAr : preset.labelEn}
                          </button>
                        ))}
                      </div>
                    </div>
                  )
                })}
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
            {isAr ? 'Ø¬Ø§Ø±ÙŠ Ø§Ù„Ø¨Ø­Ø« ÙˆØ§Ù„ØªØ­Ù…ÙŠÙ„...' : 'Searching and loading catalog...'}
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
                      RAM: {item.ram_capacity_gb}GB â€¢ SSD: {item.storage_capacity_gb}GB
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
                            ðŸŸ¢ {Math.round(score)}/100 {isAr ? def.labelAr : def.labelEn}
                          </span>
                        )
                      })}
                    </div>
                  )}
                </div>

                <div className="pt-3 border-t border-slate-800/80 mt-3 flex items-baseline justify-between">
                  <div>
                    <span className="text-[10px] text-slate-400 block">
                      {isAr ? 'ÙŠØ¨Ø¯Ø£ Ù…Ù†:' : 'From:'}
                    </span>
                    {hasValidPrice ? (
                      <span className="font-extrabold text-sm text-white font-mono">
                        {item.min_price_egp.toLocaleString()} EGP
                      </span>
                    ) : (
                      <span className="text-amber-400 font-semibold text-xs">
                        {isAr ? 'Ø§Ù„Ø³Ø¹Ø± Ø¹Ù†Ø¯ Ø§Ù„Ø·Ù„Ø¨' : 'Price on request'}
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
              {isAr ? 'Ù„Ù… Ù†Ø¹Ø«Ø± Ø¹Ù„Ù‰ Ù„Ø§Ø¨ØªÙˆØ¨Ø§Øª Ù…Ø·Ø§Ø¨Ù‚Ø© Ù„Ø¨Ø­Ø«Ùƒ' : 'No matching laptops found'}
            </h3>
            <p className="text-xs text-slate-400 max-w-md mx-auto">
              {isAr
                ? 'Ø¬Ø±Ø¨ Ø§Ù„Ø¨Ø­Ø« Ø¨ÙƒÙ„Ù…Ø§Øª Ø£Ø¨Ø³Ø·ØŒ Ø£Ùˆ Ø¥Ø²Ø§Ù„Ø© Ø¨Ø¹Ø¶ Ø§Ù„ÙÙ„Ø§ØªØ±ØŒ Ø£Ùˆ ÙƒØªØ§Ø¨Ø© Ø§Ø³Ù… Ø§Ù„Ù…ÙˆØ¯ÙŠÙ„ Ø§Ù„Ø£Ø³Ø§Ø³ÙŠ Ù…Ø«Ù„ LOQ Ø£Ùˆ TUF Ø£Ùˆ Pavilion.'
                : 'Try searching with broader keywords, clearing active filters, or typing the core model name like LOQ, TUF, or Pavilion.'}
            </p>
          </div>
          <button
            type="button"
            onClick={handleClearSearch}
            className="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-semibold border border-slate-700 transition-colors inline-flex items-center gap-2"
          >
            <RotateCcw className="w-3.5 h-3.5" />
            <span>{isAr ? 'Ø¥Ø¹Ø§Ø¯Ø© Ø¶Ø¨Ø· Ø§Ù„Ø¨Ø­Ø« ÙˆØ§Ù„ÙÙ„Ø§ØªØ±' : 'Reset Search & Filters'}</span>
          </button>
        </div>
      )}

      {/* 3. Pagination Controls */}
      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-3 pt-4">
          <button
            onClick={() => setOffset(Math.max(0, offset - limit))}
            disabled={offset === 0}
            className="p-2 rounded-xl bg-slate-800 text-slate-300 disabled:opacity-40 hover:bg-slate-700 transition-colors"
          >
            <ChevronLeft className="w-4 h-4" />
          </button>
          <span className="text-xs text-slate-400 font-mono">
            {currentPage} / {totalPages}
          </span>
          <button
            onClick={() => setOffset(offset + limit)}
            disabled={currentPage >= totalPages}
            className="p-2 rounded-xl bg-slate-800 text-slate-300 disabled:opacity-40 hover:bg-slate-700 transition-colors"
          >
            <ChevronRight className="w-4 h-4" />
          </button>
        </div>
      )}
    </div>
  )
}
