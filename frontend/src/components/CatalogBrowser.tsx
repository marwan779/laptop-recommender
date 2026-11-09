import React, { useEffect, useState } from 'react'
import { Filter, ChevronLeft, ChevronRight } from 'lucide-react'
import type { CatalogListResponse } from '../types/api'
import { fetchCatalog } from '../services/api'

interface CatalogBrowserProps {
  lang: 'ar' | 'en'
}

const BRANDS = ['All', 'Lenovo', 'ASUS', 'HP', 'Dell', 'Apple', 'Acer', 'MSI']

export const CatalogBrowser: React.FC<CatalogBrowserProps> = ({ lang }) => {
  const isAr = lang === 'ar'
  const [data, setData] = useState<CatalogListResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [brand, setBrand] = useState('All')
  const [minPrice] = useState<number | undefined>()
  const [maxPrice] = useState<number | undefined>()
  const [offset, setOffset] = useState(0)
  const limit = 12

  const loadLaptops = () => {
    setLoading(true)
    fetchCatalog({
      brand: brand === 'All' ? undefined : brand,
      min_price: minPrice,
      max_price: maxPrice,
      in_stock_only: true,
      offset,
      limit,
    })
      .then((res) => setData(res))
      .catch((err) => console.error(err))
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    loadLaptops()
  }, [brand, offset])

  const totalPages = data ? Math.ceil(data.total / limit) : 0
  const currentPage = Math.floor(offset / limit) + 1

  return (
    <div className="space-y-6">
      {/* Filters Bar */}
      <div className="bg-slate-900 border border-slate-800 rounded-3xl p-5 shadow-xl flex flex-wrap items-center justify-between gap-4">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs text-slate-400 font-semibold uppercase tracking-wider flex items-center gap-1.5 mr-2">
            <Filter className="w-3.5 h-3.5 text-indigo-400" />
            <span>{isAr ? 'الماركة:' : 'Brand:'}</span>
          </span>
          {BRANDS.map((b) => (
            <button
              key={b}
              onClick={() => {
                setBrand(b)
                setOffset(0)
              }}
              className={`px-3 py-1.5 rounded-xl text-xs font-medium transition-all ${
                brand === b
                  ? 'bg-indigo-600 text-white shadow-md shadow-indigo-600/20'
                  : 'bg-slate-800 text-slate-400 hover:text-white hover:bg-slate-700'
              }`}
            >
              {b}
            </button>
          ))}
        </div>

        <div className="text-xs text-slate-400">
          {isAr ? 'إجمالي الأجهزة المتاحة:' : 'Total Active Laptops:'}{' '}
          <span className="font-bold text-white font-mono">{data?.total || 0}</span>
        </div>
      </div>

      {/* Grid of Laptops */}
      {loading ? (
        <div className="py-20 flex flex-col items-center justify-center gap-3">
          <div className="w-8 h-8 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin" />
          <p className="text-xs text-slate-400 font-medium">
            {isAr ? 'جاري تحميل اللابتوبات...' : 'Loading catalog...'}
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {data?.items.map((item) => (
            <div
              key={item.id}
              className="bg-slate-900 border border-slate-800 rounded-2xl p-4 shadow-lg hover:border-slate-700 transition-all flex flex-col justify-between group"
            >
              <div className="space-y-3">
                <div className="bg-slate-950/60 rounded-xl p-3 border border-slate-800 flex items-center justify-center aspect-video">
                  <img
                    src={item.thumbnail_url}
                    alt={item.title}
                    className="max-h-28 object-contain group-hover:scale-105 transition-transform"
                    onError={(e) => {
                      ;(e.target as HTMLElement).style.display = 'none'
                    }}
                  />
                </div>
                <div>
                  <span className="text-[10px] font-bold text-indigo-400 uppercase tracking-wider">
                    {item.brand}
                  </span>
                  <h4 className="font-bold text-xs text-white line-clamp-2 leading-tight">
                    {item.title}
                  </h4>
                </div>

                <div className="text-[11px] text-slate-400 space-y-0.5">
                  <div>CPU: {item.cpu_model}</div>
                  <div>GPU: {item.gpu_model}</div>
                  <div>RAM: {item.ram_capacity_gb}GB • SSD: {item.storage_capacity_gb}GB</div>
                </div>
              </div>

              <div className="pt-3 border-t border-slate-800/80 mt-3 flex items-baseline justify-between">
                <div>
                  <span className="text-[10px] text-slate-400 block">
                    {isAr ? 'يبدأ من:' : 'From:'}
                  </span>
                  <span className="font-extrabold text-sm text-white font-mono">
                    {item.min_price_egp.toLocaleString()} EGP
                  </span>
                </div>
                <span className="text-[10px] px-2 py-0.5 rounded bg-slate-800 text-slate-300 border border-slate-700 font-mono">
                  {item.cheapest_store}
                </span>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Pagination Controls */}
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
