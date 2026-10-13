/** Пользователи (OWNER/ADMIN): создание, смена роли, блокировка, сброс пароля. */
import { useMemo, useState, type FormEvent } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'

import { authApi, usersApi } from '@/api/endpoints'
import { qk } from '@/api/query'
import { ADImportModal } from '@/components/ADImportModal'
import { Modal } from '@/components/Modal'
import {
  Avatar,
  Badge,
  EmptyState,
  ErrorState,
  Pagination,
  RoleBadge,
  Spinner,
} from '@/components/ui'
import { useToast } from '@/components/Toast'
import { CAP, can, canManageRole } from '@/lib/permissions'
import { ROLE_LABEL_FULL, formatDate, formatDateTime } from '@/lib/format'
import { useAuthStore } from '@/store/auth'
import type { Role, User } from '@/types'

const PER_PAGE = 20
const ROLES: Role[] = ['OWNER', 'ADMIN', 'TEACHER']

interface FormState {
  id?: string
  email: string
  full_name: string
  position: string
  phone: string
  role: Role
  is_active: boolean
  password: string
}

const emptyForm = (actorRole: Role): FormState => ({
  email: '',
  full_name: '',
  position: '',
  phone: '',
  role: actorRole === 'OWNER' ? 'ADMIN' : 'TEACHER',
  is_active: true,
  password: '',
})

