export const MIN_REALISTIC_PRICE_EGP = 5000

export type AvailabilityState = 'in_stock' | 'coming_soon' | 'out_of_stock'

export function isValidDisplayPrice(price: number | null | undefined): price is number {
  return typeof price === 'number' && Number.isFinite(price) && price >= MIN_REALISTIC_PRICE_EGP
}

export function isPlaceholderPrice(price: number | null | undefined): boolean {
  return typeof price === 'number' && Number.isFinite(price) && price > 0 && price < MIN_REALISTIC_PRICE_EGP
}

export function isOfferAvailable(offer: { in_stock: boolean; price_egp: number }): boolean {
  return Boolean(offer.in_stock) && isValidDisplayPrice(offer.price_egp)
}

export function getAvailabilityState(
  inStock: boolean | undefined,
  priceEgp: number | null | undefined,
): AvailabilityState {
  if (isPlaceholderPrice(priceEgp)) return 'coming_soon'
  if (inStock === false || !isValidDisplayPrice(priceEgp)) return 'out_of_stock'
  return 'in_stock'
}
