import React, { useEffect, useState } from 'react'
import { CheckCircle, Flag, History, Send, X } from 'lucide-react'
import { useUserSession } from '../context/UserSessionContext'
import { fetchMyFeedback, submitFeedback } from '../services/usersApi'
import type { FeedbackCategory, FeedbackReport } from '../types/users'

interface FeedbackModalProps {
  lang: 'ar' | 'en'
}

const CATEGORIES: Array<{ value: FeedbackCategory; en: string; ar: string }> = [
  { value: 'WRONG_PRICE', en: 'Wrong price or store offer', ar: 'سعر أو متجر غير صحيح' },
  { value: 'WRONG_SPEC', en: 'Wrong hardware specification', ar: 'مواصفة تقنية غير صحيحة' },
  { value: 'BROKEN_LINK', en: 'Broken store link', ar: 'رابط متجر لا يعمل' },
  { value: 'MISSING_LAPTOP', en: 'Missing laptop model', ar: 'لابتوب غير موجود' },
  { value: 'UI_BUG', en: 'Website / UI bug', ar: 'مشكلة في الموقع' },
  { value: 'OTHER', en: 'Other feedback', ar: 'ملاحظة أخرى' },
]

export const FeedbackModal: React.FC<FeedbackModalProps> = ({ lang }) => {
  const { user, feedbackModalOpen, feedbackInitialTab, feedbackContext, closeFeedbackModal } = useUserSession()
  const isAr = lang === 'ar'

  const [tab, setTab] = useState<'submit' | 'mine'>('submit')
  const [category, setCategory] = useState<FeedbackCategory>('WRONG_PRICE')
  const [reporterEmail, setReporterEmail] = useState('')
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [submitted, setSubmitted] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [myReports, setMyReports] = useState<FeedbackReport[]>([])
  const [loadingMine, setLoadingMine] = useState(false)

  useEffect(() => {
    if (!feedbackModalOpen) {
      setTab('submit')
      setSubmitted(false)
      setError(null)
      setTitle('')
      setDescription('')
      setReporterEmail('')
      return
    }

    setTab(feedbackInitialTab)
    setCategory(feedbackContext?.canonicalId ? 'WRONG_PRICE' : 'UI_BUG')
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') closeFeedbackModal()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [feedbackModalOpen, feedbackInitialTab, feedbackContext, closeFeedbackModal])

  useEffect(() => {
    if (!feedbackModalOpen || tab !== 'mine' || !user) return
    setLoadingMine(true)
    fetchMyFeedback()
      .then(setMyReports)
      .catch(() => setMyReports([]))
      .finally(() => setLoadingMine(false))
  }, [feedbackModalOpen, tab, user])

  if (!feedbackModalOpen) return null

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      await submitFeedback({
        category,
        title: title.trim(),
        description: description.trim(),
        reporterEmail: !user && reporterEmail.trim() ? reporterEmail.trim() : null,
        canonicalId: feedbackContext?.canonicalId ?? null,
        laptopTitleSnapshot: feedbackContext?.laptopTitle ?? null,
        pageUrl: window.location.href,
      })
      setSubmitted(true)
      setTitle('')
      setDescription('')
      setReporterEmail('')
    } catch (err) {
      setError(err instanceof Error ? err.message : isAr ? 'تعذر إرسال البلاغ' : 'Failed to submit feedback')
    } finally {
      setSubmitting(false)
    }
  }

  const statusBadge = (status: string) => {
    switch (status) {
      case 'RESOLVED':
        return 'border-[var(--success)] text-[var(--success)] bg-[var(--success-dim)]'
      case 'IN_REVIEW':
        return 'border-[var(--cyan)] text-[var(--cyan)] bg-[var(--cyan-dim)]'
      case 'DISMISSED':
        return 'border-[var(--border-strong)] text-[var(--text-muted)] bg-[var(--bg-input)]'
      default:
        return 'border-[var(--gold)] text-[var(--gold-bright)] bg-[var(--gold-dim)]'
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 p-4 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-label={isAr ? 'الإبلاغ عن خطأ أو ملاحظة' : 'Report an issue or feedback'}
      onClick={closeFeedbackModal}
    >
      <div
        className="w-full max-w-lg max-h-[90vh] flex flex-col rounded-[14px] border border-[var(--border-strong)] bg-[var(--bg-surface)] shadow-2xl overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-[var(--border-subtle)] bg-[var(--bg-raised)] px-5 py-4">
          <div className="flex items-center gap-2.5">
            <Flag className="w-4 h-4 text-[var(--gold)]" />
            <div>
              <h2 className="font-display text-[16px] font-bold text-[var(--text-primary)]">
                {isAr ? 'إرسال ملاحظة أو بلاغ' : 'Report Issue & Feedback'}
              </h2>
              <p className="text-[11.5px] text-[var(--text-muted)]">
                {isAr
                  ? 'ساعدنا في تصحيح الأسعار أو المواصفات أو تحسين الموقع'
                  : 'Help us fix wrong prices, specs, or site issues'}
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={closeFeedbackModal}
            className="rounded-lg border border-[var(--border-subtle)] p-1.5 text-[var(--text-muted)] hover:border-[var(--border-strong)] hover:text-[var(--text-primary)]"
            aria-label={isAr ? 'إغلاق' : 'Close'}
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {user && (
          <div className="grid grid-cols-2 gap-1.5 border-b border-[var(--border-subtle)] bg-[var(--bg-input)] px-5 py-2.5">
            <button
              type="button"
              onClick={() => setTab('submit')}
              className={`rounded-[7px] py-1.5 text-[12.5px] font-semibold transition-colors ${
                tab === 'submit'
                  ? 'bg-[var(--bg-raised)] text-[var(--gold-bright)] border border-[var(--gold)]'
                  : 'text-[var(--text-muted)] hover:text-[var(--text-primary)]'
              }`}
            >
              {isAr ? 'إرسال بلاغ جديد' : 'Submit Report'}
            </button>
            <button
              type="button"
              onClick={() => setTab('mine')}
              className={`inline-flex items-center justify-center gap-1.5 rounded-[7px] py-1.5 text-[12.5px] font-semibold transition-colors ${
                tab === 'mine'
                  ? 'bg-[var(--bg-raised)] text-[var(--gold-bright)] border border-[var(--gold)]'
                  : 'text-[var(--text-muted)] hover:text-[var(--text-primary)]'
              }`}
            >
              <History className="w-3.5 h-3.5" />
              <span>{isAr ? 'بلاغاتي' : 'My Reports'}</span>
            </button>
          </div>
        )}

        <div className="flex-1 overflow-y-auto p-5">
          {tab === 'submit' ? (
            submitted ? (
              <div className="py-8 text-center space-y-3">
                <CheckCircle className="w-10 h-10 text-[var(--success)] mx-auto" />
                <h3 className="font-display text-[16px] font-bold text-[var(--text-primary)]">
                  {isAr ? 'تم استلام بلاغك بنجاح' : 'Thanks! Your report was submitted'}
                </h3>
                <p className="text-[12.5px] text-[var(--text-secondary)] max-w-sm mx-auto">
                  {user
                    ? isAr
                      ? 'يمكنك متابعة حالة البلاغ ورد الإدارة من تبويب "بلاغاتي".'
                      : 'You can track its status and admin response anytime in "My Reports".'
                    : isAr
                    ? 'شكراً لمساعدتنا في تحسين دقة البيانات.'
                    : 'Thank you for helping keep laptop prices and specs accurate.'}
                </p>
                <div className="flex items-center justify-center gap-2 pt-2">
                  {user && (
                    <button
                      type="button"
                      onClick={() => {
                        setSubmitted(false)
                        setTab('mine')
                      }}
                      className="btn btn-secondary btn-sm"
                    >
                      {isAr ? 'عرض بلاغاتي' : 'View My Reports'}
                    </button>
                  )}
                  <button type="button" onClick={closeFeedbackModal} className="btn btn-primary btn-sm">
                    {isAr ? 'إغلاق' : 'Done'}
                  </button>
                </div>
              </div>
            ) : (
              <form onSubmit={handleSubmit} className="space-y-3.5">
                {feedbackContext?.laptopTitle && (
                  <div className="rounded-[8px] border border-[var(--cyan)] bg-[var(--cyan-dim)] px-3 py-2 text-[12px]">
                    <span className="font-semibold text-[var(--cyan)]">
                      {isAr ? 'بخصوص اللابتوب: ' : 'Regarding laptop: '}
                    </span>
                    <span dir="auto" className="text-[var(--text-primary)] font-medium">
                      {feedbackContext.laptopTitle}
                    </span>
                  </div>
                )}

                {error && (
                  <div className="rounded-[8px] border border-[var(--danger)] bg-[var(--danger-dim)] px-3 py-2 text-[12.5px] text-[var(--danger)]">
                    {error}
                  </div>
                )}

                <div className="space-y-1.5">
                  <label className="block text-[12px] font-medium text-[var(--text-secondary)]">
                    {isAr ? 'نوع المشكلة' : 'Category'}
                  </label>
                  <select
                    value={category}
                    onChange={(e) => setCategory(e.target.value as FeedbackCategory)}
                    className="w-full rounded-[8px] border border-[var(--border-subtle)] bg-[var(--bg-input)] px-3 py-2 text-[13px] text-[var(--text-primary)] focus:border-[var(--gold)] focus:outline-none"
                  >
                    {CATEGORIES.map((c) => (
                      <option key={c.value} value={c.value}>
                        {isAr ? c.ar : c.en}
                      </option>
                    ))}
                  </select>
                </div>

                {!user && (
                  <div className="space-y-1.5">
                    <label className="block text-[12px] font-medium text-[var(--text-secondary)]">
                      {isAr ? 'البريد الإلكتروني (اختياري)' : 'Email (optional)'}
                    </label>
                    <input
                      type="email"
                      dir="ltr"
                      value={reporterEmail}
                      onChange={(e) => setReporterEmail(e.target.value)}
                      placeholder="name@example.com"
                      className="w-full rounded-[8px] border border-[var(--border-subtle)] bg-[var(--bg-input)] px-3 py-2 text-[13px] text-[var(--text-primary)] text-left focus:border-[var(--gold)] focus:outline-none"
                    />
                  </div>
                )}

                <div className="space-y-1.5">
                  <label className="block text-[12px] font-medium text-[var(--text-secondary)]">
                    {isAr ? 'عنوان البلاغ' : 'Summary'}
                  </label>
                  <input
                    type="text"
                    required
                    maxLength={200}
                    value={title}
                    onChange={(e) => setTitle(e.target.value)}
                    placeholder={isAr ? 'مثال: السعر في المتجر مختلف عن المعروض' : 'e.g. Store price is lower than listed'}
                    className="w-full rounded-[8px] border border-[var(--border-subtle)] bg-[var(--bg-input)] px-3 py-2 text-[13px] text-[var(--text-primary)] focus:border-[var(--gold)] focus:outline-none"
                  />
                </div>

                <div className="space-y-1.5">
                  <label className="block text-[12px] font-medium text-[var(--text-secondary)]">
                    {isAr ? 'التفاصيل' : 'Details'}
                  </label>
                  <textarea
                    required
                    rows={4}
                    maxLength={2000}
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                    placeholder={
                      isAr
                        ? 'اكتب تفاصيل الخطأ أو السعر الصحيح أو اسم المتجر...'
                        : 'Share what looks wrong, the expected value, or steps to reproduce...'
                    }
                    className="w-full rounded-[8px] border border-[var(--border-subtle)] bg-[var(--bg-input)] px-3 py-2 text-[13px] text-[var(--text-primary)] focus:border-[var(--gold)] focus:outline-none"
                  />
                </div>

                <button
                  type="submit"
                  disabled={submitting}
                  className="btn btn-primary w-full min-h-[42px] justify-center"
                >
                  <Send className="w-3.5 h-3.5" />
                  <span>
                    {submitting
                      ? isAr
                        ? 'جاري الإرسال...'
                        : 'Submitting...'
                      : isAr
                      ? 'إرسال البلاغ'
                      : 'Submit Feedback'}
                  </span>
                </button>
              </form>
            )
          ) : loadingMine ? (
            <div className="py-10 text-center text-[13px] text-[var(--text-muted)]">
              {isAr ? 'جاري تحميل بلاغاتك...' : 'Loading your reports...'}
            </div>
          ) : myReports.length === 0 ? (
            <div className="rounded-[10px] border border-[var(--border-subtle)] bg-[var(--bg-raised)] p-8 text-center space-y-1.5">
              <p className="text-[14px] font-semibold text-[var(--text-primary)]">
                {isAr ? 'لم ترسل أي بلاغات بعد' : 'No submitted reports yet'}
              </p>
              <p className="text-[12px] text-[var(--text-muted)]">
                {isAr ? 'ستظهر هنا حالة بلاغاتك وملاحظات الإدارة.' : 'Your submitted reports and admin updates will appear here.'}
              </p>
            </div>
          ) : (
            <div className="space-y-3">
              {myReports.map((r) => (
                <div
                  key={r.id}
                  className="rounded-[10px] border border-[var(--border-subtle)] bg-[var(--bg-raised)] p-3.5 space-y-2"
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className={`inline-flex items-center rounded border px-1.5 py-0.5 text-[10px] font-mono font-semibold ${statusBadge(r.status)}`}>
                      {r.status}
                    </span>
                    <span className="text-[11px] font-mono text-[var(--text-muted)]">
                      {r.category}
                    </span>
                  </div>
                  <h4 dir="auto" className="text-[13.5px] font-semibold text-[var(--text-primary)]">
                    {r.title}
                  </h4>
                  {r.laptopTitleSnapshot && (
                    <div className="text-[11.5px] text-[var(--cyan)]">{r.laptopTitleSnapshot}</div>
                  )}
                  <p dir="auto" className="text-[12.5px] text-[var(--text-secondary)]">
                    {r.description}
                  </p>
                  {r.adminNotes && (
                    <div className="rounded-[7px] border border-[var(--border-strong)] bg-[var(--bg-input)] px-3 py-2 text-[12px] text-[var(--text-primary)]">
                      <span className="font-semibold text-[var(--gold)]">
                        {isAr ? 'رد الإدارة: ' : 'Admin note: '}
                      </span>
                      <span dir="auto">{r.adminNotes}</span>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
