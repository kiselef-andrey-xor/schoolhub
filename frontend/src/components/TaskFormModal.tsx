/** Форма задачи: создание (OWNER/ADMIN) и редактирование.
 *  v1.2: исполнителей может быть НЕСКОЛЬКО; для учителя — урезанный набор полей. */
import { useEffect, useMemo, useState, type FormEvent } from 'react'
import { useQuery } from '@tanstack/react-query'

import { tasksApi, usersApi } from '@/api/endpoints'
import { qk } from '@/api/query'
import { Modal } from '@/components/Modal'
import { UserMultiSelect } from '@/components/UserMultiSelect'
import { useToast } from '@/components/Toast'
import { PRIORITY_LABEL, fromDateTimeLocal, shortName, toDateTimeLocal } from '@/lib/format'
import { CAP, can } from '@/lib/permissions'
import { useAuthStore } from '@/store/auth'
import type { Task, TaskPriority } from '@/types'

interface Props {
  open: boolean
  task?: Task | null
  defaultAssigneeId?: string | null
  onClose: () => void
  onSaved: (task: Task) => void
}

interface FormState {
  title: string
  description: string
  assignee_ids: string[]
  deadline: string
  priority: TaskPriority
}

export function TaskFormModal({ open, task, defaultAssigneeId, onClose, onSaved }: Props) {
  const user = useAuthStore((s) => s.user)!
  const toast = useToast()
  const canAssign = can(user.capabilities, CAP.tasksAssign)
  const [busy, setBusy] = useState(false)
  const [form, setForm] = useState<FormState>(() => empty(defaultAssigneeId))

  // справочник сотрудников — доступен только staff (учителю API его не отдаёт)
  const { data: people = [] } = useQuery({
    queryKey: qk('/users/options'),
    queryFn: () => usersApi.options(),
    enabled: open && canAssign,
  })

  useEffect(() => {
    if (!open) return
    setForm(
      task
        ? {
            title: task.title,
            description: task.description ?? '',
            assignee_ids: task.assignees.map((a) => a.user.id),
            deadline: task.deadline ? toDateTimeLocal(new Date(task.deadline.endsWith('Z') ? task.deadline : `${task.deadline}Z`)) : '',
            priority: task.priority,
          }
        : empty(defaultAssigneeId),
    )
  }, [open, task, defaultAssigneeId])

  const options = useMemo(() => people, [people])

  async function submit(e: FormEvent) {
    e.preventDefault()
    if (canAssign && form.assignee_ids.length === 0) {
      toast.error(new Error('Назначьте хотя бы одного исполнителя'))
      return
    }
    setBusy(true)
    try {
      const saved = canAssign
        ? task
          ? await tasksApi.update(task.id, {
              title: form.title.trim(),
              description: form.description.trim() || null,
              assignee_ids: form.assignee_ids,
              deadline: fromDateTimeLocal(form.deadline),
              priority: form.priority,
            })
          : await tasksApi.create({
              title: form.title.trim(),
              description: form.description.trim() || null,
              assignee_ids: form.assignee_ids,
              deadline: fromDateTimeLocal(form.deadline),
              priority: form.priority,
            })
        : // режим исполнителя: только описание
          await tasksApi.update(task!.id, { description: form.description.trim() || null })
      toast.success(task ? 'Задача обновлена' : `Задача создана${form.assignee_ids.length > 1 ? `, ${form.assignee_ids.length} исполнителя уведомлены` : ' и назначена исполнителю'}`)
      onSaved(saved)
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
      title={task ? 'Редактирование задачи' : 'Новая задача'}
      footer={
        <>
          <button className="btn" onClick={onClose} disabled={busy}>Отмена</button>
          <button className="btn btn--primary" form="task-form" type="submit" disabled={busy}>
            {busy ? 'Сохраняем…' : task ? 'Сохранить' : 'Создать и назначить'}
          </button>
        </>
      }
    >
      <form id="task-form" onSubmit={submit} className="stack" style={{ gap: 14 }}>
        <label className="field">
          <span className="field__label">Что нужно сделать *</span>
          <input
            className="input"
            required
            minLength={3}
            value={form.title}
            disabled={!canAssign}
            onChange={(e) => setForm({ ...form, title: e.target.value })}
            placeholder="Например: сдать отчёт по успеваемости 9-х классов"
          />
        </label>

        <label className="field">
          <span className="field__label">Описание</span>
          <textarea
            className="textarea"
            value={form.description}
            onChange={(e) => setForm({ ...form, description: e.target.value })}
            placeholder="Контекст, формат результата, где отметить выполнение"
          />
        </label>

        {canAssign ? (
          <>
            <div className="field">
              <span className="field__label">Исполнители (можно несколько) *</span>
              <UserMultiSelect
                options={options}
                value={form.assignee_ids}
                onChange={(ids) => setForm({ ...form, assignee_ids: ids })}
                placeholder="Исполнители не выбраны"
              />
              <span className="field__hint">
                Каждый получит уведомление; у всех своя отметка «выполнено» — задача закроется, когда отметятся все
              </span>
            </div>

            <div className="form-grid">
              <label className="field">
                <span className="field__label">Дедлайн</span>
                <input
                  className="input"
                  type="datetime-local"
                  value={form.deadline}
                  onChange={(e) => setForm({ ...form, deadline: e.target.value })}
                />
                <span className="field__hint">После дедлайна задача автоматически станет «Просрочена»</span>
              </label>

              <label className="field">
                <span className="field__label">Приоритет</span>
                <select
                  className="select"
                  value={form.priority}
                  onChange={(e) => setForm({ ...form, priority: e.target.value as TaskPriority })}
                >
                  {(Object.entries(PRIORITY_LABEL) as [TaskPriority, string][]).map(([value, label]) => (
                    <option key={value} value={value}>{label}</option>
                  ))}
                </select>
              </label>
            </div>
          </>
        ) : (
          <div className="alert alert--info small">
            Исполнители, дедлайн и приоритет назначаются администрацией. Вы можете уточнить описание,
            менять статус своей задачи, ставить отметку «выполнено» и прикреплять файлы.
            {task && task.assignees.length > 0 && (
              <div>Исполнители: {task.assignees.map((a) => shortName(a.user.full_name)).join(', ')}</div>
            )}
          </div>
        )}
      </form>
    </Modal>
  )
}

function empty(defaultAssigneeId?: string | null): FormState {
  const deadline = new Date(Date.now() + 3 * 86_400_000)
  return {
    title: '',
    description: '',
    assignee_ids: defaultAssigneeId ? [defaultAssigneeId] : [],
    deadline: toDateTimeLocal(deadline),
    priority: 'NORMAL',
  }
}
