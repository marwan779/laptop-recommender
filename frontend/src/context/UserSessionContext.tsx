import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'
import type {
  AddWishlistItemRequest,
  AuthResponse,
  NotificationItem,
  UpdateWishlistPreferencesRequest,
  UserProfile,
  WishlistItem,
} from '../types/users'
import {
  addToWishlist,
  clearTokens,
  fetchCurrentUser,
  fetchNotifications,
  fetchUnreadCount,
  fetchWishlist,
  getAccessToken,
  getRefreshToken,
  logoutUser,
  markAllNotificationsRead,
  markNotificationRead,
  removeFromWishlist,
  setOnAuthExpired,
  updateWishlistPreferences,
} from '../services/usersApi'

const DEFAULT_POLL_MS = import.meta.env.DEV ? 30_000 : 3_600_000
const POLL_INTERVAL_MS = (() => {
  const parsed = Number(import.meta.env.VITE_NOTIFICATIONS_POLL_MS)
  return Number.isFinite(parsed) && parsed >= 5_000 ? parsed : DEFAULT_POLL_MS
})()
const STALE_COOLDOWN_MS = import.meta.env.DEV ? 10_000 : 15 * 60_000

interface UserSessionContextValue {
  user: UserProfile | null
  authLoading: boolean
  wishlistItems: WishlistItem[]
  wishlistIds: Set<string>
  notifications: NotificationItem[]
  unreadCount: number
  notificationsLoading: boolean
  authModalOpen: boolean
  wishlistDrawerOpen: boolean
  notificationsOpen: boolean
  setAuthModalOpen: (open: boolean) => void
  setWishlistDrawerOpen: (open: boolean) => void
  setNotificationsOpen: (open: boolean) => void
  handleAuthSuccess: (auth: AuthResponse) => Promise<void>
  logout: () => Promise<void>
  toggleWishlist: (item: AddWishlistItemRequest) => Promise<void>
  saveWishlistPreferences: (
    canonicalId: string,
    prefs: UpdateWishlistPreferencesRequest,
  ) => Promise<WishlistItem>
  removeWishlistItem: (canonicalId: string) => Promise<void>
  refreshNotifications: () => Promise<void>
  markAsRead: (notificationId: string) => Promise<void>
  markAllAsRead: () => Promise<void>
}

const UserSessionContext = createContext<UserSessionContextValue | null>(null)

