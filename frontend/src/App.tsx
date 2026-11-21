import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Navbar } from './components/Navbar'
import { BudgetPersonaBar } from './components/BudgetPersonaBar'
import { StatusBanner } from './components/StatusBanner'
import { LaptopCard } from './components/LaptopCard'
import { LaptopDetailModal } from './components/LaptopDetailModal'
import { CatalogBrowser } from './components/CatalogBrowser'
import { CompareBar } from './components/CompareBar'
import { CompareModal } from './components/CompareModal'
import type {
  PersonaType,
  RankedLaptop,
  CatalogListItem,
  MetricFilterKey,
  RecommendationResponse,
  RecommendationRequest,
} from './types/api'
import type { CompareEntry } from './types/compare'
import { EMPTY_METRIC_FILTERS, toMetricQuery } from './config/metricFilters'
import { PERSONA_LABELS, resolvePersonaKey } from './config/personas'
import { fetchRecommendations } from './services/api'
import { getSortComparator, formatCardTitle, type SortOption } from './utils/laptopSummary'
import { AlertCircle, ChevronDown, Pencil, ShieldCheck } from 'lucide-react'

const SORT_OPTIONS: Array<{ key: SortOption; ar: string; en: string }> = [
  { key: 'best', ar: 'الأنسب لك', en: 'Best for you' },
  { key: 'cheapest', ar: 'الأقل سعراً', en: 'Cheapest' },
  { key: 'battery', ar: 'أطول بطارية', en: 'Best battery' },
  { key: 'thermals', ar: 'أفضل تبريد', en: 'Best cooling' },
  { key: 'display', ar: 'أفضل شاشة', en: 'Best display' },
]

const list = (value: string | null): string[] =>
  value ? value.split(',').map((item) => item.trim()).filter(Boolean) : []

