/** Журнал событий (OWNER/ADMIN): кто, что и когда сделал. Фильтры по действию, субъекту и периоду. */
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'

import { auditApi } from '@/api/endpoints'
import { qk } from '@/api/query'
import { Badge, EmptyState, ErrorState, Pagination, Spinner } from '@/components/ui'
import { ACTION_LABEL, formatDateTime, relativeTime } from '@/lib/format'
import { ROLE_LABEL } from '@/lib/permissions'
import type { AuditEntry, Role } from '@/types'

const PER_PAGE = 30

export function AuditPage() {
  const [action, setAction] = useState('')
  const [entity, setEntity] = useState('')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [page, setPage] = useState(1)
  const [expanded, setExpanded] = useState<string | null>(null)

  const params = {
    action: action || undefined,
    entity_type: entity || undefined,
    date_from: dateFrom || undefined,
    date_to: dateTo || undefined,
    page,
    per_page: PER_PAGE,
  }

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: qk('/audit', params as never),
    queryFn: () => auditApi.list(params),
  })

  const { data: actions = [] } = useQuery({
    queryKey: qk('/audit/actions'),
    queryFn: auditApi.actions,
  })

  return (
    <div className="stack" style={{ gap: 16 }}>
      <div className="page-head">
        <div className="page-head__text">
          <h1>Журнал событий</h1>
          <div className="page-head__hint">
            Аудит значимых действий: создание и публикация приказов, загрузки документов, подтверждения
            ознакомления, операции с задачами и пользователями.
          </div>
        </div>
      </div>

      <section className="card">
        <div className="card__body">
          <div className="filters">
            <label className="field">
              <span className="field__label">Действие</span>
              <select className="select" value={action} onChange={(e) => { setAction(e.target.value); setPage(1) }}>
                <option value="">Все действия</option>
                {actions.map((a) => (
                  <option key={a} value={a}>{ACTION_LABEL[a] ?? a} ({a})</option>
                ))}
              </select>
            </label>
            <label className="field">
              <span className="field__label">Объект</span>
              <select className="select" value={entity} onChange={(e) => { setEntity(e.target.value); setPage(1) }}>
                <option value="">Все объекты</option>
                <option value="order">Приказы</option>
                <option value="task">Задачи</option>
                <option value="user">Пользователи</option>
              </select>
            </label>
            <label className="field">
              <span className="field__label">Период с</span>
              <input className="input" type="date" value={dateFrom} onChange={(e) => { setDateFrom(e.target.value); setPage(1) }} />
            </label>
            <label className="field">
              <span className="field__label">Период по</span>
              <input className="input" type="date" value={dateTo} onChange={(e) => { setDateTo(e.target.value); setPage(1) }} />
            </label>
          </div>
        </div>
      </section>

      <section className="card">
        {isLoading ? (
          <Spinner label="Загружаем журнал…" />
        ) : error ? (
          <ErrorState error={error} onRetry={() => void refetch()} />
        ) : !data || data.items.length === 0 ? (
          <EmptyState icon="🧾" title="Записей не найдено" hint="Измените фильтры или период" />
        ) : (
          <>
            <table className="table table--clickable">
              <thead>
                <tr>
                  <th style={{ width: 170 }}>Когда</th>
                  <th style={{ width: 240 }}>Кто</th>
                  <th style={{ width: 250 }}>Действие</th>
                  <th>Изменения</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((entry) => (
                  <AuditRow
                    key={entry.id}
                    entry={entry}
                    expanded={expanded === entry.id}
                    onToggle={() => setExpanded(expanded === entry.id ? null : entry.id)}
                  />
                ))}
              </tbody>
            </table>
            <Pagination page={data.page} pages={data.pages} total={data.total} perPage={data.per_page} onPage={setPage} />
          </>
        )}
      </section>
    </div>
  )
}

function AuditRow({ entry, expanded, onToggle }: { entry: AuditEntry; expanded: boolean; onToggle: () => void }) {
  const changes = entry.changes ?? {}
  const summary = Object.entries(changes)
    .slice(0, 3)
    .map(([key, value]) => {
      const text = typeof value === 'object' && value !== null
        ? Object.entries(value as Record<string, unknown>)
            .map(([k, v]) => `${k}: ${String(v ?? '—')}`)
            .join(' → ')
        : String(value)
      return `${key} = ${text}`
    })
    .join(', ')

  return (
    <tr onClick={onToggle}>
      <td className="small nowrap">
        {formatDateTime(entry.created_at)}
        <div className="tiny muted">{relativeTime(entry.created_at)}</div>
      </td>
      <td className="small">
        {entry.actor_email ?? 'система'}
        {entry.actor_role && (
          <div className="tiny muted">{ROLE_LABEL[entry.actor_role as Role] ?? entry.actor_role}</div>
        )}
      </td>
      <td>
        <Badge tone={toneFor(entry.action)}>{ACTION_LABEL[entry.action] ?? entry.action}</Badge>
        <div className="tiny muted">{entry.entity_type ? `${entry.entity_type}${entry.entity_id ? ` · ${String(entry.entity_id).slice(0, 8)}` : ''}` : ''}</div>
      </td>
      <td className="small">
        {expanded ? (
          <pre className="mono" style={{ margin: 0, whiteSpace: 'pre-wrap', maxHeight: 220, overflow: 'auto' }}>
            {JSON.stringify(changes, null, 2)}
          </pre>
        ) : (
          <span className="muted">{summary || '—'}</span>
        )}
        {entry.ip_address && <div className="tiny muted mono">ip: {entry.ip_address}</div>}
      </td>
    </tr>
  )
}

function toneFor(action: string): 'ok' | 'warn' | 'danger' | 'info' | 'neutral' {
  if (action.includes('FAILED') || action.includes('DELETE') || action.includes('DEACTIVATE')) return 'danger'
  if (action.includes('PUBLISH') || action.includes('ACK')) return 'ok'
  if (action.includes('CREATE')) return 'info'
  if (action.includes('UPDATE') || action.includes('STATUS') || action.includes('MARK') || action.includes('RECIPIENTS')) return 'warn'
  return 'neutral'
}
