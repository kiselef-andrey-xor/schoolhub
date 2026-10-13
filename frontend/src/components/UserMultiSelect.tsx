/** Мультивыбор сотрудников: чипы выбранных + выпадающая панель с поиском.
 *  Используется в форме задачи (исполнители), приказе (круг ознакомления) и редакторе плана (ответственные). */
import { useEffect, useMemo, useRef, useState } from 'react'

import { Avatar } from '@/components/ui'
import { shortName } from '@/lib/format'
import type { User } from '@/types'

interface Props {
  options: User[]
  value: string[]
  onChange: (ids: string[]) => void
  placeholder?: string
  disabled?: boolean
}

export function UserMultiSelect({ options, value, onChange, placeholder = 'Никто не выбран', disabled }: Props) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const rootRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const onClick = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onClick)
    return () => document.removeEventListener('mousedown', onClick)
  }, [open])

  const byId = useMemo(() => new Map(options.map((u) => [u.id, u])), [options])
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return options
    return options.filter((u) =>
      `${u.full_name} ${u.position ?? ''} ${u.email}`.toLowerCase().includes(q),
    )
  }, [options, query])

  const toggle = (id: string) =>
    onChange(value.includes(id) ? value.filter((x) => x !== id) : [...value, id])

  return (
    <div ref={rootRef}>
      {value.length > 0 ? (
        <div className="chips">
          {value.map((id) => {
            const u = byId.get(id)
            return (
              <span className="uchip" key={id}>
                <Avatar name={u?.full_name ?? '?'} size="sm" />
                <span>{u ? shortName(u.full_name) : '…'}</span>
                {!disabled && (
                  <button
                    type="button"
                    className="uchip__x"
                    title="Убрать"
                    onClick={() => toggle(id)}
                  >
                    ✕
                  </button>
                )}
              </span>
            )
          })}
        </div>
      ) : (
        <div className="tiny muted">{placeholder}</div>
      )}

      {!disabled && (
        <div className="picker" style={{ marginTop: 7 }}>
          <button type="button" className="btn btn--sm" onClick={() => setOpen((v) => !v)}>
            {value.length ? '✎ Изменить список' : '＋ Выбрать сотрудников'}
          </button>
          {open && (
            <div className="picker__panel">
              <input
                className="input"
                autoFocus
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Поиск: ФИО, должность, e-mail…"
                style={{ marginBottom: 6 }}
              />
              <div className="row" style={{ gap: 6, marginBottom: 4 }}>
                <button
                  type="button"
                  className="btn btn--sm"
                  onClick={() => onChange(Array.from(new Set([...value, ...filtered.map((u) => u.id)])))}
                >
                  Выбрать всех
                </button>
                <button type="button" className="btn btn--sm" onClick={() => onChange([])}>Очистить</button>
                <span className="grow" />
                <span className="tiny muted">выбрано: {value.length}</span>
              </div>
              <div style={{ maxHeight: 220, overflowY: 'auto' }}>
                {filtered.length === 0 && <div className="small muted" style={{ padding: 8 }}>Никого не найдено</div>}
                {filtered.map((u) => (
                  <div className="picker__row" key={u.id} onClick={() => toggle(u.id)}>
                    <span className="picker__check">{value.includes(u.id) ? '☑' : '☐'}</span>
                    <Avatar name={u.full_name} size="sm" />
                    <span style={{ minWidth: 0 }}>
                      <span style={{ display: 'block', fontWeight: 600 }}>{u.full_name}</span>
                      <span className="tiny muted">{u.position ?? 'сотрудник'}</span>
                    </span>
                  </div>
                ))}
              </div>
              <div className="row" style={{ marginTop: 6 }}>
                <span className="grow" />
                <button type="button" className="btn btn--sm" onClick={() => setOpen(false)}>Готово</button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
