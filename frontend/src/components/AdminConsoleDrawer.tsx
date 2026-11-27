import React, { useCallback, useEffect, useState } from 'react'
import { Flag, Search, ShieldCheck, Users as UsersIcon, X } from 'lucide-react'
import { useUserSession } from '../context/UserSessionContext'
import {
  changeAdminUserRole,
  changeAdminUserStatus,
  fetchAdminFeedback,
  fetchAdminUsers,
  reviewAdminFeedback,
} from '../services/usersApi'
import type { AdminUser, FeedbackReport, FeedbackStatus } from '../types/users'

interface AdminConsoleDrawerProps {
  lang: 'ar' | 'en'
}

export const AdminConsoleDrawer: React.FC<AdminConsoleDrawerProps> = ({ lang }) => {
  const { user, adminConsoleOpen, setAdminConsoleOpen } = useUserSession()
  const isAr = lang === 'ar'

  const [tab, setTab] = useState<'feedback' | 'users'>('feedback')
  const [statusFilter, setStatusFilter] = useState<string>('ALL')
  const [reports, setReports] = useState<FeedbackReport[]>([])
  const [notesDraft, setNotesDraft] = useState<Record<string, string>>({})
  const [loadingReports, setLoadingReports] = useState(false)

  const [userSearch, setUserSearch] = useState('')
  const [users, setUsers] = useState<AdminUser[]>([])
  const [loadingUsers, setLoadingUsers] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const loadReports = useCallback(async () => {
    setLoadingReports(true)
    setError(null)
    try {
      const data = await fetchAdminFeedback(statusFilter)
      setReports(data)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load feedback queue')
    } finally {
      setLoadingReports(false)
    }
  }, [statusFilter])

  const loadUsers = useCallback(async () => {
    setLoadingUsers(true)
    setError(null)
    try {
      const data = await fetchAdminUsers(userSearch)
      setUsers(data)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load users')
    } finally {
      setLoadingUsers(false)
    }
  }, [userSearch])

  useEffect(() => {
    if (!adminConsoleOpen || user?.role !== 'Admin') return
    if (tab === 'feedback') {
      void loadReports()
    } else {
      void loadUsers()
    }
  }, [adminConsoleOpen, user?.role, tab, loadReports, loadUsers])

  useEffect(() => {
    if (!adminConsoleOpen) return
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setAdminConsoleOpen(false)
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [adminConsoleOpen, setAdminConsoleOpen])

  if (!adminConsoleOpen || user?.role !== 'Admin') return null

  const handleReview = async (reportId: string, status: FeedbackStatus) => {
    setError(null)
    try {
      const updated = await reviewAdminFeedback(reportId, {
        status,
        adminNotes: notesDraft[reportId] ?? undefined,
      })
      setReports((prev) => prev.map((r) => (r.id === reportId ? updated : r)))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update report')
    }
  }

  const handleRoleToggle = async (target: AdminUser) => {
    setError(null)
    const nextRole = target.role === 'Admin' ? 'User' : 'Admin'
    try {
      const updated = await changeAdminUserRole(target.id, nextRole)
      setUsers((prev) => prev.map((u) => (u.id === target.id ? updated : u)))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to change role')
    }
  }

  const handleStatusToggle = async (target: AdminUser) => {
    setError(null)
    try {
      const updated = await changeAdminUserStatus(target.id, !target.isActive)
      setUsers((prev) => prev.map((u) => (u.id === target.id ? updated : u)))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to change status')
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex justify-end bg-black/75 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-label={isAr ? 'لوحة الإدارة' : 'Admin Console'}
      onClick={() => setAdminConsoleOpen(false)}
    >
      <aside
        className="flex h-full w-full max-w-xl flex-col border-s border-[var(--border-strong)] bg-[var(--bg-surface)] shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-[var(--border-subtle)] bg-[var(--bg-raised)] px-5 py-4">
          <div className="flex items-center gap-2">
            <ShieldCheck className="w-4.5 h-4.5 text-[var(--gold)]" />
            <h2 className="font-display text-[16px] font-bold text-[var(--text-primary)]">
              {isAr ? 'لوحة تحكم الإدارة' : 'Admin Console'}
            </h2>
          </div>
          <button
            type="button"
            onClick={() => setAdminConsoleOpen(false)}
            className="rounded-lg border border-[var(--border-subtle)] p-1.5 text-[var(--text-muted)] hover:border-[var(--border-strong)] hover:text-[var(--text-primary)]"
            aria-label={isAr ? 'إغلاق' : 'Close'}
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="grid grid-cols-2 gap-1.5 border-b border-[var(--border-subtle)] bg-[var(--bg-input)] px-5 py-2.5">
          <button
            type="button"
            onClick={() => setTab('feedback')}
            className={`inline-flex items-center justify-center gap-1.5 rounded-[7px] py-2 text-[12.5px] font-semibold transition-colors ${
              tab === 'feedback'
                ? 'bg-[var(--bg-raised)] text-[var(--gold-bright)] border border-[var(--gold)]'
                : 'text-[var(--text-muted)] hover:text-[var(--text-primary)]'
            }`}
          >
            <Flag className="w-3.5 h-3.5" />
            <span>{isAr ? 'بلاغات المستخدمين' : 'Feedback Queue'}</span>
          </button>
          <button
            type="button"
            onClick={() => setTab('users')}
            className={`inline-flex items-center justify-center gap-1.5 rounded-[7px] py-2 text-[12.5px] font-semibold transition-colors ${
              tab === 'users'
                ? 'bg-[var(--bg-raised)] text-[var(--gold-bright)] border border-[var(--gold)]'
                : 'text-[var(--text-muted)] hover:text-[var(--text-primary)]'
            }`}
          >
            <UsersIcon className="w-3.5 h-3.5" />
            <span>{isAr ? 'المستخدمون والصلاحيات' : 'Users & Roles'}</span>
          </button>
        </div>

        {error && (
          <div className="mx-5 mt-3 rounded-[8px] border border-[var(--danger)] bg-[var(--danger-dim)] px-3 py-2 text-[12.5px] text-[var(--danger)]">
            {error}
          </div>
        )}

        <div className="flex-1 overflow-y-auto p-5 space-y-3">
          {tab === 'feedback' ? (
            <>
              <div className="flex flex-wrap gap-1.5">
                {(['ALL', 'OPEN', 'IN_REVIEW', 'RESOLVED', 'DISMISSED'] as const).map((s) => (
                  <button
                    key={s}
                    type="button"
                    onClick={() => setStatusFilter(s)}
                    className={`rounded-[7px] border px-2.5 py-1 text-[11.5px] font-mono font-semibold ${
                      statusFilter === s
                        ? 'border-[var(--gold)] bg-[var(--gold-dim)] text-[var(--gold-bright)]'
                        : 'border-[var(--border-subtle)] bg-[var(--bg-raised)] text-[var(--text-secondary)]'
                    }`}
                  >
                    {s}
                  </button>
                ))}
              </div>

              {loadingReports ? (
                <div className="py-10 text-center text-[13px] text-[var(--text-muted)]">
                  {isAr ? 'جاري تحميل البلاغات...' : 'Loading feedback queue...'}
                </div>
              ) : reports.length === 0 ? (
                <div className="rounded-[10px] border border-[var(--border-subtle)] bg-[var(--bg-raised)] p-8 text-center text-[13px] text-[var(--text-muted)]">
                  {isAr ? 'لا توجد بلاغات مطابقة.' : 'No reports match this filter.'}
                </div>
              ) : (
                reports.map((r) => (
                  <div
                    key={r.id}
                    className="rounded-[10px] border border-[var(--border-subtle)] bg-[var(--bg-raised)] p-4 space-y-2.5"
                  >
                    <div className="flex items-center justify-between gap-2 flex-wrap">
                      <span className="rounded border border-[var(--gold)] bg-[var(--gold-dim)] px-1.5 py-0.5 text-[10px] font-mono font-semibold text-[var(--gold-bright)]">
                        {r.status}
                      </span>
                      <span className="text-[11px] font-mono text-[var(--text-muted)]">
                        {r.category} · {r.reporterEmail || 'Guest'}
                      </span>
                    </div>

                    <h4 dir="auto" className="text-[14px] font-semibold text-[var(--text-primary)]">
                      {r.title}
                    </h4>
                    {r.laptopTitleSnapshot && (
                      <div className="text-[11.5px] text-[var(--cyan)]">
                        {r.laptopTitleSnapshot}
                      </div>
                    )}
                    <p dir="auto" className="text-[12.5px] text-[var(--text-secondary)] leading-relaxed">
                      {r.description}
                    </p>

                    <input
                      type="text"
                      value={notesDraft[r.id] ?? r.adminNotes ?? ''}
                      onChange={(e) =>
                        setNotesDraft((prev) => ({ ...prev, [r.id]: e.target.value }))
                      }
                      placeholder={isAr ? 'أضف ملاحظة للمستخدم...' : 'Add admin resolution note...'}
                      className="w-full rounded-[7px] border border-[var(--border-subtle)] bg-[var(--bg-input)] px-2.5 py-1.5 text-[12px] text-[var(--text-primary)] focus:border-[var(--gold)] focus:outline-none"
                    />

                    <div className="flex flex-wrap gap-1.5">
                      {(['IN_REVIEW', 'RESOLVED', 'DISMISSED'] as FeedbackStatus[]).map((st) => (
                        <button
                          key={st}
                          type="button"
                          onClick={() => void handleReview(r.id, st)}
                          className="btn btn-secondary btn-sm !min-h-[30px] !text-[11px] font-mono"
                        >
                          {st}
                        </button>
                      ))}
                    </div>
                  </div>
                ))
              )}
            </>
          ) : (
            <>
              <div className="relative">
                <Search className="w-4 h-4 text-[var(--text-muted)] absolute top-1/2 -translate-y-1/2 start-3" />
                <input
                  type="text"
                  value={userSearch}
                  onChange={(e) => setUserSearch(e.target.value)}
                  placeholder={isAr ? 'ابحث بالاسم أو البريد...' : 'Search by email or name...'}
                  className="w-full rounded-[8px] border border-[var(--border-subtle)] bg-[var(--bg-input)] ps-9 pe-3 py-2 text-[13px] text-[var(--text-primary)] focus:border-[var(--gold)] focus:outline-none"
                />
              </div>

              {loadingUsers ? (
                <div className="py-10 text-center text-[13px] text-[var(--text-muted)]">
                  {isAr ? 'جاري تحميل المستخدمين...' : 'Loading users...'}
                </div>
              ) : (
                users.map((u) => (
                  <div
                    key={u.id}
                    className="flex items-center justify-between gap-3 rounded-[10px] border border-[var(--border-subtle)] bg-[var(--bg-raised)] p-3.5"
                  >
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="text-[13.5px] font-semibold text-[var(--text-primary)] truncate">
                          {u.fullName}
                        </span>
                        <span
                          className={`rounded border px-1.5 py-0.5 text-[10px] font-mono font-bold ${
                            u.role === 'Admin'
                              ? 'border-[var(--gold)] bg-[var(--gold-dim)] text-[var(--gold-bright)]'
                              : 'border-[var(--border-strong)] text-[var(--text-secondary)]'
                          }`}
                        >
                          {u.role}
                        </span>
                        {!u.isActive && (
                          <span className="rounded border border-[var(--danger)] bg-[var(--danger-dim)] px-1.5 py-0.5 text-[10px] font-mono text-[var(--danger)]">
                            DISABLED
                          </span>
                        )}
                      </div>
                      <div className="text-[12px] font-mono text-[var(--text-muted)] truncate">
                        {u.email}
                      </div>
                    </div>

                    <div className="flex items-center gap-1.5 shrink-0">
                      <button
                        type="button"
                        onClick={() => void handleRoleToggle(u)}
                        className="btn btn-secondary btn-sm !min-h-[32px] !text-[11.5px]"
                      >
                        {u.role === 'Admin'
                          ? isAr
                            ? 'تخفيض لـ User'
                            : 'Make User'
                          : isAr
                          ? 'ترقية لـ Admin'
                          : 'Make Admin'}
                      </button>
                      <button
                        type="button"
                        onClick={() => void handleStatusToggle(u)}
                        className="btn btn-secondary btn-sm !min-h-[32px] !text-[11.5px]"
                      >
                        {u.isActive
                          ? isAr
                            ? 'تعطيل'
                            : 'Disable'
                          : isAr
                          ? 'تفعيل'
                          : 'Enable'}
                      </button>
                    </div>
                  </div>
                ))
              )}
            </>
          )}
        </div>
      </aside>
    </div>
  )
}
