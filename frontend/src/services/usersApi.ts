import type {
  AddWishlistItemRequest,
  AdminUser,
  AuthResponse,
  CreateFeedbackRequest,
  FeedbackReport,
  LoginRequest,
  MarkAllReadResponse,
  NotificationItem,
  NotificationListResponse,
  RegisterRequest,
  RoleInfo,
  UnreadCountResponse,
  UpdateFeedbackStatusRequest,
  UpdateWishlistPreferencesRequest,
  UserProfile,
  WishlistItem,
} from '../types/users'

const USERS_API_BASE = '/api/v1/users'
const ACCESS_TOKEN_KEY = 'lr_access_token'
const REFRESH_TOKEN_KEY = 'lr_refresh_token'

let refreshPromise: Promise<string | null> | null = null
let onAuthExpiredCallback: (() => void) | null = null

export function setOnAuthExpired(callback: (() => void) | null): void {
  onAuthExpiredCallback = callback
}

export function getAccessToken(): string | null {
  return localStorage.getItem(ACCESS_TOKEN_KEY)
}

export function getRefreshToken(): string | null {
  return localStorage.getItem(REFRESH_TOKEN_KEY)
}

export function storeTokens(accessToken: string, refreshToken: string): void {
  localStorage.setItem(ACCESS_TOKEN_KEY, accessToken)
  localStorage.setItem(REFRESH_TOKEN_KEY, refreshToken)
}

export function clearTokens(): void {
  localStorage.removeItem(ACCESS_TOKEN_KEY)
  localStorage.removeItem(REFRESH_TOKEN_KEY)
}

async function parseErrorMessage(response: Response): Promise<string> {
  try {
    const text = (await response.text()).trim()
    if (!text) return `Request failed (${response.status})`
    const parsed = JSON.parse(text) as { detail?: string; title?: string; message?: string }
    return parsed.detail || parsed.message || parsed.title || `Request failed (${response.status})`
  } catch {
    return `Request failed (${response.status})`
  }
}

async function refreshAccessToken(): Promise<string | null> {
  if (refreshPromise) return refreshPromise

  const refreshToken = getRefreshToken()
  if (!refreshToken) {
    clearTokens()
    return null
  }

  refreshPromise = (async () => {
    try {
      const response = await fetch(`${USERS_API_BASE}/auth/refresh`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Accept: 'application/json',
        },
        body: JSON.stringify({ refreshToken }),
      })

      if (!response.ok) {
        clearTokens()
        onAuthExpiredCallback?.()
        return null
      }

      const data = (await response.json()) as AuthResponse
      storeTokens(data.accessToken, data.refreshToken)
      return data.accessToken
    } catch {
      return null
    } finally {
      refreshPromise = null
    }
  })()

  return refreshPromise
}

async function usersFetch<T>(
  path: string,
  init: RequestInit = {},
  retryOnUnauthorized = true,
): Promise<T> {
  const token = getAccessToken()
  const headers = new Headers(init.headers)
  headers.set('Accept', 'application/json')
  if (init.body && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }
  if (token) {
    headers.set('Authorization', `Bearer ${token}`)
  }

  const response = await fetch(`${USERS_API_BASE}${path}`, {
    ...init,
    headers,
  })

  if (response.status === 401 && retryOnUnauthorized && getRefreshToken()) {
    const newToken = await refreshAccessToken()
    if (newToken) {
      return usersFetch<T>(path, init, false)
    }
  }

  if (!response.ok) {
    throw new Error(await parseErrorMessage(response))
  }

  if (response.status === 204) {
    return undefined as T
  }

  const text = await response.text()
  if (!text) return undefined as T
  return JSON.parse(text) as T
}

export async function loginUser(request: LoginRequest): Promise<AuthResponse> {
  const data = await usersFetch<AuthResponse>(
    '/auth/login',
    { method: 'POST', body: JSON.stringify(request) },
    false,
  )
  storeTokens(data.accessToken, data.refreshToken)
  return data
}

export async function registerUser(request: RegisterRequest): Promise<AuthResponse> {
  const data = await usersFetch<AuthResponse>(
    '/auth/register',
    { method: 'POST', body: JSON.stringify(request) },
    false,
  )
  storeTokens(data.accessToken, data.refreshToken)
  return data
}

