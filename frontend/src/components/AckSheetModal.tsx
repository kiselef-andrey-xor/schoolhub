/** Лист ознакомления (для Администрации/Владельца): кто подписал, кто нет, экспорт в CSV. */
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'

import { downloadAuthorized } from '@/api/client'
import { ordersApi } from '@/api/endpoints'
import { qk } from '@/api/query'
import { Modal } from '@/components/Modal'
import { AckBadge, Avatar, EmptyState, Progress, Spinner } from '@/components/ui'
import { formatDateTime } from '@/lib/format'
import type { OrderDetail } from '@/types'

export function AckSheetModal({ open, order, onClose }: { open: boolean; order: OrderDetail | null; onClose: () => void }) {
  const [filter, setFilter] = useState<'all' | 'PENDING' | 'ACKNOWLEDGED'>('all')

  const { data, isLoading } = useQuery({
    queryKey: qk(`/orders/${order?.id}/acknowledgements`, { status: filter === 'all' ? undefined : filter }),
    queryFn: () => ordersApi.acknowledgements(order!.id, filter === 'all' ? undefined : filter),
    enabled: open && Boolean(order),
  })

  const { data: summary } = useQuery({
    queryKey: qk(`/orders/${order?.id}/ack-summary`),
    queryFn: () => ordersApi.ackSummary(order!.id),
    enabled: open && Boolean(order),
  })

  if (!order) return null

  return (
    <Modal
      open={open}
      onClose={onClose}
      wide
      title={`Лист ознакомления — приказ №${order.number}`}
      footer={
        <>
          <button className="btn" onClick={onClose}>Закрыть</button>
          <button
            className="btn btn--primary"
            onClick={() => void downloadAuthorized(ordersApi.exportAckSheet(), 'ack_sheet.csv')}
            title="Выгрузка по всем опубликованным приказам"
          >
            ⬇ Экспорт CSV
          </button>
        </>
      }
    >
      <div className="stack" style={{ gap: 14 }}>
        {summary && (
          <div className="row" style={{ gap: 16 }}>
            <div className="grow">
              <div className="row small muted">
                <span>
                  Подписали {summary.acknowledged} из {summary.total}
                </span>
                <span className="grow" />
                <span>{summary.progress.toFixed(0)}%</span>
              </div>
              <Progress value={summary.progress} tone={summary.progress === 100 ? 'ok' : undefined} />
            </div>
            {summary.ack_deadline && <div className="small muted nowrap">срок до {summary.ack_deadline}</div>}
          </div>
        )}

        <div className="row">
          {(['all', 'ACKNOWLEDGED', 'PENDING'] as const).map((value) => (
            <button
              key={value}
              className={filter === value ? 'chip chip--active' : 'chip'}
              onClick={() => setFilter(value)}
            >
              {value === 'all' ? 'Все' : value === 'ACKNOWLEDGED' ? 'Ознакомлены' : 'Не ознакомлены'}
            </button>
          ))}
        </div>

        {isLoading ? (
          <Spinner />
        ) : !data || data.length === 0 ? (
          <EmptyState icon="🗒" title="Нет записей" hint="Измените фильтр или круг ознакомления" />
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Сотрудник</th>
                <th style={{ width: 200 }}>Должность</th>
                <th style={{ width: 150 }}>Статус</th>
                <th style={{ width: 170 }}>Дата и время</th>
                <th>Комментарий</th>
              </tr>
            </thead>
            <tbody>
              {data.map((a) => (
                <tr key={a.id}>
                  <td>
                    <div className="user-chip">
                      <Avatar name={a.user.full_name} size="sm" />
                      <div>
                        <div className="user-chip__name">{a.user.full_name}</div>
                        <div className="tiny muted">{a.user.email}</div>
                      </div>
                    </div>
                  </td>
                  <td className="small">{a.user.position ?? '—'}</td>
                  <td><AckBadge status={a.status} /></td>
                  <td className="small nowrap">
                    {a.acknowledged_at ? formatDateTime(a.acknowledged_at) : '—'}
                    {a.ip_address && <div className="tiny muted mono">{a.ip_address}</div>}
                  </td>
                  <td className="small">{a.comment ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        {summary && summary.pending_users.length > 0 && (
          <div className="alert alert--warn small">
            <strong>Напомнить ({summary.pending_users.length}):</strong>{' '}
            {summary.pending_users.map((u) => u.full_name).join(', ')}
          </div>
        )}
      </div>
    </Modal>
  )
}
