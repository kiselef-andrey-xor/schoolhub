import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'

import { dashboardApi } from '@/api/endpoints'
import { qk } from '@/api/query'
import {
  AckBadge,
  Badge,
  EmptyState,
  ErrorState,
  Kpi,
  Section,
  Spinner,
  TaskStatusBadge,
} from '@/components/ui'
import { CAP, ROLE_LABEL, can } from '@/lib/permissions'
import { PLAN_STATUS_LABEL, deadlineLabel, formatDate, formatWeekRange, plural, relativeTime } from '@/lib/format'
import { useAuthStore } from '@/store/auth'

export function DashboardPage() {
  const user = useAuthStore((s) => s.user)!
  const isStaff = can(user.capabilities, CAP.dashboardGlobal)

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: qk('/dashboard'),
    queryFn: dashboardApi.summary,
    refetchInterval: 60_000,
  })

  if (isLoading) return <Spinner large label="Собираем сводку…" />
  if (error) return <ErrorState error={error} onRetry={() => void refetch()} />
  if (!data) return null

  const { summary, pending_acks, my_tasks, recent_orders, recent_tasks, current_plan } = data

  return (
    <div className="stack" style={{ gap: 16 }}>
      <div className="page-head">
        <div className="page-head__text">
          <h1>Здравствуйте, {user.full_name.split(' ').slice(0, 2).join(' ')}</h1>
          <div className="page-head__hint">
            {ROLE_LABEL[user.role]}
            {user.position ? ` · ${user.position}` : ''} · {isStaff ? 'сводка по всей школе' : 'ваша личная сводка'}
          </div>
        </div>
        <div className="page-head__actions">
          <Link className="btn" to="/orders">📜 Приказы</Link>
          <Link className="btn" to="/tasks">✅ Задачи</Link>
          <Link className="btn" to="/plans">🗓 План работы</Link>
        </div>
      </div>

      <div className="grid grid--kpi">
        <Kpi
          label={isStaff ? 'Приказов опубликовано' : 'Приказов доступно'}
          value={isStaff ? summary.orders.published : summary.orders.total}
          note={isStaff ? `всего в системе ${summary.orders.total}` : 'только опубликованные'}
          tone="brand"
        />
        <Kpi
          label={isStaff ? 'Ждут ознакомления' : 'Нужно ознакомиться'}
          value={summary.orders.pending_ack}
          note={isStaff ? 'подписей по всем приказам' : plural(summary.orders.pending_ack, 'приказ', 'приказа', 'приказов')}
          tone={summary.orders.pending_ack > 0 ? 'warn' : 'ok'}
        />
        <Kpi
          label={isStaff ? 'Задач в работе' : 'Мои задачи в работе'}
          value={summary.tasks.in_progress + summary.tasks.new}
          note={`новых: ${summary.tasks.new}, в работе: ${summary.tasks.in_progress}`}
        />
        <Kpi
          label="Просрочено"
          value={summary.tasks.overdue}
          note={summary.tasks.overdue ? 'требуется реакция' : 'просрочек нет'}
          tone={summary.tasks.overdue > 0 ? 'danger' : 'ok'}
        />
        {isStaff && summary.users && (
          <Kpi
            label="Сотрудников"
            value={summary.users.total}
            note={`учителей: ${summary.users.teachers} · администрация: ${summary.users.admins} · активных: ${summary.users.active}`}
          />
        )}
      </div>

      <div className="grid grid--2">
        <Section
          title={isStaff ? 'Ознакомление идёт' : 'Требуется ваше ознакомление'}
          actions={<Link className="btn btn--sm" to="/orders?mine_pending=true">Все приказы →</Link>}
          flush
        >
          {pending_acks.length === 0 ? (
            <EmptyState
              icon="🎉"
              title={isStaff ? 'Все подписи собраны' : 'Всё прочитано'}
              hint={isStaff ? 'Нет приказов, ожидающих ознакомления' : 'Новых приказов на ознакомление нет'}
            />
          ) : (
            pending_acks.map((o) => (
              <Link key={o.id} to={`/orders/${o.id}`} className="list-item" style={{ color: 'inherit' }}>
                <div className="list-item__main">
                  <div className="list-item__title">
                    №{o.number} · {o.title}
                  </div>
                  <div className="list-item__meta">
                    <span>от {formatDate(o.issued_on)}</span>
                    {o.ack_deadline && <span>ознакомиться до {formatDate(o.ack_deadline)}</span>}
                    {isStaff && (
                      <span>
                        подписей {o.ack_done}/{o.ack_total}
                      </span>
                    )}
                  </div>
                </div>
                <div className="list-item__actions">
                  <AckBadge status={o.my_ack?.status} />
                </div>
              </Link>
            ))
          )}
        </Section>

        <Section
          title={isStaff ? 'Просроченные и ближайшие задачи' : 'Мои ближайшие задачи'}
          actions={<Link className="btn btn--sm" to="/tasks">Все задачи →</Link>}
          flush
        >
          {my_tasks.length === 0 ? (
            <EmptyState icon="🌤" title="Задач нет" hint={isStaff ? 'Просроченных задач не найдено' : 'Вам пока ничего не назначено'} />
          ) : (
            my_tasks.map((t) => (
              <Link key={t.id} to={`/tasks/${t.id}`} className="list-item" style={{ color: 'inherit' }}>
                <div className="list-item__main">
                  <div className="list-item__title">{t.title}</div>
                  <div className="list-item__meta">
                    <span>{deadlineLabel(t.deadline, t.status === 'DONE')}</span>
                    {isStaff && t.assignees.length > 0 && (
                      <span>· {t.assignees.map((a) => a.user.full_name).join(', ')}{t.assignees.length > 1 ? ` (${t.marks_done}/${t.assignees.length} ✓)` : ''}</span>
                    )}
                  </div>
                </div>
                <div className="list-item__actions">
                  <TaskStatusBadge status={t.effective_status} />
                </div>
              </Link>
            ))
          )}
        </Section>
      </div>

      {current_plan && (
        <Section
          title="План работы на неделю"
          actions={<Link className="btn btn--sm" to="/plans">Все планы →</Link>}
          flush
        >
          <Link to={`/plans/${current_plan.id}`} className="list-item" style={{ color: 'inherit' }}>
            <div style={{ fontSize: 22 }}>🗓</div>
            <div className="list-item__main">
              <div className="list-item__title">
                {formatWeekRange(current_plan.week_start, current_plan.week_end)}
                {current_plan.content.duty.klass && ` · дежурный класс ${current_plan.content.duty.klass}`}
              </div>
              <div className="list-item__meta">
                <span>мероприятий: {current_plan.events_total}</span>
                <span>ответственных: {current_plan.responsibles_total}</span>
                {current_plan.my_items > 0 && (
                  <span className="strong" style={{ color: 'var(--brand-700)' }}>
                    вы отвечаете за {current_plan.my_items} {plural(current_plan.my_items, 'пункт', 'пункта', 'пунктов')}
                  </span>
                )}
              </div>
            </div>
            <div className="list-item__actions">
              <Badge tone={current_plan.status === 'PUBLISHED' ? 'ok' : 'warn'} dot>
                {PLAN_STATUS_LABEL[current_plan.status]}
              </Badge>
            </div>
          </Link>
        </Section>
      )}

      <div className="grid grid--2">
        <Section title="Последние приказы" actions={<Link className="btn btn--sm" to="/orders">Открыть →</Link>} flush>
          {recent_orders.length === 0 ? (
            <EmptyState icon="📜" title="Приказов пока нет" />
          ) : (
            recent_orders.map((o) => (
              <Link key={o.id} to={`/orders/${o.id}`} className="list-item" style={{ color: 'inherit' }}>
                <div className="list-item__main">
                  <div className="list-item__title">
                    №{o.number} · {o.title}
                  </div>
                  <div className="list-item__meta">
                    <span>от {formatDate(o.issued_on)}</span>
                    <span>{o.ack_done}/{o.ack_total} подписей</span>
                    {o.published_at && <span>опубликован {relativeTime(o.published_at)}</span>}
                  </div>
                </div>
                <div className="list-item__actions">
                  <Badge tone={o.status === 'PUBLISHED' ? 'ok' : o.status === 'DRAFT' ? 'warn' : 'muted'}>
                    {o.status === 'PUBLISHED' ? 'Опубликован' : o.status === 'DRAFT' ? 'Черновик' : 'Архив'}
                  </Badge>
                </div>
              </Link>
            ))
          )}
        </Section>

        <Section title="Последние задачи" actions={<Link className="btn btn--sm" to="/tasks">Открыть →</Link>} flush>
          {recent_tasks.length === 0 ? (
            <EmptyState icon="✅" title="Задач пока нет" />
          ) : (
            recent_tasks.map((t) => (
              <Link key={t.id} to={`/tasks/${t.id}`} className="list-item" style={{ color: 'inherit' }}>
                <div className="list-item__main">
                  <div className="list-item__title">{t.title}</div>
                  <div className="list-item__meta">
                    <span>создана {relativeTime(t.created_at)}</span>
                    {t.assignees.length > 0 && (
                      <span>· {t.assignees.map((a) => a.user.full_name).join(', ')}</span>
                    )}
                  </div>
                </div>
                <div className="list-item__actions">
                  <TaskStatusBadge status={t.effective_status} />
                </div>
              </Link>
            ))
          )}
        </Section>
      </div>
    </div>
  )
}