export function UsersPage() {
  const me = useAuthStore((s) => s.user)!
  const toast = useToast()
  const qc = useQueryClient()
  const canManage = can(me.capabilities, CAP.usersManage)

  const [search, setSearch] = useState('')
  const [debounced, setDebounced] = useState('')
  const [role, setRole] = useState<Role | ''>('')
  const [page, setPage] = useState(1)
  const [form, setForm] = useState<FormState | null>(null)
  const [adOpen, setAdOpen] = useState(false)
  const [busy, setBusy] = useState(false)

  const params = useMemo(
    () => ({ search: debounced || undefined, role: role || undefined, page, per_page: PER_PAGE }),
    [debounced, role, page],
  )

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: qk('/users', params as never),
    queryFn: () => usersApi.list(params),
  })

  const invalidate = () => {
    void qc.invalidateQueries({ queryKey: ['/users'] })
    void qc.invalidateQueries({ queryKey: ['/dashboard'] })
  }

  async function submit(e: FormEvent) {
    e.preventDefault()
    if (!form) return
    setBusy(true)
    try {
      if (form.id) {
        const payload: Record<string, unknown> = {
          full_name: form.full_name.trim(),
          position: form.position.trim() || null,
          phone: form.phone.trim() || null,
          email: form.email.trim().toLowerCase(),
          role: form.role,
          is_active: form.is_active,
        }
        if (form.password.trim()) payload.password = form.password.trim()
        await usersApi.update(form.id, payload as never)
        toast.success('Данные сотрудника обновлены')
      } else {
        await usersApi.create({
          email: form.email.trim().toLowerCase(),
          password: form.password,
          full_name: form.full_name.trim(),
          role: form.role,
          position: form.position.trim() || undefined,
          phone: form.phone.trim() || undefined,
        })
        toast.success('Учётная запись создана')
      }
      setForm(null)
      invalidate()
      void refetch()
    } catch (err) {
      toast.error(err)
    } finally {
      setBusy(false)
    }
  }

  async function deactivate(u: User) {
    if (!window.confirm(`Заблокировать учётную запись ${u.full_name}? Доступ к системе будет закрыт, история сохранится.`)) return
    try {
      await usersApi.deactivate(u.id)
      toast.success('Учётная запись заблокирована')
      invalidate()
      void refetch()
    } catch (err) {
      toast.error(err)
    }
  }

  const editing = form?.id ? data?.items.find((u) => u.id === form.id) ?? null : null
  const selfEdit = form?.id === me.id

  return (
    <div className="stack" style={{ gap: 16 }}>
      <div className="page-head">
        <div className="page-head__text">
          <h1>Пользователи</h1>
          <div className="page-head__hint">
            {me.role === 'OWNER'
              ? 'Полное управление доступом: роли, блокировки, сброс паролей.'
              : 'Сотрудники школы. Назначайте задачи и управляйте учётными записями учителей.'}
          </div>
        </div>
        <div className="page-head__actions">
          {canManage && (
            <button className="btn" onClick={() => setAdOpen(true)} title="Найти сотрудников в каталоге домена и завести им учётки">
              🌐 Импорт из AD
            </button>
          )}
          {canManage && (
            <button className="btn btn--primary" onClick={() => setForm(emptyForm(me.role))}>
              + Локальная учётка
            </button>
          )}
        </div>
      </div>

      <section className="card">
        <div className="card__body">
          <div className="filters">
            <label className="field field--grow">
              <span className="field__label">Поиск</span>
              <input
                className="input"
                value={search}
                onChange={(e) => { setSearch(e.target.value); setPage(1) }}
                onBlur={() => setDebounced(search)}
                onKeyDown={(e) => { if (e.key === 'Enter') { setDebounced(search); setPage(1) } }}
                placeholder="ФИО, e-mail или должность…"
              />
            </label>
            <label className="field">
              <span className="field__label">Роль</span>
              <select className="select" value={role} onChange={(e) => { setRole(e.target.value as Role | ''); setPage(1) }}>
                <option value="">Все роли</option>
                {ROLES.filter((r) => me.role === 'OWNER' || r !== 'OWNER').map((r) => (
                  <option key={r} value={r}>{ROLE_LABEL_FULL[r]}</option>
                ))}
              </select>
            </label>
          </div>
        </div>
      </section>

      <section className="card">
        {isLoading ? (
          <Spinner label="Загружаем список сотрудников…" />
        ) : error ? (
          <ErrorState error={error} onRetry={() => void refetch()} />
        ) : !data || data.items.length === 0 ? (
          <EmptyState icon="👥" title="Никого не найдено" hint="Измените условия поиска" />
        ) : (
          <>
            <table className="table">
              <thead>
                <tr>
                  <th>Сотрудник</th>
                  <th style={{ width: 220 }}>Должность</th>
                  <th style={{ width: 150 }}>Роль</th>
                  <th style={{ width: 130 }}>Статус</th>
                  <th style={{ width: 160 }}>Последний вход</th>
                  <th style={{ width: 130 }} />
                </tr>
              </thead>
              <tbody>
                {data.items.map((u) => (
                  <tr key={u.id}>
                    <td>
                      <div className="user-chip">
                        <Avatar name={u.full_name} />
                        <div>
                          <div className="user-chip__name">
                            {u.full_name}
                            {u.id === me.id && <Badge tone="brand">это вы</Badge>}
                          </div>
                          <div className="tiny muted">{u.email}</div>
                        </div>
                      </div>
                    </td>
                    <td className="small">{u.position ?? '—'}</td>
                    <td><RoleBadge role={u.role} /></td>
                    <td>
                      {u.is_active ? <Badge tone="ok" dot>Активен</Badge> : <Badge tone="muted" dot>Заблокирован</Badge>}
                    </td>
                    <td className="small nowrap">
                      {u.last_login_at ? formatDateTime(u.last_login_at) : 'не входил'}
                      <div className="tiny muted">создан {formatDate(u.created_at)}</div>
                    </td>
                    <td>
                      <div className="row" style={{ gap: 6, justifyContent: 'flex-end' }}>
                        {canManage && (
                          <button
                            className="btn btn--sm"
                            disabled={!canManageRole(me.role, u.role) && u.id !== me.id}
                            onClick={() =>
                              setForm({
                                id: u.id,
                                email: u.email,
                                full_name: u.full_name,
                                position: u.position ?? '',
                                phone: u.phone ?? '',
                                role: u.role,
                                is_active: u.is_active,
                                password: '',
                              })
                            }
                          >
                            ✎ Изменить
                          </button>
                        )}
                        {me.role === 'OWNER' && u.id !== me.id && u.is_active && (
                          <button className="btn btn--sm btn--danger" onClick={() => void deactivate(u)}>
                            Заблокировать
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <Pagination page={data.page} pages={data.pages} total={data.total} perPage={data.per_page} onPage={setPage} />
          </>
        )}
      </section>

      {me.role === 'OWNER' && <ADDiagnostics />}

      <ADImportModal
        open={adOpen}
        actorRole={me.role}
        onClose={() => setAdOpen(false)}
        onDone={() => { invalidate(); void refetch() }}
      />

      <Modal
        open={form !== null}
        onClose={() => setForm(null)}
        title={form?.id ? 'Редактирование сотрудника' : 'Новая локальная учётка'}
        footer={
          <>
            <button className="btn" onClick={() => setForm(null)} disabled={busy}>Отмена</button>
            <button className="btn btn--primary" form="user-form" type="submit" disabled={busy}>
              {busy ? 'Сохраняем…' : 'Сохранить'}
            </button>
          </>
        }
      >
        {form && (
          <form id="user-form" onSubmit={submit} className="stack" style={{ gap: 14 }}>
            <div className="form-grid">
              <label className="field">
                <span className="field__label">ФИО *</span>
                <input className="input" required value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} />
              </label>
              <label className="field">
                <span className="field__label">E-mail *</span>
                <input className="input" type="email" required value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
              </label>
              <label className="field">
                <span className="field__label">Должность</span>
                <input className="input" value={form.position} onChange={(e) => setForm({ ...form, position: e.target.value })} placeholder="Учитель математики" />
              </label>
              <label className="field">
                <span className="field__label">Телефон</span>
                <input className="input" value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} placeholder="+7 …" />
              </label>
              <label className="field">
                <span className="field__label">Роль *</span>
                <select
                  className="select"
                  value={form.role}
                  disabled={selfEdit}
                  onChange={(e) => setForm({ ...form, role: e.target.value as Role })}
                >
                  {ROLES.filter((r) => canManageRole(me.role, r) || r === form.role).map((r) => (
                    <option key={r} value={r}>{ROLE_LABEL_FULL[r]}</option>
                  ))}
                </select>
                <span className="field__hint">
                  {me.role === 'OWNER'
                    ? 'Владелец может назначать любую роль'
                    : 'Администрация назначает только роль «Учитель»'}
                </span>
              </label>
              {editing?.auth_source === 'ldap' ? (
                <div className="field">
                  <span className="field__label">Пароль</span>
                  <div className="alert alert--info small">
                    Учётная запись домена: пароль меняется в Active Directory
                    {editing.domain_account ? ` (${editing.domain_account})` : ''}.
                  </div>
                </div>
              ) : (
                <label className="field">
                  <span className="field__label">{form.id ? 'Новый пароль (необязательно)' : 'Пароль *'}</span>
                  <input
                    className="input"
                    type="password"
                    minLength={8}
                    required={!form.id}
                    value={form.password}
                    onChange={(e) => setForm({ ...form, password: e.target.value })}
                    placeholder={form.id ? 'оставьте пустым, чтобы не менять' : 'минимум 8 символов'}
                  />
                  {!form.id && (
                    <span className="field__hint">
                      Локальная учётка — запасной вход, если контроллер домена недоступен
                    </span>
                  )}
                </label>
              )}
            </div>

            {form.id && !selfEdit && (
              <label className="row small" style={{ gap: 8 }}>
                <input type="checkbox" checked={form.is_active} onChange={(e) => setForm({ ...form, is_active: e.target.checked })} />
                Учётная запись активна (снимите, чтобы заблокировать доступ)
              </label>
            )}

            {editing && (
              <div className="alert alert--info small">
                Текущая роль: {ROLE_LABEL_FULL[editing.role]}. Последний вход:{' '}
                {editing.last_login_at ? formatDateTime(editing.last_login_at) : 'не входил'}.
              </div>
            )}
            {selfEdit && (
              <div className="alert alert--warn small">
                Собственную роль и активность изменить нельзя — это защита от случайной потери доступа к управлению школой.
              </div>
            )}
          </form>
        )}
      </Modal>
    </div>
  )
}


/** Панель диагностики подключения к Active Directory (только Владелец). */
function ADDiagnostics() {
  const { data, isLoading, refetch, isFetching } = useQuery({
    queryKey: qk('/auth/ad/diagnostics'),
    queryFn: authApi.adDiagnostics,
  })
  const [open, setOpen] = useState(false)

  if (isLoading) return null
  const diag = data as
    | { enabled?: boolean; hint?: string; config?: Record<string, unknown>; problems?: string[]; ping?: Record<string, unknown> }
    | undefined

  if (!diag) return null
  if (diag.enabled === false) {
    return (
      <section className="card">
        <div className="card__body">
          <div className="alert alert--warn small">
            <strong>Active Directory не включена.</strong> {diag.hint ?? 'Установите LDAP_ENABLED=true в .env'} —
            сейчас доступен только вход по локальным учётным записям SchoolHub.
          </div>
        </div>
      </section>
    )
  }

  const problems = diag.problems ?? []
  const ping = (diag.ping ?? {}) as { ok?: boolean; error?: string; server?: string; skipped?: boolean }

  return (
    <section className="card">
      <header className="card__head">
        <h3>Диагностика Active Directory</h3>
        <span className="grow" />
        {ping.ok ? (
          <Badge tone="ok" dot>DC отвечает</Badge>
        ) : ping.skipped ? (
          <Badge tone="warn" dot>не проверялось</Badge>
        ) : (
          <Badge tone="danger" dot>нет связи с DC</Badge>
        )}
        <button className="btn btn--sm" onClick={() => void refetch()} disabled={isFetching}>
          {isFetching ? 'Проверяем…' : '↻ Проверить'}
        </button>
        <button className="btn btn--sm btn--ghost" onClick={() => setOpen((v) => !v)}>
          {open ? 'Скрыть детали' : 'Детали'}
        </button>
      </header>
      <div className="card__body stack" style={{ gap: 10 }}>
        {problems.length > 0 && (
          <div className="alert alert--error small">
            <strong>Требуется настройка:</strong>
            <ul style={{ margin: '6px 0 0 18px', padding: 0 }}>
              {problems.map((p) => (
                <li key={p}>{p}</li>
              ))}
            </ul>
          </div>
        )}
        {ping.ok === false && ping.error && <div className="alert alert--error small">Ответ каталога: {ping.error}</div>}
        {problems.length === 0 && ping.ok && (
          <div className="alert alert--info small">
            Конфигурация корректна, контроллер домена доступен. Сотрудники могут входить под доменными учётками.
          </div>
        )}

        {open && (
          <pre className="mono" style={{ background: 'var(--surface-2)', padding: 12, borderRadius: 8, overflow: 'auto', maxHeight: 320 }}>
            {JSON.stringify({ config: diag.config, ping: diag.ping }, null, 2)}
          </pre>
        )}
      </div>
    </section>
  )
}
