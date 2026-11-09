import React, { useEffect, useState } from 'react'
import {
  X,
  Cpu,
  Monitor,
  HardDrive,
  MemoryStick,
  BatteryCharging,
  ExternalLink,
  Store,
} from 'lucide-react'
import type { FullLaptopDetailResponse, RankedLaptop } from '../types/api'
import { fetchLaptopDetail } from '../services/api'

interface LaptopDetailModalProps {
  laptop: RankedLaptop | null
  onClose: () => void
  lang: 'ar' | 'en'
}

export const LaptopDetailModal: React.FC<LaptopDetailModalProps> = ({
  laptop,
  onClose,
  lang,
}) => {
  const isAr = lang === 'ar'
  const [detail, setDetail] = useState<FullLaptopDetailResponse | null>(null)
  const [, setLoading] = useState(false)

  useEffect(() => {
    if (!laptop) return
    setLoading(true)
    fetchLaptopDetail(laptop.canonical_id)
      .then((data) => setDetail(data))
      .catch((err) => console.error('Error fetching detail:', err))
      .finally(() => setLoading(false))
  }, [laptop])

  if (!laptop) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6 bg-slate-950/80 backdrop-blur-md overflow-y-auto">
      <div className="bg-slate-900 border border-slate-800 rounded-3xl max-w-3xl w-full max-h-[90vh] flex flex-col shadow-2xl relative overflow-hidden my-auto animate-in fade-in duration-200">
        {/* Header */}
        <div className="p-6 border-b border-slate-800 flex items-start justify-between gap-4 sticky top-0 bg-slate-900/90 backdrop-blur-md z-10">
          <div>
            <span className="text-xs font-bold text-indigo-400 uppercase tracking-wider">
              {laptop.brand} • {laptop.laptop_family}
            </span>
            <h2 className="text-lg font-bold text-white line-clamp-1">
              {laptop.title}
            </h2>
          </div>
          <button
            onClick={onClose}
            className="p-2 rounded-xl bg-slate-800 text-slate-400 hover:text-white hover:bg-slate-700 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Scrollable Content */}
        <div className="p-6 space-y-6 overflow-y-auto">
          {/* Main Top Grid */}
          <div className="grid grid-cols-1 sm:grid-cols-12 gap-6">
            <div className="sm:col-span-5 bg-slate-950/60 rounded-2xl p-4 border border-slate-800 flex items-center justify-center aspect-video sm:aspect-square">
              <img
                src={laptop.thumbnail_url}
                alt={laptop.title}
                className="max-h-48 object-contain"
              />
            </div>
            <div className="sm:col-span-7 space-y-4">
              <div>
                <span className="text-xs text-slate-400 block">
                  {isAr ? 'أقل سعر مسجل في مصر:' : 'Cheapest Store Offer:'}
                </span>
                <div className="flex items-baseline gap-2">
                  <span className="text-2xl font-extrabold text-white font-mono">
                    {laptop.effective_price_egp.toLocaleString()}
                  </span>
                  <span className="text-sm font-semibold text-slate-400">
                    {isAr ? 'ج.م' : 'EGP'}
                  </span>
                  <span className="text-xs text-emerald-400">
                    (@ {laptop.cheapest_store})
                  </span>
                </div>
              </div>

              {/* Store Offers Table */}
              <div className="space-y-2">
                <span className="text-xs font-semibold text-slate-400 flex items-center gap-1.5">
                  <Store className="w-3.5 h-3.5 text-indigo-400" />
                  <span>{isAr ? 'عروض المتاجر المتاحة:' : 'Retailer Price Comparison:'}</span>
                </span>
                <div className="space-y-1.5">
                  {(laptop.offers || []).map((off, idx) => (
                    <div
                      key={idx}
                      className="flex items-center justify-between p-2.5 rounded-xl bg-slate-950/40 border border-slate-800 text-xs"
                    >
                      <div className="flex items-center gap-2">
                        <span className="font-semibold text-white">
                          {off.store_name}
                        </span>
                        {off.is_cheapest && (
                          <span className="px-1.5 py-0.5 rounded text-[10px] bg-emerald-500/20 text-emerald-400 font-semibold border border-emerald-500/30">
                            {isAr ? 'الأرخص' : 'Best Price'}
                          </span>
                        )}
                      </div>
                      <div className="flex items-center gap-3">
                        <span className="font-mono text-slate-200 font-bold">
                          {off.price_egp.toLocaleString()} EGP
                        </span>
                        <a
                          href={off.product_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-indigo-400 hover:text-indigo-300 transition-colors"
                        >
                          <ExternalLink className="w-3.5 h-3.5" />
                        </a>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>

          {/* Detailed Hardware Specs Grid */}
          <div className="space-y-3">
            <h3 className="text-sm font-bold text-white flex items-center gap-2">
              <Cpu className="w-4 h-4 text-indigo-400" />
              <span>{isAr ? 'المواصفات التقنية الدقيقة' : 'Hardware Specifications'}</span>
            </h3>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
              {/* CPU */}
              <div className="p-3.5 rounded-2xl bg-slate-950/50 border border-slate-800 space-y-1">
                <div className="text-slate-400 flex items-center gap-1.5 font-semibold">
                  <Cpu className="w-3.5 h-3.5 text-indigo-400" />
                  <span>{isAr ? 'المعالج (CPU)' : 'Processor (CPU)'}</span>
                </div>
                <div className="text-white font-medium">
                  {detail?.cpu.full_name || laptop.title.split(' ')[2] || 'Processor'}
                </div>
                <div className="text-slate-400 text-[11px]">
                  {detail?.cpu.cores} Cores • {detail?.cpu.threads} Threads • {detail?.cpu.clock_boost_ghz} GHz Boost
                </div>
              </div>

              {/* GPU */}
              <div className="p-3.5 rounded-2xl bg-slate-950/50 border border-slate-800 space-y-1">
                <div className="text-slate-400 flex items-center gap-1.5 font-semibold">
                  <Monitor className="w-3.5 h-3.5 text-indigo-400" />
                  <span>{isAr ? 'كارت الشاشة (GPU)' : 'Graphics (GPU)'}</span>
                </div>
                <div className="text-white font-medium">
                  {detail?.gpu.model || 'Integrated / Dedicated'}
                </div>
                <div className="text-slate-400 text-[11px]">
                  {detail?.gpu.vram_gb ? `${detail.gpu.vram_gb}GB VRAM` : 'Shared'} • {detail?.gpu.tdp_w ? `${detail.gpu.tdp_w}W TGP` : 'Standard'}
                </div>
              </div>

              {/* Memory */}
              <div className="p-3.5 rounded-2xl bg-slate-950/50 border border-slate-800 space-y-1">
                <div className="text-slate-400 flex items-center gap-1.5 font-semibold">
                  <MemoryStick className="w-3.5 h-3.5 text-indigo-400" />
                  <span>{isAr ? 'الذاكرة العشوائية (RAM)' : 'Memory (RAM)'}</span>
                </div>
                <div className="text-white font-medium">
                  {detail?.memory.capacity_gb || 16}GB {detail?.memory.memory_type || 'DDR5'}
                </div>
                <div className="text-slate-400 text-[11px]">
                  {detail?.memory.slot_count ? `${detail.memory.slot_count}x SO-DIMM Slots` : 'Dual Channel'}
                </div>
              </div>

              {/* Storage */}
              <div className="p-3.5 rounded-2xl bg-slate-950/50 border border-slate-800 space-y-1">
                <div className="text-slate-400 flex items-center gap-1.5 font-semibold">
                  <HardDrive className="w-3.5 h-3.5 text-indigo-400" />
                  <span>{isAr ? 'وحدة التخزين (SSD)' : 'Storage (SSD)'}</span>
                </div>
                <div className="text-white font-medium">
                  {detail?.storage.capacity_gb || 512}GB {detail?.storage.storage_type || 'NVMe SSD'}
                </div>
                <div className="text-slate-400 text-[11px]">
                  {detail?.storage.slot_count ? `${detail.storage.slot_count}x M.2 Slots available` : 'Fast PCIe Gen 4'}
                </div>
              </div>

              {/* Display */}
              <div className="p-3.5 rounded-2xl bg-slate-950/50 border border-slate-800 space-y-1">
                <div className="text-slate-400 flex items-center gap-1.5 font-semibold">
                  <Monitor className="w-3.5 h-3.5 text-indigo-400" />
                  <span>{isAr ? 'الشاشة' : 'Display'}</span>
                </div>
                <div className="text-white font-medium">
                  {detail?.display.size_inches}" {detail?.display.resolution} ({detail?.display.panel_type || 'IPS'})
                </div>
                <div className="text-slate-400 text-[11px]">
                  {detail?.display.refresh_rate_hz || 60}Hz • {detail?.display.touchscreen ? 'Touchscreen' : 'Non-touch'}
                </div>
              </div>

              {/* Battery & Weight */}
              <div className="p-3.5 rounded-2xl bg-slate-950/50 border border-slate-800 space-y-1">
                <div className="text-slate-400 flex items-center gap-1.5 font-semibold">
                  <BatteryCharging className="w-3.5 h-3.5 text-indigo-400" />
                  <span>{isAr ? 'البطارية والوزن' : 'Battery & Portability'}</span>
                </div>
                <div className="text-white font-medium">
                  {detail?.power_battery.battery_capacity_wh || 60}Wh Battery
                </div>
                <div className="text-slate-400 text-[11px]">
                  {detail?.physical.weight_kg ? `${detail.physical.weight_kg} kg` : 'Portable'} • {detail?.power_battery.usb_c_pd_charging ? 'USB-C Charging' : 'Standard Barrel'}
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="p-4 border-t border-slate-800 bg-slate-900 flex justify-end">
          <a
            href={laptop.cheapest_offer_url}
            target="_blank"
            rel="noopener noreferrer"
            className="px-6 py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white font-semibold text-xs shadow-lg shadow-indigo-600/20 transition-all flex items-center gap-2"
          >
            <span>{isAr ? 'عرض في أرخص متجر' : 'Go to Lowest Store'}</span>
            <ExternalLink className="w-3.5 h-3.5" />
          </a>
        </div>
      </div>
    </div>
  )
}
