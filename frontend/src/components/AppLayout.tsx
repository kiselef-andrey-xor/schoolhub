/** Каркас приложения: боковая навигация (по правам роли), топбар, уведомления, меню профиля. */
import { useEffect, useMemo, useRef, useState } from 'react'
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'

import { notificationsApi } from '@/api/endpoints'
import { qk } from '@/api/query'
import { Avatar, Badge } from '@/components/ui'
import { useToast } from '@/components/Toast'
import { CAP, ROLE_LABEL, can, type Capability } from '@/lib/permissions'
import { relativeTime } from '@/lib/format'
import { authStore, useAuthStore } from '@/store/auth'

interface NavItem {
  to: string
  label: string
  icon: string
  cap?: Capability
  /** пункт виден, если есть ЛЮБАЯ из перечисленных возможностей */
  anyCaps?: Capability[]
  end?: boolean
  group: string
}

const NAV: NavItem[] = [
  { to: '/', label: 'Дашборд', icon: '📊', group: 'Обзор', end: true },
  { to: '/orders', label: 'Приказы', icon: '📜', group: 'Документы', cap: CAP.ordersRead },
  // ВАЖНО: «Задачи» видны всем ролям — у учителя tasks:read-own, у администрации/владельца tasks:read-all
  { to: '/tasks', label: 'Задачи', icon: '✅', group: 'Работа', anyCaps: [CAP.tasksReadOwn, CAP.tasksReadAll] },
  { to: '/plans', label: 'План работы', icon: '🗓', group: 'Работа', cap: CAP.plansRead },
  { to: '/notifications', label: 'Уведомления', icon: '🔔', group: 'Работа' },
  { to: '/users', label: 'Пользователи', icon: '👥', group: 'Администрирование', cap: CAP.usersRead },
  { to: '/audit', label: 'Журнал событий', icon: '🧾', group: 'Администрирование', cap: CAP.auditRead },
  { to: '/profile', label: 'Мой профиль', icon: '🪪', group: 'Аккаунт' },
]

const TITLES: Record<string, string> = {
  '/': 'Дашборд',
  '/orders': 'Приказы',
  '/tasks': 'Задачи',
  '/plans': 'План работы',
  '/notifications': 'Уведомления',
  '/users': 'Пользователи',
  '/audit': 'Журнал событий',
  '/profile': 'Мой профиль',
}

