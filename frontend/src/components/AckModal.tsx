/** Подтверждение ознакомления с приказом (юридически значимое действие: фиксируются время, IP, User-Agent). */
import { useState } from 'react'

import { ordersApi } from '@/api/endpoints'
import { Modal } from '@/components/Modal'
import { useToast } from '@/components/Toast'
import { formatDate } from '@/lib/format'
import type { OrderDetail } from '@/types'

interface Props {
  open: boolean
  order: OrderDetail
  onClose: () => void
  onDone: () => void
}

export function AckModal({ open, order, onClose, onDone }: Props) {
  const toast = useToast()
  const [confirmed, setConfirmed] = useState(false)
  const [comment, setComment] = useState('')
  const [busy, setBusy] = useState(false)

  async function submit() {
    if (!confirmed) return
    setBusy(true)
    try {
      await ordersApi.acknowledge(order.id, comment.trim() || undefined)
      toast.success('Ознакомление подтверждено')
      setConfirmed(false)
      setComment('')
      onDone()
      onClose()
    } catch (err) {
      toast.error(err)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Подтверждение ознакомления"
      footer={
        <>
          <button className="btn" onClick={onClose} disabled={busy}>Отмена</button>
          <button className="btn btn--success" onClick={submit} disabled={!confirmed || busy}>
            {busy ? 'Отправляем…' : 'Подтвердить ознакомление'}
          </button>
        </>
      }
    >
      <div className="stack" style={{ gap: 12 }}>
        <div className="alert alert--info">
          <strong>Приказ №{order.number} от {formatDate(order.issued_on)}</strong>
          <div>{order.title}</div>
        </div>

        <label className="row small" style={{ gap: 8, alignItems: 'flex-start' }}>
          <input type="checkbox" checked={confirmed} onChange={(e) => setConfirmed(e.target.checked)} style={{ marginTop: 3 }} />
          <span>
            Я полностью прочитал(а) текст приказа, смысл и порядок его исполнения мне понятны.
            Подтверждение фиксирует дату и время, IP-адрес и браузер — как подпись в бумажном листе ознакомления.
          </span>
        </label>

        <label className="field">
          <span className="field__label">Комментарий (необязательно)</span>
          <textarea
            className="textarea"
            value={comment}
            maxLength={500}
            onChange={(e) => setComment(e.target.value)}
            placeholder="Например: «Принято к исполнению» или вопрос ответственному"
          />
          <span className="field__hint">{comment.length}/500 символов</span>
        </label>
      </div>
    </Modal>
  )
}
