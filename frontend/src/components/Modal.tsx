/** Модальное окно: focus-trap (упрощённый), закрытие по Esc и по клику на подложку. */
import { useEffect, useRef, type ReactNode } from 'react'

interface ModalProps {
  open: boolean
  title: ReactNode
  onClose: () => void
  children: ReactNode
  footer?: ReactNode
  wide?: boolean
}

export function Modal({ open, title, onClose, children, footer, wide = false }: ModalProps) {
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKey)
    document.body.style.overflow = 'hidden'
    // автофокус на первый интерактивный элемент
    const focusable = ref.current?.querySelector<HTMLElement>(
      'input,select,textarea,button:not([data-autofocus-skip])',
    )
    focusable?.focus()
    return () => {
      document.removeEventListener('keydown', onKey)
      document.body.style.overflow = ''
    }
  }, [open, onClose])

  if (!open) return null

  return (
    <div
      className="modal-backdrop"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose()
      }}
      role="presentation"
    >
      <div className={wide ? 'modal modal--wide' : 'modal'} role="dialog" aria-modal="true" ref={ref}>
        <header className="modal__head">
          <h3>{title}</h3>
          <button className="btn btn--ghost btn--icon" onClick={onClose} aria-label="Закрыть" data-autofocus-skip>
            ✕
          </button>
        </header>
        <div className="modal__body">{children}</div>
        {footer && <footer className="modal__foot">{footer}</footer>}
      </div>
    </div>
  )
}
