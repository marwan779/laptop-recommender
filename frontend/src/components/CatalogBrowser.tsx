import React, { useEffect, useState } from 'react'
import { Filter, ChevronLeft, ChevronRight, Eye, Search, X, RotateCcw } from 'lucide-react'
import type { CatalogListItem, CatalogListResponse } from '../types/api'
import { fetchCatalog } from '../services/api'

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
  const limit = 12

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
    fetchCatalog({
      search: debouncedSearch || undefined,
      brand: brand === 'All' ? undefined : brand,
      in_stock_only: inStockOnly,
      offset,
      limit,
    })
      .then((res) => setData(res))
      .catch((err) => console.error(err))
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    loadLaptops()
  }, [brand, debouncedSearch, inStockOnly, offset])

  const totalPages = data ? Math.ceil(data.total / limit) : 0
  const currentPage = Math.floor(offset / limit) + 1

  const handleClearSearch = () => {
    setSearchTerm('')
    setDebouncedSearch('')
    setBrand('All')
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
                  setOffset(0)
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