const numberOrNull = (value: string | null): number | null => {
  if (value == null || value.trim() === '') return null
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

export function App() {
  const [lang, setLang] = useState<'ar' | 'en'>(() =>
    document.documentElement.getAttribute('lang') === 'en' ? 'en' : 'ar',
  )
  const [theme, setTheme] = useState<'light' | 'dark'>(() =>
    document.documentElement.getAttribute('data-theme') === 'dark' ? 'dark' : 'light',
  )
  const [tab, setTab] = useState<'recommend' | 'catalog'>('recommend')
  const [budget, setBudget] = useState<number>(45000)
  const [selectedPersona, setSelectedPersona] = useState<PersonaType>('balanced')
  const [promptText, setPromptText] = useState<string>('')
  const [minRam, setMinRam] = useState<number | null>(null)
  const [minStorage, setMinStorage] = useState<number | null>(null)
  const [requireDgpu, setRequireDgpu] = useState<boolean | null>(null)
  const [selectedBrands, setSelectedBrands] = useState<string[]>([])
  const [metricFilters, setMetricFilters] =
    useState<Record<MetricFilterKey, number | null>>(EMPTY_METRIC_FILTERS)
  const [topK, setTopK] = useState<number>(8)
  const [sortKey, setSortKey] = useState<SortOption>('best')

  const [loading, setLoading] = useState<boolean>(false)
  const [error, setError] = useState<string | null>(null)
  const [recommendations, setRecommendations] = useState<RecommendationResponse | null>(null)
  const [finderOpen, setFinderOpen] = useState<boolean>(false)

  const [selectedLaptop, setSelectedLaptop] = useState<RankedLaptop | CatalogListItem | null>(null)
  const [compareEntries, setCompareEntries] = useState<CompareEntry[]>([])
  const [compareOpen, setCompareOpen] = useState<boolean>(false)
  const [compareNotice, setCompareNotice] = useState<string | null>(null)

  const hydratedRef = useRef(false)
  const didInitRef = useRef(false)
  const isAr = lang === 'ar'

  // ── Theme / language document sync ─────────────────────────────────
  useEffect(() => {
    document.documentElement.setAttribute('lang', lang)
    document.documentElement.setAttribute('dir', lang === 'ar' ? 'rtl' : 'ltr')
    document.title =
      lang === 'ar'
        ? 'دليل اللابتوب — مقارنة الأسعار والمراجعات في مصر'
        : 'Laptop Guide EG — Live Prices & Real Reviews'
    localStorage.setItem('lang', lang)
  }, [lang])

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
    localStorage.setItem('theme', theme)
  }, [theme])

  const handleSelectPersona = (persona: PersonaType) => {
    setSelectedPersona(persona)
  }

  const handleToggleBrand = (brand: string) => {
    setSelectedBrands((prev) =>
      prev.includes(brand) ? prev.filter((b) => b !== brand) : [...prev, brand],
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

  const activeFilterCount = useMemo(() => {
    const metrics = Object.values(metricFilters).filter((value) => value != null).length
    return (
      metrics +
      (minRam != null ? 1 : 0) +
      (minStorage != null ? 1 : 0) +
      (requireDgpu != null ? 1 : 0) +
      selectedBrands.length
    )
  }, [metricFilters, minRam, minStorage, requireDgpu, selectedBrands])

  const buildRequest = useCallback(
    (overrides: Partial<RecommendationRequest> = {}): RecommendationRequest => ({
      budget_egp: budget,
      persona: selectedPersona,
      user_text_prompt: promptText.trim() ? promptText.trim() : undefined,
      min_ram_gb: minRam ?? undefined,
      min_storage_gb: minStorage ?? undefined,
      require_dgpu: requireDgpu ?? undefined,
      brand_filter: selectedBrands.length > 0 ? selectedBrands : undefined,
      top_k: topK,
      ...toMetricQuery(metricFilters),
      ...overrides,
    }),
    [
      budget,
      selectedPersona,
      promptText,
      minRam,
      minStorage,
      requireDgpu,
      selectedBrands,
      topK,
      metricFilters,
    ],
  )

  const runRecommendations = useCallback(
    async (overrides: Partial<RecommendationRequest> = {}) => {
      setLoading(true)
      setError(null)
      try {
        const data = await fetchRecommendations(buildRequest(overrides))
        setRecommendations(data)
        setFinderOpen(false)
      } catch (err: unknown) {
        setError(err instanceof Error ? err.message : 'Failed to connect to the recommendation service')
      } finally {
        setLoading(false)
      }
    },
    [buildRequest],
  )

  // ── URL sync ───────────────────────────────────────────────────────
  const writeUrl = useCallback(
    (updates: Record<string, string | null> = {}) => {
      const params = new URLSearchParams(window.location.search)
      const setOrDelete = (key: string, value: string | null) => {
        if (value == null || value === '') params.delete(key)
        else params.set(key, value)
      }

      setOrDelete('tab', tab === 'recommend' ? null : tab)
      setOrDelete('lang', lang === 'ar' ? null : lang)
      setOrDelete('budget', String(budget))
      setOrDelete('persona', selectedPersona)
      setOrDelete('personas', null)
      setOrDelete('q', promptText.trim() || null)
      setOrDelete('ram', minRam != null ? String(minRam) : null)
      setOrDelete('ssd', minStorage != null ? String(minStorage) : null)
      setOrDelete('dgpu', requireDgpu != null ? String(requireDgpu) : null)
      setOrDelete('brands', selectedBrands.length ? selectedBrands.join(',') : null)
      setOrDelete('sort', sortKey === 'best' ? null : sortKey)
      setOrDelete('laptop', selectedLaptop?.canonical_id ?? null)
      setOrDelete('compare', compareOpen ? '1' : null)

      for (const [key, value] of Object.entries(updates)) setOrDelete(key, value)

      const search = params.toString()
      window.history.replaceState({}, '', `${window.location.pathname}${search ? `?${search}` : ''}`)
    },
    [
      tab,
      lang,
      budget,
      selectedPersona,
      promptText,
      minRam,
      minStorage,
      requireDgpu,
      selectedBrands,
      sortKey,
      selectedLaptop,
      compareOpen,
    ],
  )

  useEffect(() => {
    if (!hydratedRef.current) return
    writeUrl()
  }, [writeUrl])

  // Initial hydration from a shared URL (?budget=...&personas=...&laptop=...)
  useEffect(() => {
    if (didInitRef.current) return
    didInitRef.current = true
    const params = new URLSearchParams(window.location.search)
    const urlTab = params.get('tab')
    if (urlTab === 'catalog') setTab('catalog')

    const urlBudget = numberOrNull(params.get('budget'))
    const rawPersona = params.get('persona') || list(params.get('personas'))[0] || null
    const urlPersona = rawPersona ? resolvePersonaKey(rawPersona) : null
    const urlPrompt = params.get('q') || ''
    const urlRam = numberOrNull(params.get('ram'))
    const urlSsd = numberOrNull(params.get('ssd'))
    const dgpuRaw = params.get('dgpu')
    const urlDgpu = dgpuRaw === 'true' ? true : dgpuRaw === 'false' ? false : null
    const urlBrands = list(params.get('brands'))
    const urlSort = params.get('sort') as SortOption | null
    const urlLaptop = params.get('laptop')

    if (urlBudget != null) setBudget(urlBudget)
    if (urlPersona != null) setSelectedPersona(urlPersona)
    if (urlPrompt) setPromptText(urlPrompt)
    if (urlRam != null) setMinRam(urlRam)
    if (urlSsd != null) setMinStorage(urlSsd)
    if (urlDgpu != null) setRequireDgpu(urlDgpu)
    if (urlBrands.length) setSelectedBrands(urlBrands)
    if (urlSort && SORT_OPTIONS.some((option) => option.key === urlSort)) setSortKey(urlSort)

    if (urlLaptop) {
      setSelectedLaptop({
        id: urlLaptop,
        canonical_id: urlLaptop,
        brand: '',
        laptop_model: '',
        title: urlLaptop,
        thumbnail_url: '',
        min_price_egp: 0,
        cheapest_store: '',
        in_stock: true,
        stores_count: 0,
        ram_capacity_gb: 0,
        storage_capacity_gb: 0,
        gpu_model: '',
        cpu_model: '',
        display_size_inches: 0,
        community_nlp_score: 0,
        value_score: 0,
        has_reviews: false,
        reviews_evidence_count: 0,
        pros_ar: [],
        pros_en: [],
        cons_ar: [],
        cons_en: [],
      })
    }

    const shouldAutoRun = params.has('budget') || params.has('persona') || params.has('personas')
    if (shouldAutoRun) {
      const overrides: Partial<RecommendationRequest> = {
        ...(urlBudget != null ? { budget_egp: urlBudget } : {}),
        ...(urlPersona != null ? { persona: urlPersona } : {}),
        ...(urlPrompt ? { user_text_prompt: urlPrompt } : {}),
        ...(urlRam != null ? { min_ram_gb: urlRam } : {}),
        ...(urlSsd != null ? { min_storage_gb: urlSsd } : {}),
        ...(urlDgpu != null ? { require_dgpu: urlDgpu } : {}),
        ...(urlBrands.length ? { brand_filter: urlBrands } : {}),
      }
      void runRecommendations(overrides)
    }

    hydratedRef.current = true
    // Run once on mount; URL is the source of truth only for the first paint.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Browser back: close modals when the URL no longer contains them.
  useEffect(() => {
    const onPopState = () => {
      const params = new URLSearchParams(window.location.search)
      if (!params.get('laptop')) setSelectedLaptop(null)
      if (!params.get('compare')) setCompareOpen(false)
      const urlLang = params.get('lang')
      if (urlLang === 'ar' || urlLang === 'en') setLang(urlLang)
      const urlTab = params.get('tab')
      if (urlTab === 'catalog') setTab('catalog')
      else if (urlTab === 'recommend' || (!urlTab && params.has('budget'))) setTab('recommend')
    }
    window.addEventListener('popstate', onPopState)
    return () => window.removeEventListener('popstate', onPopState)
  }, [])

  const openLaptop = (laptop: RankedLaptop | CatalogListItem) => {
    setSelectedLaptop(laptop)
    const params = new URLSearchParams(window.location.search)
    params.set('laptop', laptop.canonical_id)
    window.history.pushState({ laptop: laptop.canonical_id }, '', `?${params.toString()}`)
  }

  const closeLaptop = () => {
    setSelectedLaptop(null)
    const params = new URLSearchParams(window.location.search)
    params.delete('laptop')
    window.history.replaceState({}, '', `${window.location.pathname}${params.toString() ? `?${params}` : ''}`)
  }

  const openCompare = () => {
    if (compareEntries.length < 2) return
    setCompareOpen(true)
    const params = new URLSearchParams(window.location.search)
    params.set('compare', '1')
    window.history.pushState({ compare: '1' }, '', `?${params.toString()}`)
  }

  const closeCompare = () => {
    setCompareOpen(false)
    const params = new URLSearchParams(window.location.search)
    params.delete('compare')
    window.history.replaceState({}, '', `${window.location.pathname}${params.toString() ? `?${params}` : ''}`)
  }

  const toggleCompare = (entry: CompareEntry) => {
    setCompareNotice(null)
    setCompareEntries((prev) => {
      if (prev.some((item) => item.id === entry.id)) {
        return prev.filter((item) => item.id !== entry.id)
      }
      if (prev.length >= 3) {
        setCompareNotice(
          isAr ? 'الحد الأقصى 3 أجهزة — شيل جهاز الأول عشان تقدر تضيف.' : 'Compare up to 3 laptops — remove one first.',
        )
        return prev
      }
      return [...prev, entry]
    })
  }

  const compareIds = compareEntries.map((entry) => entry.id)
  const sortedResults = useMemo(() => {
    if (!recommendations) return []
    return [...recommendations.results].sort(getSortComparator(sortKey))
  }, [recommendations, sortKey])

  const personaSummary = isAr ? PERSONA_LABELS[selectedPersona].ar : PERSONA_LABELS[selectedPersona].en

  const stageOne = recommendations === null

  return (
    <div className="min-h-screen flex flex-col">
      <Navbar
        currentTab={tab}
        onTabChange={setTab}
        lang={lang}
        onToggleLang={() => setLang(lang === 'ar' ? 'en' : 'ar')}
        theme={theme}
        onToggleTheme={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
      />

      <main className={`page-wrap flex-1 w-full space-y-5 ${compareEntries.length > 0 ? 'pb-24' : ''}`}>
        {tab === 'recommend' ? (
          <>
            {error && (
              <div className="flex items-start gap-3 rounded-[10px] border border-[var(--danger)] bg-[var(--danger-dim)] px-4 py-3 text-[13px] text-[var(--danger)]">
                <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
                <span>{error}</span>
              </div>
            )}

            {stageOne && !loading && (
              <div className="max-w-3xl mx-auto w-full space-y-5">
                <div className="text-center space-y-2 pt-2">
                  <span className="inline-flex items-center gap-1.5 rounded-full border border-[var(--border-subtle)] bg-[var(--bg-raised)] px-3 py-1 text-[11px] font-semibold text-[var(--text-secondary)]">
                    <ShieldCheck className="w-3.5 h-3.5 text-[var(--success)]" strokeWidth={1.8} />
                    {isAr ? 'مستقل · بدون عمولات' : 'Independent · commission-free'}
                  </span>
                  <h1 className="font-display text-[24px] sm:text-[30px] font-bold text-[var(--text-primary)] leading-tight">
                    {isAr ? 'اختار اللابتوب الصح لأول مرة' : 'Choose the right laptop, first time'}
                  </h1>
                  <p className="text-[13px] sm:text-[14px] text-[var(--text-secondary)] max-w-xl mx-auto leading-[1.7]">
                    {isAr
                      ? 'قارن أسعار المتاجر الحقيقية في مصر، وشوف عيوب كل جهاز من مراجعات أصحابه — قبل ما تدفع.'
                      : 'Compare real Egyptian store prices and see each laptop’s real-world flaws from owner reviews before you pay.'}
                  </p>
                </div>

                <BudgetPersonaBar
                  budget={budget}
                  onBudgetChange={setBudget}
                  selectedPersona={selectedPersona}
                  onSelectPersona={handleSelectPersona}
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
                  onSubmit={() => void runRecommendations()}
                  isLoading={loading}
                  lang={lang}
                />

                <p className="text-center text-[12px] text-[var(--text-muted)]">
                  {isAr ? 'مش عارف تبدأ منين؟' : 'Not sure where to start?'}{' '}
                  <button
                    type="button"
                    onClick={() => setTab('catalog')}
                    className="text-[var(--gold)] underline underline-offset-2 hover:text-[var(--gold-bright)]"
                  >
                    {isAr ? 'تصفح كل اللابتوبات' : 'Browse all laptops'}
                  </button>
                </p>
              </div>
            )}

            {stageOne && loading && (
              <div className="max-w-3xl mx-auto w-full py-16 flex flex-col items-center gap-3">
                <div className="spinner" />
                <p className="text-[13px] text-[var(--text-muted)]">
                  {isAr ? 'بندور على أنسب الاختيارات...' : 'Finding your best matches...'}
                </p>
              </div>
            )}

            {recommendations && (
              <div className="space-y-5">
                {/* Compact search summary bar */}
                <div className="rounded-[12px] border border-[var(--border-subtle)] bg-[var(--bg-surface)] shadow-[var(--shadow-1)] px-4 py-3">
                  <div className="flex items-center justify-between gap-3 flex-wrap">
                    <div className="flex items-center gap-2 flex-wrap min-w-0 text-[12.5px]">
                      <span className="font-display font-semibold tabular-nums text-[var(--text-primary)]">
                        {budget.toLocaleString('en-US')} {isAr ? 'ج.م' : 'EGP'}
                      </span>
                      <span className="text-[var(--text-muted)]">·</span>
                      <span dir="auto" className="text-[var(--text-secondary)] truncate max-w-[200px]">
                        {personaSummary}
                      </span>
                      {activeFilterCount > 0 && (
                        <>
                          <span className="text-[var(--text-muted)]">·</span>
                          <span className="text-[var(--text-muted)]">
                            {isAr ? `${activeFilterCount} فلتر` : `${activeFilterCount} filters`}
                          </span>
                        </>
                      )}
                    </div>

                    <button
                      type="button"
                      onClick={() => setFinderOpen(!finderOpen)}
                      className="btn btn-secondary btn-sm !h-9 shrink-0"
                      aria-expanded={finderOpen}
                    >
                      <Pencil className="w-3.5 h-3.5" strokeWidth={1.8} />
                      <span>{isAr ? 'تعديل البحث' : 'Edit search'}</span>
                      <ChevronDown
                        className={`w-3.5 h-3.5 transition-transform ${finderOpen ? 'rotate-180' : ''}`}
                        strokeWidth={2}
                      />
                    </button>
                  </div>
                </div>

                {finderOpen && (
                  <div className="rounded-[14px] border border-[var(--border-strong)] bg-[var(--bg-surface)] p-3 sm:p-4 shadow-[var(--shadow-1)]">
                    <BudgetPersonaBar
                      budget={budget}
                      onBudgetChange={setBudget}
                      selectedPersona={selectedPersona}
                      onSelectPersona={handleSelectPersona}
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
                      onSubmit={() => void runRecommendations()}
                      isLoading={loading}
                      lang={lang}
                      mode="edit"
                      onCancel={() => setFinderOpen(false)}
                    />
                  </div>
                )}

                <StatusBanner response={recommendations} lang={lang} />

                {/* Sort strip */}
                <div className="-mx-4 px-4 sm:mx-0 sm:px-0 overflow-x-auto">
                  <div className="flex items-center gap-2 min-w-max pb-1">
                    {SORT_OPTIONS.map((option) => (
                      <button
                        key={option.key}
                        type="button"
                        aria-pressed={sortKey === option.key}
                        onClick={() => setSortKey(option.key)}
                        className={`rounded-full border px-3.5 py-2 text-[12px] whitespace-nowrap transition-colors min-h-[38px] ${
                          sortKey === option.key
                            ? 'border-[var(--gold)] bg-[var(--gold-dim)] text-[var(--gold-bright)] font-semibold'
                            : 'border-[var(--border-subtle)] bg-[var(--bg-surface)] text-[var(--text-secondary)] hover:border-[var(--border-strong)] hover:text-[var(--text-primary)]'
                        }`}
                      >
                        {isAr ? option.ar : option.en}
                      </button>
                    ))}
                  </div>
                </div>

                <div className="section-head">
                  <span className="no">{isAr ? 'النتائج' : 'RESULTS'}</span>
                  <h2>
                    {isAr
                      ? `أفضل ${sortedResults.length} اختيارات لميزانيتك`
                      : `Top ${sortedResults.length} matches for your budget`}
                  </h2>
                </div>

                <div className="grid grid-cols-1 gap-5">
                  {sortedResults.map((laptop) => (
                    <LaptopCard
                      key={laptop.canonical_id}
                      laptop={laptop}
                      lang={lang}
                      onSelect={openLaptop}
                      isCompared={compareIds.includes(laptop.canonical_id)}
                      compareDisabled={compareEntries.length >= 3}
                      onToggleCompare={(lap) =>
                        toggleCompare({
                          id: lap.canonical_id,
                          title: `${lap.brand} ${formatCardTitle(lap.brand, lap.laptop_family, lap.laptop_model)}`,
                          brand: lap.brand,
                          thumbnail_url: lap.thumbnail_url,
                          price: lap.effective_price_egp,
                        })
                      }
                    />
                  ))}
                </div>

                <div className="text-center pt-1">
                  <button
                    type="button"
                    onClick={() => {
                      setRecommendations(null)
                      setFinderOpen(false)
                      setError(null)
                    }}
                    className="btn-ghost"
                  >
                    {isAr ? 'ابدأ بحث جديد' : 'Start a new search'}
                  </button>
                </div>
              </div>
            )}

            {compareNotice && (
              <div className="fixed bottom-24 inset-x-0 z-40 px-4 pointer-events-none">
                <p className="mx-auto max-w-md rounded-[10px] border border-[var(--warning)] bg-[var(--warning-dim)] px-3.5 py-2.5 text-center text-[12px] text-[var(--warning)] shadow-[var(--shadow-1)]">
                  {compareNotice}
                </p>
              </div>
            )}
          </>
        ) : (
          <CatalogBrowser
            lang={lang}
            onSelectLaptop={openLaptop}
            compareIds={compareIds}
            compareDisabled={compareEntries.length >= 3}
            onToggleCompare={toggleCompare}
          />
        )}
      </main>

      <LaptopDetailModal laptop={selectedLaptop} onClose={closeLaptop} lang={lang} />

      <CompareBar
        entries={compareEntries}
        lang={lang}
        onRemove={(id) => {
          const next = compareEntries.filter((entry) => entry.id !== id)
          setCompareEntries(next)
          if (next.length < 2) closeCompare()
        }}
        onClear={() => {
          setCompareEntries([])
          closeCompare()
        }}
        onOpen={openCompare}
      />

      {compareOpen && compareEntries.length >= 2 && (
        <CompareModal entries={compareEntries} lang={lang} onClose={closeCompare} />
      )}

      <footer className="site-footer">
        <div className="inner">
          <span dir="auto" className="text-[12px] text-[var(--text-secondary)]">
            {isAr
              ? 'مستقل 100% بدون عمولات متاجر · الأسعار محدثة من متاجر مصر الموثوقة'
              : '100% independent, no store commissions · Prices refreshed from trusted Egyptian stores'}
          </span>
          <span className="text-[11px] text-[var(--text-muted)]">
            {isAr ? 'مراجعات حقيقية من يوتيوب والمنتديات' : 'Real reviews from YouTube & forums'}
          </span>
        </div>
      </footer>
    </div>
  )
}

export default App
