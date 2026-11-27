import React, { useEffect, useState } from 'react'
import { Bell, CheckCheck, ExternalLink, Trash2, X } from 'lucide-react'
import { useUserSession } from '../context/UserSessionContext'
import type { NotificationItem } from '../types/users'

interface NotificationsDrawerProps {
  lang: 'ar' | 'en'
  onSelectNotification?: (notification: NotificationItem) => void
}

export const NotificationsDrawer: React.FC<NotificationsDrawerProps> = ({
  lang,
  onSelectNotification,
}) => {
  const {
    notificationsOpen,
    setNotificationsOpen,
    notifications,
    unreadCount,
    notificationsLoading,
    refreshNotifications,
    markAsRead,
    markAllAsRead,
    clearAllNotifications,
  } = useUserSession()
  const [clearing, setClearing] = useState(false)
  const isAr = lang === 'ar'

  useEffect(() => {
    if (notificationsOpen) {
      void refreshNotifications()
    }
  }, [notificationsOpen, refreshNotifications])

  if (!notificationsOpen) return null

  const handleNotificationClick = (n: NotificationItem) => {
    if (!n.isRead) {
      void markAsRead(n.id)
    }
    setNotificationsOpen(false)
    onSelectNotification?.(n)
  }

  const handleClearAll = async () => {
    if (clearing) return
    setClearing(true)
    try {
      await clearAllNotifications()
    } finally {
      setClearing(false)
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex justify-end bg-black/70 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-label={isAr ? 'التنبيهات' : 'Notifications'}
      onClick={() => setNotificationsOpen(false)}
    >
      <aside
        className="flex h-full w-full max-w-md flex-col border-s border-[var(--border-strong)] bg-[var(--bg-surface)] shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between gap-2 border-b border-[var(--border-subtle)] bg-[var(--bg-raised)] px-5 py-4">
          <div className="flex items-center gap-2 min-w-0">
            <Bell className="w-4 h-4 text-[var(--gold)] shrink-0" />
            <h2 className="font-display text-[16px] font-bold text-[var(--text-primary)] truncate">
              {isAr ? 'التنبيهات' : 'Price Alerts'}
            </h2>
            {unreadCount > 0 && (
              <span className="rounded-full bg-[var(--gold-dim)] border border-[var(--gold)] px-2 py-0.5 text-[11px] font-mono font-bold text-[var(--gold-bright)] num">
                {unreadCount}
              </span>
            )}
          </div>

          <div className="flex items-center gap-1.5 shrink-0">
            {unreadCount > 0 && (
              <button
                type="button"
                onClick={() => void markAllAsRead()}
                className="inline-flex items-center gap-1 rounded-[7px] border border-[var(--border-subtle)] px-2 py-1 text-[11.5px] font-medium text-[var(--text-secondary)] hover:border-[var(--border-strong)] hover:text-[var(--text-primary)]"
                title={isAr ? 'تحديد الكل كمقروء' : 'Mark all read'}
              >
                <CheckCheck className="w-3.5 h-3.5 text-[var(--emerald)]" />
                <span>{isAr ? 'قراءة الكل' : 'Mark read'}</span>
              </button>
            )}
            {notifications.length > 0 && (
              <button
                type="button"
                disabled={clearing}
                onClick={() => void handleClearAll()}
                className="inline-flex items-center gap-1 rounded-[7px] border border-[var(--border-subtle)] px-2 py-1 text-[11.5px] font-medium text-[var(--text-secondary)] hover:border-[var(--danger)] hover:text-[var(--danger)]"
                title={isAr ? 'حذف جميع التنبيهات' : 'Clear all notifications'}
              >
                <Trash2 className="w-3.5 h-3.5" />
                <span>{isAr ? 'حذف الكل' : 'Clear all'}</span>
              </button>
            )}
            <button
              type="button"
              onClick={() => setNotificationsOpen(false)}
              className="rounded-lg border border-[var(--border-subtle)] p-1.5 text-[var(--text-muted)] hover:border-[var(--border-strong)] hover:text-[var(--text-primary)]"
              aria-label={isAr ? 'إغلاق' : 'Close'}
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto p-4 space-y-2.5">
          {notificationsLoading ? (
            <div className="py-12 text-center text-[13px] text-[var(--text-muted)]">
              {isAr ? 'جاري تحميل التنبيهات...' : 'Loading alerts...'}
            </div>
          ) : notifications.length === 0 ? (
            <div className="rounded-[10px] border border-[var(--border-subtle)] bg-[var(--bg-raised)] p-8 text-center space-y-2">
              <Bell className="w-7 h-7 text-[var(--text-muted)] mx-auto" />
              <p className="text-[14px] font-semibold text-[var(--text-primary)]">
                {isAr ? 'لا توجد تنبيهات بعد' : 'No alerts yet'}
              </p>
              <p className="text-[12px] text-[var(--text-muted)]">
                {isAr
                  ? 'ستظهر هنا إشعارات انخفاض الأسعار أو عودة التوفر للابتوبات المفضلة.'
                  : 'Price drops and restocks for your watched laptops will appear here.'}
              </p>
            </div>
          ) : (
            notifications.map((n) => {
              const badgeColor =
                n.changeType === 'PRICE_DROP'
                  ? 'border-[var(--emerald)] text-[var(--emerald)] bg-[var(--emerald-dim)]'
                  : n.changeType === 'RESTOCK'
                  ? 'border-[var(--cyan)] text-[var(--cyan)] bg-[var(--cyan-dim)]'
                  : 'border-[var(--border-strong)] text-[var(--text-secondary)] bg-[var(--bg-input)]'

              return (
                <button
                  key={n.id}
                  type="button"
                  onClick={() => handleNotificationClick(n)}
                  className={`group w-full text-start rounded-[10px] border p-3.5 transition-colors hover:border-[var(--cyan)] ${
                    n.isRead
                      ? 'border-[var(--border-subtle)] bg-[var(--bg-raised)] opacity-85 hover:opacity-100'
                      : 'border-[var(--gold)] bg-[var(--bg-raised)]'
                  }`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className={`inline-flex items-center rounded border px-1.5 py-0.5 text-[10px] font-mono font-semibold ${badgeColor}`}>
                      {n.changeType}
                    </span>
                    <span className="inline-flex items-center gap-1.5 text-[11px] font-mono text-[var(--text-muted)] num">
                      {new Date(n.createdAtUtc).toLocaleDateString(isAr ? 'ar-EG' : 'en-US', {
                        month: 'short',
                        day: 'numeric',
                      })}
                      <ExternalLink className="w-3 h-3 opacity-0 group-hover:opacity-100 text-[var(--cyan)] transition-opacity" />
                    </span>
                  </div>

                  <div className="mt-2 flex items-start justify-between gap-2">
                    <h4 dir="auto" className="text-[13.5px] font-semibold text-[var(--text-primary)] group-hover:text-[var(--gold-bright)] transition-colors">
                      {n.title}
                    </h4>
                    {!n.isRead && (
                      <span className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-[var(--gold)]" />
                    )}
                  </div>

                  <p dir="auto" className="mt-1 text-[12.5px] text-[var(--text-secondary)] leading-relaxed">
                    {n.message}
                  </p>

                  {n.newPriceEgp != null && (
                    <div className="mt-2 flex items-center gap-2 text-[12px] font-mono num">
                      <span className="font-bold text-[var(--gold)]">
                        {n.newPriceEgp.toLocaleString('en-US')} EGP
                      </span>
                      {n.oldPriceEgp != null && n.oldPriceEgp !== n.newPriceEgp && (
                        <span className="text-[var(--text-muted)] line-through">
                          {n.oldPriceEgp.toLocaleString('en-US')} EGP
                        </span>
                      )}
                      {n.cheapestStore && (
                        <span className="text-[var(--text-muted)]">· {n.cheapestStore}</span>
                      )}
                    </div>
                  )}
                </button>
              )
            })
          )}
        </div>
      </aside>
    </div>
  )
}
