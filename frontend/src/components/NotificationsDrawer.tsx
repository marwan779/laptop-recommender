import React, { useEffect } from 'react'
import { Bell, CheckCheck, X } from 'lucide-react'
import { useUserSession } from '../context/UserSessionContext'

interface NotificationsDrawerProps {
  lang: 'ar' | 'en'
}

export const NotificationsDrawer: React.FC<NotificationsDrawerProps> = ({ lang }) => {
  const {
    notificationsOpen,
    setNotificationsOpen,
    notifications,
    unreadCount,
    notificationsLoading,
    refreshNotifications,
    markAsRead,
    markAllAsRead,
  } = useUserSession()
  const isAr = lang === 'ar'

  useEffect(() => {
    if (notificationsOpen) {
      void refreshNotifications()
    }
  }, [notificationsOpen, refreshNotifications])

  if (!notificationsOpen) return null

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
        <div className="flex items-center justify-between border-b border-[var(--border-subtle)] bg-[var(--bg-raised)] px-5 py-4">
          <div className="flex items-center gap-2">
            <Bell className="w-4 h-4 text-[var(--gold)]" />
            <h2 className="font-display text-[16px] font-bold text-[var(--text-primary)]">
              {isAr ? 'التنبيهات' : 'Price Alerts'}
            </h2>
            {unreadCount > 0 && (
              <span className="rounded-full bg-[var(--gold-dim)] border border-[var(--gold)] px-2 py-0.5 text-[11px] font-mono font-bold text-[var(--gold-bright)] num">
                {unreadCount}
              </span>
            )}
          </div>

          <div className="flex items-center gap-2">
            {unreadCount > 0 && (
              <button
                type="button"
                onClick={() => void markAllAsRead()}
                className="inline-flex items-center gap-1 rounded-[7px] border border-[var(--border-subtle)] px-2.5 py-1 text-[11.5px] font-medium text-[var(--text-secondary)] hover:border-[var(--border-strong)] hover:text-[var(--text-primary)]"
              >
                <CheckCheck className="w-3.5 h-3.5 text-[var(--emerald)]" />
                <span>{isAr ? 'قراءة الكل' : 'Mark all read'}</span>
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
                  onClick={() => {
                    if (!n.isRead) void markAsRead(n.id)
                  }}
                  className={`w-full text-start rounded-[10px] border p-3.5 transition-colors ${
                    n.isRead
                      ? 'border-[var(--border-subtle)] bg-[var(--bg-raised)] opacity-75'
                      : 'border-[var(--gold)] bg-[var(--bg-raised)]'
                  }`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className={`inline-flex items-center rounded border px-1.5 py-0.5 text-[10px] font-mono font-semibold ${badgeColor}`}>
                      {n.changeType}
                    </span>
                    <span className="text-[11px] font-mono text-[var(--text-muted)] num">
                      {new Date(n.createdAtUtc).toLocaleDateString(isAr ? 'ar-EG' : 'en-US', {
                        month: 'short',
                        day: 'numeric',
                      })}
                    </span>
                  </div>

                  <div className="mt-2 flex items-start justify-between gap-2">
                    <h4 dir="auto" className="text-[13.5px] font-semibold text-[var(--text-primary)]">
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