export const UserSessionProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<UserProfile | null>(null)
  const [authLoading, setAuthLoading] = useState<boolean>(() => Boolean(getAccessToken() || getRefreshToken()))
  const [wishlistItems, setWishlistItems] = useState<WishlistItem[]>([])
  const [notifications, setNotifications] = useState<NotificationItem[]>([])
  const [unreadCount, setUnreadCount] = useState<number>(0)
  const [notificationsLoading, setNotificationsLoading] = useState<boolean>(false)

  const [authModalOpen, setAuthModalOpen] = useState<boolean>(false)
  const [wishlistDrawerOpen, setWishlistDrawerOpen] = useState<boolean>(false)
  const [notificationsOpen, setNotificationsOpen] = useState<boolean>(false)

  const lastPollAtRef = useRef<number>(0)
  const pendingWishlistRef = useRef<AddWishlistItemRequest | null>(null)

  const resetSession = useCallback(() => {
    setUser(null)
    setWishlistItems([])
    setNotifications([])
    setUnreadCount(0)
    setWishlistDrawerOpen(false)
    setNotificationsOpen(false)
  }, [])

  const loadUserData = useCallback(async () => {
    const [wl, unread] = await Promise.all([
      fetchWishlist().catch(() => [] as WishlistItem[]),
      fetchUnreadCount().catch(() => ({ unreadCount: 0 })),
    ])
    setWishlistItems(wl)
    setUnreadCount(unread.unreadCount)
    lastPollAtRef.current = Date.now()
  }, [])

  useEffect(() => {
    setOnAuthExpired(() => {
      resetSession()
    })
    return () => setOnAuthExpired(null)
  }, [resetSession])

  // Hydrate existing session on mount
  useEffect(() => {
    if (!getAccessToken() && !getRefreshToken()) {
      setAuthLoading(false)
      return
    }

    let cancelled = false
    fetchCurrentUser()
      .then(async (profile) => {
        if (cancelled) return
        setUser(profile)
        await loadUserData()
      })
      .catch(() => {
        if (!cancelled) {
          clearTokens()
          resetSession()
        }
      })
      .finally(() => {
        if (!cancelled) setAuthLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [loadUserData, resetSession])

  // Smart Polling for unread notification count (pauses when tab is hidden)
  useEffect(() => {
    if (!user) return

    const pollUnread = async () => {
      if (document.visibilityState === 'hidden') return
      try {
        const res = await fetchUnreadCount()
        setUnreadCount(res.unreadCount)
        lastPollAtRef.current = Date.now()
      } catch {
        // Silent fail on background poll
      }
    }

    const handleVisibility = () => {
      if (document.visibilityState !== 'visible') return
      if (Date.now() - lastPollAtRef.current >= STALE_COOLDOWN_MS) {
        void pollUnread()
      }
    }

    const timer = window.setInterval(() => {
      void pollUnread()
    }, POLL_INTERVAL_MS)

    document.addEventListener('visibilitychange', handleVisibility)
    return () => {
      window.clearInterval(timer)
      document.removeEventListener('visibilitychange', handleVisibility)
    }
  }, [user])

  const handleAuthSuccess = useCallback(
    async (auth: AuthResponse) => {
      setUser({
        userId: auth.userId,
        email: auth.email,
        fullName: auth.fullName,
        role: auth.role,
        preferredLanguage: auth.preferredLanguage,
      })
      setAuthModalOpen(false)
      await loadUserData()

      const pending = pendingWishlistRef.current
      pendingWishlistRef.current = null
      if (pending) {
        try {
          const created = await addToWishlist(pending)
          setWishlistItems((prev) =>
            prev.some((w) => w.canonicalId === created.canonicalId) ? prev : [created, ...prev],
          )
        } catch {
          // Ignore if already in wishlist
        }
      }
    },
    [loadUserData],
  )

  const logout = useCallback(async () => {
    await logoutUser()
    resetSession()
  }, [resetSession])

  const wishlistIds = useMemo(
    () => new Set(wishlistItems.map((w) => w.canonicalId)),
    [wishlistItems],
  )

  const toggleWishlist = useCallback(
    async (item: AddWishlistItemRequest) => {
      if (!user) {
        pendingWishlistRef.current = item
        setAuthModalOpen(true)
        return
      }

      if (wishlistIds.has(item.canonicalId)) {
        await removeFromWishlist(item.canonicalId)
        setWishlistItems((prev) => prev.filter((w) => w.canonicalId !== item.canonicalId))
      } else {
        const created = await addToWishlist(item)
        setWishlistItems((prev) => [created, ...prev.filter((w) => w.canonicalId !== created.canonicalId)])
      }
    },
    [user, wishlistIds],
  )

  const saveWishlistPreferences = useCallback(
    async (canonicalId: string, prefs: UpdateWishlistPreferencesRequest) => {
      const updated = await updateWishlistPreferences(canonicalId, prefs)
      setWishlistItems((prev) =>
        prev.map((w) => (w.canonicalId === canonicalId ? updated : w)),
      )
      return updated
    },
    [],
  )

  const removeWishlistItem = useCallback(async (canonicalId: string) => {
    await removeFromWishlist(canonicalId)
    setWishlistItems((prev) => prev.filter((w) => w.canonicalId !== canonicalId))
  }, [])

  const refreshNotifications = useCallback(async () => {
    if (!user) return
    setNotificationsLoading(true)
    try {
      const res = await fetchNotifications(false, 50)
      setNotifications(res.items)
      setUnreadCount(res.unreadCount)
      lastPollAtRef.current = Date.now()
    } finally {
      setNotificationsLoading(false)
    }
  }, [user])

  const markAsRead = useCallback(async (notificationId: string) => {
    const updated = await markNotificationRead(notificationId)
    setNotifications((prev) =>
      prev.map((n) => (n.id === notificationId ? updated : n)),
    )
    setUnreadCount((prev) => Math.max(0, prev - 1))
  }, [])

  const markAllAsRead = useCallback(async () => {
    await markAllNotificationsRead()
    const now = new Date().toISOString()
    setNotifications((prev) => prev.map((n) => (n.isRead ? n : { ...n, isRead: true, readAtUtc: now })))
    setUnreadCount(0)
  }, [])

  return (
    <UserSessionContext.Provider
      value={{
        user,
        authLoading,
        wishlistItems,
        wishlistIds,
        notifications,
        unreadCount,
        notificationsLoading,
        authModalOpen,
        wishlistDrawerOpen,
        notificationsOpen,
        setAuthModalOpen,
        setWishlistDrawerOpen,
        setNotificationsOpen,
        handleAuthSuccess,
        logout,
        toggleWishlist,
        saveWishlistPreferences,
        removeWishlistItem,
        refreshNotifications,
        markAsRead,
        markAllAsRead,
      }}
    >
      {children}
    </UserSessionContext.Provider>
  )
}

export function useUserSession(): UserSessionContextValue {
  const ctx = useContext(UserSessionContext)
  if (!ctx) {
    throw new Error('useUserSession must be used within UserSessionProvider')
  }
  return ctx
}
