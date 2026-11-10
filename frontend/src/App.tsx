import { useState, useEffect } from 'react'
import { Navbar } from './components/Navbar'
import { BudgetPersonaBar } from './components/BudgetPersonaBar'
import { StatusBanner } from './components/StatusBanner'
import { LaptopCard } from './components/LaptopCard'
import { LaptopDetailModal } from './components/LaptopDetailModal'
import { CatalogBrowser } from './components/CatalogBrowser'
import type {
  PersonaType,
  RankedLaptop,
  CatalogListItem,
  MetricFilterKey,
  RecommendationResponse,
} from './types/api'
import { EMPTY_METRIC_FILTERS, toMetricQuery } from './config/metricFilters'
import { fetchRecommendations } from './services/api'
import { Sparkles, AlertCircle } from 'lucide-react'

export function App() {
  const [lang, setLang] = useState<'ar' | 'en'>('ar')
  const [tab, setTab] = useState<'recommend' | 'catalog'>('recommend')
  const [budget, setBudget] = useState<number>(45000)
  const [selectedPersonas, setSelectedPersonas] = useState<PersonaType[]>(['balanced'])
  const [promptText, setPromptText] = useState<string>('')
  const [minRam, setMinRam] = useState<number | null>(null)
  const [minStorage, setMinStorage] = useState<number | null>(null)
  const [requireDgpu, setRequireDgpu] = useState<boolean | null>(null)
  const [selectedBrands, setSelectedBrands] = useState<string[]>([])
  const [metricFilters, setMetricFilters] =
    useState<Record<MetricFilterKey, number | null>>(EMPTY_METRIC_FILTERS)
  const [topK, setTopK] = useState<number>(8)
  const [loading, setLoading] = useState<boolean>(false)
  const [error, setError] = useState<string | null>(null)
  const [recommendations, setRecommendations] = useState<RecommendationResponse | null>(null)
  const [selectedLaptop, setSelectedLaptop] = useState<RankedLaptop | CatalogListItem | null>(null)

  const isAr = lang === 'ar'

  const handleTogglePersona = (p: PersonaType) => {
    if (selectedPersonas.includes(p)) {
      if (selectedPersonas.length > 1) {
        setSelectedPersonas(selectedPersonas.filter((item) => item !== p))
      }
    } else {
      setSelectedPersonas([...selectedPersonas, p])
    }
  }

  const handleToggleBrand = (brand: string) => {
    setSelectedBrands((prev) =>
      prev.includes(brand) ? prev.filter((b) => b !== brand) : [...prev, brand]
    )
  }

  const handleMetricChange = (key: MetricFilterKey, value: number | null) => {
    setMetricFilters((prev) => ({ ...prev, [key]: value }))
  }

  const handleResetAdvancedFilters = () => {
    setMinRam(null)
    setMinStorage(null)
    setRequireDgpu(null)
    setSelectedBrands([])
    setMetricFilters(EMPTY_METRIC_FILTERS)
    setTopK(8)
  }

  const handleGetRecommendations = async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await fetchRecommendations({
        budget_egp: budget,
        persona: selectedPersonas[0],
        personas: selectedPersonas,
        user_text_prompt: promptText.trim() ? promptText.trim() : undefined,
        min_ram_gb: minRam !== null ? minRam : undefined,
        min_storage_gb: minStorage !== null ? minStorage : undefined,
        require_dgpu: requireDgpu !== null ? requireDgpu : undefined,
        brand_filter: selectedBrands.length > 0 ? selectedBrands : undefined,
        top_k: topK,
        ...toMetricQuery(metricFilters),
      })
      setRecommendations(data)
    } catch (err: any) {
      console.error(err)
      setError(err?.message || 'Failed to connect to recommendation service')
    } finally {
      setLoading(false)
    }
  }

  // Load initial recommendation on first render and whenever personas change
  useEffect(() => {
    handleGetRecommendations()
  }, [selectedPersonas])

  return (
    <div
      dir={isAr ? 'rtl' : 'ltr'}
      className="min-h-screen bg-slate-950 text-slate-100 flex flex-col font-sans"
    >
      {/* 1. Top Navigation Bar */}
      <Navbar
        currentTab={tab}
        onTabChange={setTab}
        lang={lang}
        onToggleLang={() => setLang(lang === 'ar' ? 'en' : 'ar')}
      />

      {/* 2. Main Body Content */}
      <main className="flex-1 max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 w-full space-y-8">
        {tab === 'recommend' ? (
          <>
            {/* Budget & Persona Selector */}
            <BudgetPersonaBar
              budget={budget}
              onBudgetChange={setBudget}
              selectedPersonas={selectedPersonas}
              onTogglePersona={handleTogglePersona}
              promptText={promptText}
              onPromptChange={setPromptText}
              minRam={minRam}
              onMinRamChange={setMinRam}
              minStorage={minStorage}
              onMinStorageChange={setMinStorage}
              requireDgpu={requireDgpu}
              onRequireDgpuChange={setRequireDgpu}
              selectedBrands={selectedBrands}
              onToggleBrand={handleToggleBrand}
              metricFilters={metricFilters}
              onMetricChange={handleMetricChange}
              topK={topK}
              onTopKChange={setTopK}
              onResetAdvancedFilters={handleResetAdvancedFilters}
              onSubmit={handleGetRecommendations}
              isLoading={loading}
              lang={lang}
            />

            {/* Error Message if API fails */}
            {error && (
              <div className="bg-rose-950/40 border border-rose-500/40 rounded-2xl p-4 flex items-center gap-3 text-rose-300 text-xs">
                <AlertCircle className="w-5 h-5 text-rose-400 shrink-0" />
                <span>{error}</span>
              </div>
            )}

            {/* Status & Results Section */}
            {recommendations && (
              <div className="space-y-6">
                {/* Status Notice Banner */}
                <StatusBanner response={recommendations} lang={lang} />

                {/* Section Title */}
                <div className="flex items-center justify-between">
                  <h3 className="font-extrabold text-lg text-white flex items-center gap-2">
                    <Sparkles className="w-4 h-4 text-indigo-400" />
                    <span>
                      {isAr
                        ? `أفضل ترشيحات لابتوب تناسبك (${recommendations.results.length} خيارات)`
                        : `Top Recommended Laptops (${recommendations.results.length} matches)`}
                    </span>
                  </h3>
                  <span className="text-xs text-slate-400 font-mono">
                    {isAr ? 'مرتبة بواسطة Vector TOPSIS' : 'Ranked via Vector TOPSIS'}
                  </span>
                </div>

                {/* Laptop Cards List */}
                <div className="grid grid-cols-1 gap-6">
                  {recommendations.results.map((laptop) => (
                    <LaptopCard
                      key={laptop.canonical_id}
                      laptop={laptop}
                      lang={lang}
                      onSelect={(lap) => setSelectedLaptop(lap)}
                    />
                  ))}
                </div>
              </div>
            )}
          </>
        ) : (
          /* Catalog Browser Tab */
          <CatalogBrowser
            lang={lang}
            onSelectLaptop={(lap) => setSelectedLaptop(lap)}
          />
        )}
      </main>

      {/* 3. Full Specifications Modal */}
      <LaptopDetailModal
        laptop={selectedLaptop}
        onClose={() => setSelectedLaptop(null)}
        lang={lang}
      />

      {/* 4. Footer */}
      <footer className="border-t border-slate-900 bg-slate-950/80 py-6 text-center text-xs text-slate-400">
        <div className="max-w-7xl mx-auto px-4 flex flex-col sm:flex-row items-center justify-between gap-3">
          <div>
            {isAr
              ? 'مرشح اللابتوبات الذكي • أسعار ومواصفات حية من المتاجر المصرية'
              : 'Smart Laptop Recommender • Live Retailer Scrapes & Vector Intelligence'}
          </div>
          <div className="font-mono text-slate-400 text-[11px]">
            Powered by FastAPI • ChromaDB • Vector TOPSIS
          </div>
        </div>
      </footer>
    </div>
  )
}

export default App