export function AppLayout() {
  const user = useAuthStore((s) => s.user)
  const navigate = useNavigate()
  const location = useLocation()
  const toast = useToast()
  const qc = useQueryClient()
  const [menuOpen, setMenuOpen] = useState(false)
  const [bellOpen, setBellOpen] = useState(false)
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const menuRef = useRef<HTMLDivElement>(null)
  const bellRef = useRef<HTMLDivElement>(null)

  const authed = user !== null

  // счётчик непрочитанных: лёгкий поллинг, чтобы бейдж «оживал» без перезагрузки
  const { data: unread = 0 } = useQuery({
    queryKey: qk('/notifications/unread-count'),
    queryFn: () => notificationsApi.unreadCount().then((r) => r.unread),
    enabled: authed,
    refetchInterval: 45_000,
  })

  // последние уведомления — подгружаем только когда колокольчик открыт
  const { data: latest = [] } = useQuery({
    queryKey: qk('/notifications/latest'),
    queryFn: () => notificationsApi.list({ per_page: 6 }).then((r) => r.items),
    enabled: authed && bellOpen,
    refetchInterval: bellOpen ? 30_000 : false,
  })

  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setMenuOpen(false)
      if (bellRef.current && !bellRef.current.contains(e.target as Node)) setBellOpen(false)
    }
    document.addEventListener('mousedown', onClick)
    return () => document.removeEventListener('mousedown', onClick)
  }, [])

  useEffect(() => setSidebarOpen(false), [location.pathname])

  const items = useMemo(
    () =>
      user
        ? NAV.filter((item) => {
            // пункт виден, если достаточно ЛЮБОЙ из перечисленных возможностей:
            // «Задачи» есть у всех ролей — у учителя tasks:read-own, у администрации tasks:read-all
            if (item.anyCaps) return item.anyCaps.some((c) => can(user.capabilities, c))
            return !item.cap || can(user.capabilities, item.cap)
          })
        : [],
    [user],
  )

  const title = useMemo(() => {
    const path = location.pathname
    if (path.startsWith('/orders/')) return 'Приказ'
    if (path.startsWith('/tasks/')) return 'Задача'
    if (path.startsWith('/plans/')) return path.endsWith('/edit') ? 'Редактор плана' : 'План работы на неделю'
    return TITLES[path] ?? 'SchoolHub'
  }, [location.pathname])

  if (!user) return null

  const groups = Array.from(new Set(items.map((i) => i.group)))

  return (
    <div className="app-shell">
      <aside className={sidebarOpen ? 'sidebar sidebar--open' : 'sidebar'}>
        <div className="sidebar__brand">
          <div className="sidebar__logo">SH</div>
          <div>
            <div className="sidebar__title">SchoolHub</div>
            <div className="sidebar__subtitle">цифровая среда школы</div>
          </div>
        </div>

        <nav className="sidebar__nav">
          {groups.map((group) => (
            <div key={group}>
              <div className="sidebar__group">{group}</div>
              {items
                .filter((i) => i.group === group)
                .map((item) => (
                  <NavLink
                    key={item.to}
                    to={item.to}
                    end={item.end}
                    className={({ isActive }) => (isActive ? 'nav-link nav-link--active' : 'nav-link')}
                  >
                    <span className="nav-link__icon" aria-hidden>{item.icon}</span>
                    <span>{item.label}</span>
                    {item.to === '/notifications' && unread > 0 ? (
                      <span className="nav-link__badge">{unread > 99 ? '99+' : unread}</span>
                    ) : null}
                  </NavLink>
                ))}
            </div>
          ))}
        </nav>

        <div className="sidebar__footer">
          <div className="user-chip" style={{ color: '#dfe7f5' }}>
            <Avatar name={user.full_name} />
            <div style={{ minWidth: 0 }}>
              <div className="user-chip__name" style={{ color: '#fff' }}>{user.full_name}</div>
              <div className="user-chip__role" style={{ color: '#9fb2d4' }}>{ROLE_LABEL[user.role]}</div>
            </div>
          </div>
        </div>
      </aside>

      <div className="main">
        <header className="topbar">
          <button className="btn btn--ghost btn--icon burger" onClick={() => setSidebarOpen((v) => !v)} aria-label="Меню">
            ☰
          </button>
          <div className="topbar__title">{title}</div>
          <div className="topbar__spacer" />

          <div className="menu" ref={bellRef}>
            <button className="btn btn--ghost row" onClick={() => setBellOpen((v) => !v)} aria-label="Уведомления">
              <span aria-hidden>🔔</span>
              {unread > 0 && <Badge tone="danger">{unread}</Badge>}
            </button>
            {bellOpen && (
              <div className="menu__panel" style={{ minWidth: 330 }}>
                <div className="row row--between" style={{ padding: '4px 8px 8px' }}>
                  <strong className="small">Последние уведомления</strong>
                  <button
                    className="btn btn--sm btn--ghost"
                    onClick={async () => {
                      try {
                        await notificationsApi.markAllRead()
                        void qc.invalidateQueries({ queryKey: ['notifications'] })
                        void qc.invalidateQueries({ queryKey: qk('/notifications/unread-count') })
                        toast.success('Все уведомления отмечены прочитанными')
                      } catch (e) {
                        toast.error(e)
                      }
                    }}
                  >
                    Прочитать все
                  </button>
                </div>
                {latest.length === 0 ? (
                  <div className="small muted" style={{ padding: '10px 8px' }}>Уведомлений пока нет</div>
                ) : (
                  latest.slice(0, 6).map((n) => (
                    <button
                      key={n.id}
                      className="menu__item"
                      style={{ flexDirection: 'column', alignItems: 'flex-start', gap: 2 }}
                      onClick={() => {
                        setBellOpen(false)
                        if (n.entity_type === 'task') navigate(`/tasks/${n.entity_id}`)
                        else if (n.entity_type === 'order') navigate(`/orders/${n.entity_id}`)
                        else navigate('/notifications')
                      }}
                    >
                      <span style={{ fontWeight: n.is_read ? 500 : 700 }}>{n.title}</span>
                      <span className="tiny muted">{relativeTime(n.created_at)}</span>
                    </button>
                  ))
                )}
                <div className="menu__sep" />
                <button className="menu__item" onClick={() => { setBellOpen(false); navigate('/notifications') }}>
                  Все уведомления →
                </button>
              </div>
            )}
          </div>

          <div className="menu" ref={menuRef}>
            <button className="btn btn--ghost row" onClick={() => setMenuOpen((v) => !v)}>
              <Avatar name={user.full_name} size="sm" />
              <span className="nowrap">{user.full_name.split(' ')[0]}</span>
              <span aria-hidden>▾</span>
            </button>
            {menuOpen && (
              <div className="menu__panel">
                <div style={{ padding: '8px 10px' }}>
                  <div className="strong">{user.full_name}</div>
                  <div className="tiny muted">{user.email}</div>
                  <div style={{ marginTop: 6 }}>
                    <Badge tone="brand">{ROLE_LABEL[user.role]}</Badge>
                  </div>
                </div>
                <div className="menu__sep" />
                <button className="menu__item" onClick={() => { setMenuOpen(false); navigate('/profile') }}>
                  🪪 Мой профиль
                </button>
                <button
                  className="menu__item"
                  onClick={async () => {
                    setMenuOpen(false)
                    await authStore.logout()
                    navigate('/login', { replace: true })
                  }}
                >
                  🚪 Выйти
                </button>
              </div>
            )}
          </div>
        </header>

        <main className="content">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
