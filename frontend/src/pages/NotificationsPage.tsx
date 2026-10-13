/** Уведомления пользователя: список, отметка прочитанным, переход к сущности. */
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'

import { notificationsApi } from '@/api/endpoints'
import { qk } from '@/api/query'
import { Badge, EmptyState, ErrorState, Pagination, Spinner } from '@/components/ui'
import { useToast } from '@/components/Toast'
import { relativeTime } from '@/lib/format'

const PER_PAGE = 20

const TYPE_META: Record<string, { icon: string; tone: 'ok' | 'warn' | 'danger' | 'info' | 'brand' | 'muted' }> = {
  ORDER_PUBLISHED: { icon: '📜', tone: 'info' },
  ORDER_UPDATED: { icon: '📝', tone: 'info' },
  ORDER_ACK_DEADLINE: { icon: '⏰', tone: 'warn' },
  TASK_ASSIGNED: { icon: '✅', tone: 'brand' },
  TASK_STATUS_CHANGED: { icon: '🔁', tone: 'warn' },
  TASK_MARK: { icon: '🔁', tone: 'ok' },
  TASK_COMMENT: { icon: '💬', tone: 'muted' },
  PLAN_PUBLISHED: { icon: '🗓', tone: 'brand' },
  PLAN_UPDATED: { icon: '🗓', tone: 'info' },
}

export function NotificationsPage() {
  const navigate = useNavigate()
  const toast = useToast()
  const qc = useQueryClient()
  const [unreadOnly, setUnreadOnly] = useState(false)
  const [page, setPage] = useState(1)

  const params = { unread_only: unreadOnly || undefined, page, per_page: PER_PAGE }
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: qk('/notifications', params as never),
    queryFn: () => notificationsApi.list(params),
  })

  const invalidate = () => {
    void qc.invalidateQueries({ queryKey: ['/notifications'] })
    void qc.invalidateQueries({ queryKey: qk('/notifications/unread-count') })
  }

  return (
    <div className="stack" style={{ gap: 16 }}>
      <div className="page-head">
        <div className="page-head__text">
          <h1>Уведомления</h1>
          <div className="page-head__hint">Новые приказы на ознакомление, назначенные задачи и изменения статусов.</div>
        </div>
        <div className="page-head__actions">
          <button className={unreadOnly ? 'chip chip--active' : 'chip'} onClick={() => { setUnreadOnly((v) => !v); setPage(1) }}>
            Только непрочитанные
          </button>
          <button
            className="btn"
            onClick={async () => {
              try {
                await notificationsApi.markAllRead()
                toast.success('Все уведомления отмечены прочитанными')
                invalidate()
                void refetch()
              } catch (e) {
                toast.error(e)
              }
            }}
          >
            Прочитать все
          </button>
        </div>
      </div>

      <section className="card">
        {isLoading ? (
          <Spinner label="Загружаем уведомления…" />
        ) : error ? (
          <ErrorState error={error} onRetry={() => void refetch()} />
        ) : !data || data.items.length === 0 ? (
          <EmptyState icon="🔔" title="Уведомлений нет" hint={unreadOnly ? 'Все уведомления прочитаны' : 'Здесь появятся события по приказам и задачам'} />
        ) : (
          <>
            {data.items.map((n) => {
              const meta = TYPE_META[n.type] ?? { icon: '🔔', tone: 'muted' as const }
              return (
                <div
                  key={n.id}
                  className="list-item"
                  style={{ cursor: n.entity_id ? 'pointer' : 'default', background: n.is_read ? undefined : 'var(--brand-50)' }}
                  onClick={async () => {
                    if (!n.is_read) {
                      try {
                        await notificationsApi.markRead(n.id)
                        invalidate()
                      } catch { /* не критично */ }
                    }
                    if (n.entity_type === 'task') navigate(`/tasks/${n.entity_id}`)
                    else if (n.entity_type === 'order') navigate(`/orders/${n.entity_id}`)
                    else if (n.entity_type === 'plan') navigate(`/plans/${n.entity_id}`)
                  }}
                >
                  <div style={{ fontSize: 20 }}>{meta.icon}</div>
                  <div className="list-item__main">
                    <div className="list-item__title" style={{ fontWeight: n.is_read ? 550 : 700 }}>{n.title}</div>
                    {n.body && <div className="small muted">{n.body}</div>}
                    <div className="list-item__meta" style={{ marginTop: 4 }}>
                      <span>{relativeTime(n.created_at)}</span>
                      <Badge tone={meta.tone}>{n.type.replace(/_/g, ' ').toLowerCase()}</Badge>
                    </div>
                  </div>
                  <div className="list-item__actions">
                    {!n.is_read && <Badge tone="danger">новое</Badge>}
                  </div>
                </div>
              )
            })}
            <Pagination page={data.page} pages={data.pages} total={data.total} perPage={data.per_page} onPage={setPage} />
          </>
        )}
      </section>
    </div>
  )
}
