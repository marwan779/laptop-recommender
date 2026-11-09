import type {
  CatalogListResponse,
  CatalogQueryParams,
  FullLaptopDetailResponse,
  RecommendationRequest,
  RecommendationResponse,
} from '../types/api'

const API_BASE = '/api/v1'

export async function fetchRecommendations(
  req: RecommendationRequest
): Promise<RecommendationResponse> {
  const response = await fetch(`${API_BASE}/recommendations`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
    },
    body: JSON.stringify(req),
  })

  if (!response.ok) {
    const errorBody = await response.text()
    throw new Error(`Recommendation failed (${response.status}): ${errorBody}`)
  }

  return response.json()
}

export async function fetchCatalog(
  params: CatalogQueryParams = {}
): Promise<CatalogListResponse> {
  const query = new URLSearchParams()
  if (params.min_price != null) query.set('min_price', String(params.min_price))
  if (params.max_price != null) query.set('max_price', String(params.max_price))
  if (params.brand) query.set('brand', params.brand)
  if (params.in_stock_only != null) query.set('in_stock_only', String(params.in_stock_only))
  if (params.offset != null) query.set('offset', String(params.offset))
  if (params.limit != null) query.set('limit', String(params.limit))

  const url = `${API_BASE}/laptops?${query.toString()}`
  const response = await fetch(url, {
    headers: { Accept: 'application/json' },
  })

  if (!response.ok) {
    throw new Error(`Failed to fetch catalog (${response.status})`)
  }

  return response.json()
}

export async function fetchLaptopDetail(
  id: string
): Promise<FullLaptopDetailResponse> {
  const response = await fetch(`${API_BASE}/laptops/${encodeURIComponent(id)}`, {
    headers: { Accept: 'application/json' },
  })

  if (!response.ok) {
    throw new Error(`Failed to load laptop detail (${response.status})`)
  }

  return response.json()
}
