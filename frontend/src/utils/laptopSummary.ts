import type { RankedLaptop } from '../types/api'

export type SortOption = 'best' | 'cheapest' | 'battery' | 'thermals' | 'display'

export interface StoreSavings {
  storeCount: number
  minPrice: number
  maxPrice: number
  savingsEgp: number
  sortedOffers: RankedLaptop['offers']
}

const isPositivePrice = (value: unknown): value is number =>
  typeof value === 'number' && Number.isFinite(value) && value > 0

/**
 * Derive the honest multi-store price spread for a recommendation card.
 * Prefers in-stock offers, then all offers, then the raw prices map.
 */
export function computeStoreSavings(
  laptop: Pick<
    RankedLaptop,
    'effective_price_egp' | 'cheapest_store' | 'prices_by_store' | 'offers'
  >,
): StoreSavings {
  const offers = Array.isArray(laptop.offers) ? laptop.offers : []
  const inStock = offers.filter((offer) => offer.in_stock && isPositivePrice(offer.price_egp))
  const priced = inStock.length > 0 ? inStock : offers.filter((offer) => isPositivePrice(offer.price_egp))

  let sortedOffers = [...priced].sort((a, b) => a.price_egp - b.price_egp)
  let prices = sortedOffers.map((offer) => offer.price_egp)

  if (prices.length === 0) {
    const mapPrices = Object.values(laptop.prices_by_store || {}).filter(isPositivePrice)
    prices = mapPrices.sort((a, b) => a - b)
    sortedOffers = []
  }

  const storeCount =
    sortedOffers.length > 0
      ? new Set(sortedOffers.map((offer) => offer.store_key)).size
      : new Set(Object.keys(laptop.prices_by_store || {})).size

  const fallbackPrice = isPositivePrice(laptop.effective_price_egp)
    ? laptop.effective_price_egp
    : null

  const minPrice = prices.length > 0 ? prices[0] : fallbackPrice ?? 0
  const maxPrice = prices.length > 0 ? prices[prices.length - 1] : minPrice
  const savingsEgp = Math.max(0, maxPrice - minPrice)

  return { storeCount, minPrice, maxPrice, savingsEgp, sortedOffers }
}

const CPU_PATTERNS: RegExp[] = [
  /Intel\s+Core\s+Ultra\s+[3579]\s+\d{3}\w*/i,
  /Core\s+i[3579][-\s]?\d{3,5}\w*/i,
  /Ryzen\s+[3579][-\s]?\d{3,4}\w*/i,
  /Apple\s+M[1-4](?:\s+(?:Pro|Max))?/i,
  /Snapdragon\s+X(?:\s+Elite)?/i,
]

const GPU_PATTERNS: RegExp[] = [
  /RTX\s?\d{4}(?:\s?Ti)?/i,
  /GTX\s?\d{4}/i,
  /RX\s?\d{4}\w*/i,
  /Arc\s+[A-Z]?\d{3}\w*/i,
]

const DISPLAY_PATTERNS: RegExp[] = [
  /\b(?:13\.[346]|14(?:\.\d)?|15\.[6]|16(?:\.\d)?|17\.[3])\s*(?:inch|in|”|"|')/i,
  /\b(?:120|144|165|240|300)\s?Hz\b/i,
  /\bOLED\b/i,
]

const STORAGE_PATTERN = /\b(256|512)\s?GB\b|\b(1|2|4)\s?TB\b/i
const RAM_PATTERN = /\b(8|12|16|24|32|48|64)\s?GB\b/i
const DDR_PATTERN = /\b(?:DDR[45]|LPDDR[45]X?)\b/i

function matchFirst(patterns: RegExp[], text: string): string | null {
  for (const pattern of patterns) {
    const match = text.match(pattern)
    if (match) return match[0].replace(/\s+/g, ' ').trim()
  }
  return null
}

/**
 * Conservatively pull only tokens that are literally printed in the store
 * title. Never fabricates a spec that the retailer did not publish.
 */
export function extractQuickSpecs(title: string): string[] {
  const text = (title || '').trim()
  if (!text) return []

  const chips: string[] = []

  const display = matchFirst(DISPLAY_PATTERNS, text)
  if (display) chips.push(display.replace(/\s*(?:inch|in)$/i, '"'))

  const cpu = matchFirst(CPU_PATTERNS, text)
  if (cpu) chips.push(cpu)

  const gpu = matchFirst(GPU_PATTERNS, text)
  if (gpu) chips.push(gpu.toUpperCase().replace(/\s+/g, ' '))

  const storage = text.match(STORAGE_PATTERN)
  if (storage) chips.push(storage[0].toUpperCase().replace(/\s+/g, ''))

  const ram = text.match(RAM_PATTERN)
  if (ram) {
    const ddr = text.match(DDR_PATTERN)
    chips.push(ddr ? `${ram[0].toUpperCase().replace(/\s+/g, '')} ${ddr[0].toUpperCase()}` : ram[0].toUpperCase())
  }

  return Array.from(new Set(chips)).slice(0, 5)
}

const scoreOr = (value: number | null | undefined): number =>
  value == null || Number.isNaN(Number(value)) ? -1 : Number(value)

/** Client-side sort comparators for the Stage 2 results strip. */
export function getSortComparator(sortKey: SortOption) {
  return (a: RankedLaptop, b: RankedLaptop): number => {
    switch (sortKey) {
      case 'cheapest':
        return a.effective_price_egp - b.effective_price_egp
      case 'battery':
        return (
          scoreOr(b.aspect_scores?.real_battery_and_reliability_score) -
          scoreOr(a.aspect_scores?.real_battery_and_reliability_score)
        )
      case 'thermals':
        return scoreOr(b.aspect_scores?.thermals_score) - scoreOr(a.aspect_scores?.thermals_score)
      case 'display':
        return scoreOr(b.topsis_inputs?.display_score) - scoreOr(a.topsis_inputs?.display_score)
      case 'best':
      default:
        return a.rank - b.rank
    }
  }
}

/** Shared clean model title used by cards, compare columns and the workbench. */
export function formatCardTitle(
  brand?: string | null,
  family?: string | null,
  model?: string | null,
): string {
  const b = (brand || '').trim()
  let f = (family || '').trim()
  let m = (model || '').trim()

  if (b && m.toLowerCase().startsWith(b.toLowerCase())) {
    m = m.slice(b.length).replace(/^[\s\-_:/]+/, '')
  }

  if (!m) {
    if (b && f.toLowerCase().startsWith(b.toLowerCase())) {
      f = f.slice(b.length).replace(/^[\s\-_:/]+/, '')
    }
    return f || b
  }

  if (!f) return m

  const fClean = f.replace(/[^a-zA-Z0-9]/g, '').toLowerCase()
  const mClean = m.replace(/[^a-zA-Z0-9]/g, '').toLowerCase()

  if (fClean && mClean && (mClean.includes(fClean) || fClean.includes(mClean))) {
    return m
  }

  return `${f} ${m}`
}