export async function logoutUser(): Promise<void> {
  const refreshToken = getRefreshToken()
  try {
    if (refreshToken) {
      await usersFetch<void>(
        '/auth/logout',
        { method: 'POST', body: JSON.stringify({ refreshToken }) },
        false,
      )
    }
  } finally {
    clearTokens()
  }
}

export async function fetchCurrentUser(): Promise<UserProfile> {
  return usersFetch<UserProfile>('/auth/me')
}

export async function fetchWishlist(): Promise<WishlistItem[]> {
  return usersFetch<WishlistItem[]>('/wishlist')
}

export async function addToWishlist(request: AddWishlistItemRequest): Promise<WishlistItem> {
  return usersFetch<WishlistItem>('/wishlist', {
    method: 'POST',
    body: JSON.stringify(request),
  })
}

export async function updateWishlistPreferences(
  canonicalId: string,
  request: UpdateWishlistPreferencesRequest,
): Promise<WishlistItem> {
  return usersFetch<WishlistItem>(`/wishlist/${encodeURIComponent(canonicalId)}`, {
    method: 'PATCH',
    body: JSON.stringify(request),
  })
}

export async function removeFromWishlist(canonicalId: string): Promise<void> {
  await usersFetch<void>(`/wishlist/${encodeURIComponent(canonicalId)}`, {
    method: 'DELETE',
  })
}

export async function fetchNotifications(
  unreadOnly = false,
  limit = 50,
): Promise<NotificationListResponse> {
  const query = new URLSearchParams({
    unreadOnly: String(unreadOnly),
    limit: String(limit),
  })
  return usersFetch<NotificationListResponse>(`/notifications?${query.toString()}`)
}

export async function fetchUnreadCount(): Promise<UnreadCountResponse> {
  return usersFetch<UnreadCountResponse>('/notifications/unread-count')
}

export async function markNotificationRead(notificationId: string): Promise<NotificationItem> {
  return usersFetch<NotificationItem>(`/notifications/${encodeURIComponent(notificationId)}/read`, {
    method: 'PATCH',
  })
}

export async function markAllNotificationsRead(): Promise<MarkAllReadResponse> {
  return usersFetch<MarkAllReadResponse>('/notifications/read-all', {
    method: 'PATCH',
  })
}

export async function clearAllNotifications(): Promise<{ deletedCount: number }> {
  return usersFetch<{ deletedCount: number }>('/notifications', {
    method: 'DELETE',
  })
}

export async function submitFeedback(request: CreateFeedbackRequest): Promise<FeedbackReport> {
  return usersFetch<FeedbackReport>('/feedback', {
    method: 'POST',
    body: JSON.stringify(request),
  })
}

export async function fetchMyFeedback(): Promise<FeedbackReport[]> {
  return usersFetch<FeedbackReport[]>('/feedback/mine')
}

export async function fetchAdminRoles(): Promise<RoleInfo[]> {
  return usersFetch<RoleInfo[]>('/admin/roles')
}

export async function fetchAdminUsers(search?: string): Promise<AdminUser[]> {
  const query = new URLSearchParams({ limit: '50', offset: '0' })
  if (search && search.trim()) query.set('search', search.trim())
  return usersFetch<AdminUser[]>(`/admin/users?${query.toString()}`)
}

export async function changeAdminUserRole(userId: string, role: string): Promise<AdminUser> {
  return usersFetch<AdminUser>(`/admin/users/${encodeURIComponent(userId)}/role`, {
    method: 'PATCH',
    body: JSON.stringify({ role }),
  })
}

export async function changeAdminUserStatus(userId: string, isActive: boolean): Promise<AdminUser> {
  return usersFetch<AdminUser>(`/admin/users/${encodeURIComponent(userId)}/status`, {
    method: 'PATCH',
    body: JSON.stringify({ isActive }),
  })
}

export async function fetchAdminFeedback(status?: string): Promise<FeedbackReport[]> {
  const query = new URLSearchParams({ limit: '50', offset: '0' })
  if (status && status !== 'ALL') query.set('status', status)
  return usersFetch<FeedbackReport[]>(`/admin/feedback?${query.toString()}`)
}

export async function reviewAdminFeedback(
  feedbackId: string,
  request: UpdateFeedbackStatusRequest,
): Promise<FeedbackReport> {
  return usersFetch<FeedbackReport>(`/admin/feedback/${encodeURIComponent(feedbackId)}`, {
    method: 'PATCH',
    body: JSON.stringify(request),
  })
}
