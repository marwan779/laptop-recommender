export interface UserProfile {
  userId: string
  email: string
  fullName: string
  role: string
  preferredLanguage: string
  emailVerified?: boolean
}

export interface AuthResponse {
  accessToken: string
  refreshToken: string
  userId: string
  email: string
  fullName: string
  role: string
  preferredLanguage: string
}

export interface LoginRequest {
  email: string
  password: string
}

export interface RegisterRequest {
  email: string
  fullName: string
  password: string
  preferredLanguage?: string
}

export interface WishlistItem {
  id: string
  canonicalId: string
  titleSnapshot: string
  thumbnailUrlSnapshot: string | null
  addedPriceEgp: number
  lastNotifiedPriceEgp: number | null
  targetPriceEgp: number | null
  notifyOnPriceDrop: boolean
  notifyOnAnyChange: boolean
  notifyOnRestock: boolean
  createdAtUtc: string
  updatedAtUtc: string | null
}

export interface AddWishlistItemRequest {
  canonicalId: string
  titleSnapshot: string
  addedPriceEgp: number
  thumbnailUrlSnapshot?: string | null
  targetPriceEgp?: number | null
  notifyOnPriceDrop?: boolean
  notifyOnAnyChange?: boolean
  notifyOnRestock?: boolean
}

export interface UpdateWishlistPreferencesRequest {
  targetPriceEgp: number | null
  notifyOnPriceDrop: boolean
  notifyOnAnyChange: boolean
  notifyOnRestock: boolean
}

export interface NotificationItem {
  id: string
  canonicalId: string
  title: string
  message: string
  changeType: string
  oldPriceEgp: number | null
  newPriceEgp: number | null
  cheapestStore: string | null
  isRead: boolean
  readAtUtc: string | null
  createdAtUtc: string
}

export interface NotificationListResponse {
  items: NotificationItem[]
  unreadCount: number
}

export interface UnreadCountResponse {
  unreadCount: number
}

export interface MarkAllReadResponse {
  markedCount: number
}

export type FeedbackCategory =
  | 'WRONG_PRICE'
  | 'WRONG_SPEC'
  | 'BROKEN_LINK'
  | 'MISSING_LAPTOP'
  | 'UI_BUG'
  | 'OTHER'

export type FeedbackStatus = 'OPEN' | 'IN_REVIEW' | 'RESOLVED' | 'DISMISSED'

export interface FeedbackReport {
  id: string
  userId: string | null
  reporterEmail: string | null
  category: FeedbackCategory | string
  canonicalId: string | null
  laptopTitleSnapshot: string | null
  title: string
  description: string
  pageUrl: string | null
  status: FeedbackStatus | string
  adminNotes: string | null
  resolvedByUserId: string | null
  resolvedAtUtc: string | null
  createdAtUtc: string
  updatedAtUtc: string | null
}

export interface CreateFeedbackRequest {
  category: FeedbackCategory
  title: string
  description: string
  reporterEmail?: string | null
  canonicalId?: string | null
  laptopTitleSnapshot?: string | null
  pageUrl?: string | null
}

export interface UpdateFeedbackStatusRequest {
  status: FeedbackStatus
  adminNotes?: string | null
}

export interface RoleInfo {
  id: string
  name: string
  description: string | null
}

export interface AdminUser {
  id: string
  email: string
  fullName: string
  role: string
  roleId: string
  isActive: boolean
  emailVerified: boolean
  createdAtUtc: string
}
