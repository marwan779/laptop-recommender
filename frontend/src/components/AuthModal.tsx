import React, { useEffect, useState } from 'react'
import { X, Lock, Mail, User as UserIcon } from 'lucide-react'
import { loginUser, registerUser } from '../services/usersApi'
import { useUserSession } from '../context/UserSessionContext'

interface AuthModalProps {
  lang: 'ar' | 'en'
}

export const AuthModal: React.FC<AuthModalProps> = ({ lang }) => {
  const { authModalOpen, setAuthModalOpen, handleAuthSuccess } = useUserSession()
  const isAr = lang === 'ar'

  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [email, setEmail] = useState('')
  const [fullName, setFullName] = useState('')
  const [password, setPassword] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!authModalOpen) {
      setMode('login')
      setEmail('')
      setFullName('')
      setPassword('')
      setError(null)
    }
  }, [authModalOpen])

  if (!authModalOpen) return null

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      const auth =
        mode === 'login'
          ? await loginUser({ email: email.trim(), password })
          : await registerUser({
              email: email.trim(),
              fullName: fullName.trim(),
              password,
              preferredLanguage: lang,
            })
      await handleAuthSuccess(auth)
      setPassword('')
    } catch (err) {
      setError(err instanceof Error ? err.message : isAr ? 'حدث خطأ غير متوقع' : 'Authentication failed')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 p-4 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-label={isAr ? 'تسجيل الدخول أو إنشاء حساب' : 'Sign in or create account'}
      onClick={() => setAuthModalOpen(false)}
    >
      <div
        className="w-full max-w-md rounded-[14px] border border-[var(--border-strong)] bg-[var(--bg-surface)] shadow-2xl overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-[var(--border-subtle)] bg-[var(--bg-raised)] px-5 py-4">
          <div>
            <h2 className="font-display text-[17px] font-bold text-[var(--text-primary)]">
              {mode === 'login'
                ? isAr
                  ? 'تسجيل الدخول'
                  : 'Sign In'
                : isAr
                ? 'إنشاء حساب جديد'
                : 'Create Account'}
            </h2>
            <p className="text-[12px] text-[var(--text-muted)]">
              {isAr
                ? 'احفظ اللابتوبات وتابع تنبيهات انخفاض الأسعار'
                : 'Save laptops and get notified on price drops & restocks'}
            </p>
          </div>
          <button
            type="button"
            onClick={() => setAuthModalOpen(false)}
            className="rounded-lg border border-[var(--border-subtle)] p-1.5 text-[var(--text-muted)] hover:border-[var(--border-strong)] hover:text-[var(--text-primary)]"
            aria-label={isAr ? 'إغلاق' : 'Close'}
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="p-5 space-y-4">
          {/* Mode Switch */}
          <div className="grid grid-cols-2 gap-1.5 rounded-[10px] border border-[var(--border-subtle)] bg-[var(--bg-input)] p-1">
            <button
              type="button"
              onClick={() => {
                setMode('login')
                setError(null)
              }}
              className={`rounded-[7px] py-2 text-[13px] font-semibold transition-colors ${
                mode === 'login'
                  ? 'bg-[var(--bg-raised)] text-[var(--gold-bright)] border border-[var(--gold)]'
                  : 'text-[var(--text-muted)] hover:text-[var(--text-primary)]'
              }`}
            >
              {isAr ? 'دخول' : 'Sign In'}
            </button>
            <button
              type="button"
              onClick={() => {
                setMode('register')
                setError(null)
              }}
              className={`rounded-[7px] py-2 text-[13px] font-semibold transition-colors ${
                mode === 'register'
                  ? 'bg-[var(--bg-raised)] text-[var(--gold-bright)] border border-[var(--gold)]'
                  : 'text-[var(--text-muted)] hover:text-[var(--text-primary)]'
              }`}
            >
              {isAr ? 'حساب جديد' : 'Register'}
            </button>
          </div>

          {error && (
            <div className="rounded-[8px] border border-[var(--danger)] bg-[var(--danger-dim)] px-3 py-2 text-[12.5px] text-[var(--danger)]">
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-3.5">
            {mode === 'register' && (
              <div className="space-y-1.5">
                <label className="block text-[12px] font-medium text-[var(--text-secondary)]">
                  {isAr ? 'الاسم الكامل' : 'Full Name'}
                </label>
                <div className="relative">
                  <UserIcon className="w-4 h-4 text-[var(--text-muted)] absolute top-1/2 -translate-y-1/2 start-3" />
                  <input
                    type="text"
                    required
                    value={fullName}
                    onChange={(e) => setFullName(e.target.value)}
                    placeholder={isAr ? 'أحمد محمد' : 'Ahmed Mohamed'}
                    className="w-full rounded-[8px] border border-[var(--border-subtle)] bg-[var(--bg-input)] ps-9 pe-3 py-2.5 text-[13.5px] text-[var(--text-primary)] focus:border-[var(--gold)] focus:outline-none"
                  />
                </div>
              </div>
            )}

            <div className="space-y-1.5">
              <label className="block text-[12px] font-medium text-[var(--text-secondary)]">
                {isAr ? 'البريد الإلكتروني' : 'Email'}
              </label>
              <div className="relative" dir="ltr">
                <Mail className="w-4 h-4 text-[var(--text-muted)] absolute top-1/2 -translate-y-1/2 left-3" />
                <input
                  type="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="name@example.com"
                  className="w-full rounded-[8px] border border-[var(--border-subtle)] bg-[var(--bg-input)] pl-9 pr-3 py-2.5 text-[13.5px] text-[var(--text-primary)] text-left focus:border-[var(--gold)] focus:outline-none"
                />
              </div>
            </div>

            <div className="space-y-1.5">
              <label className="block text-[12px] font-medium text-[var(--text-secondary)]">
                {isAr ? 'كلمة المرور' : 'Password'}
              </label>
              <div className="relative" dir="ltr">
                <Lock className="w-4 h-4 text-[var(--text-muted)] absolute top-1/2 -translate-y-1/2 left-3" />
                <input
                  type="password"
                  required
                  minLength={8}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••"
                  className="w-full rounded-[8px] border border-[var(--border-subtle)] bg-[var(--bg-input)] pl-9 pr-3 py-2.5 text-[13.5px] text-[var(--text-primary)] text-left focus:border-[var(--gold)] focus:outline-none"
                />
              </div>
            </div>

            <button
              type="submit"
              disabled={submitting}
              className="btn btn-primary w-full min-h-[42px] justify-center"
            >
              {submitting
                ? isAr
                  ? 'جاري المعالجة...'
                  : 'Please wait...'
                : mode === 'login'
                ? isAr
                  ? 'دخول'
                  : 'Sign In'
                : isAr
                ? 'إنشاء الحساب'
                : 'Create Account'}
            </button>
          </form>
        </div>
      </div>
    </div>
  )
}
