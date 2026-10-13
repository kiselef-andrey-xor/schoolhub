/** Форматирование дат, чисел и производных статусов. Все даты храним в UTC, показываем в локали. */
import type { EffectiveTaskStatus, OrderStatus, OrderType, AckStatus, PlanStatus, Role, TaskPriority } from '@/types'

const LOCALE = 'ru-RU'

/** Бэкенд отдаёт наивные datetime'ы (UTC) — нормализуем, чтобы JS не счёл их локальными. */
export function parseDate(value?: string | null): Date | null {
  if (!value) return null
  const iso = /Z$|[+-]\d{2}:?\d{2}$/.test(value) ? value : `${value}Z`
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? null : d
}

export function formatDate(value?: string | null): string {
  const d = parseDate(value)
  return d ? d.toLocaleDateString(LOCALE) : '—'
}

export function formatDateTime(value?: string | null): string {
  const d = parseDate(value)
  return d
    ? d.toLocaleString(LOCALE, { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' })
    : '—'
}

/** Дата без времени («2026-10-12») → «12.10.2026» — без сдвига часовых поясов. */
export function formatDateIso(iso?: string | null): string {
  if (!iso) return '—'
  const [y, m, d] = String(iso).slice(0, 10).split('-')
  return d && m && y ? `${d}.${m}.${y}` : '—'
}

export function formatTime(value?: string | null): string {
  const d = parseDate(value)
  return d ? d.toLocaleTimeString(LOCALE, { hour: '2-digit', minute: '2-digit' }) : '—'
}

export function relativeTime(value?: string | null): string {
  const d = parseDate(value)
  if (!d) return '—'
  const diff = Date.now() - d.getTime()
  const min = Math.round(diff / 60000)
  if (Math.abs(min) < 1) return 'только что'
  if (Math.abs(min) < 60) return min > 0 ? `${min} мин назад` : `через ${-min} мин`
  const hours = Math.round(min / 60)
  if (Math.abs(hours) < 24) return hours > 0 ? `${hours} ч назад` : `через ${-hours} ч`
  const days = Math.round(hours / 24)
  if (Math.abs(days) < 30) return days > 0 ? `${days} дн назад` : `через ${-days} дн`
  return formatDate(value)
}

/** «осталось N дн» / «просрочено на N дн» — для дедлайнов задач. */
export function deadlineLabel(deadline?: string | null, done = false): string {
  const d = parseDate(deadline)
  if (!d) return 'без срока'
  if (done) return `завершено ${formatDate(deadline)}`
  const ms = d.getTime() - Date.now()
  const days = Math.ceil(ms / 86_400_000)
  if (ms < 0) return `просрочено на ${Math.abs(days)} ${plural(Math.abs(days), 'день', 'дня', 'дней')}`
  if (days === 0) return 'сегодня'
  if (days === 1) return 'завтра'
  return `осталось ${days} ${plural(days, 'день', 'дня', 'дней')}`
}

export function plural(n: number, one: string, few: string, many: string): string {
  const mod10 = n % 10
  const mod100 = n % 100
  if (mod10 === 1 && mod100 !== 11) return one
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 10 || mod100 >= 20)) return few
  return many
}

export function formatSize(bytes?: number | null): string {
  if (!bytes && bytes !== 0) return '—'
  const units = ['Б', 'КБ', 'МБ', 'ГБ']
  let value = bytes
  let i = 0
  while (value >= 1024 && i < units.length - 1) {
    value /= 1024
    i += 1
  }
  return `${i === 0 ? value : value.toFixed(1)} ${units[i]}`
}

export function toDateInput(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

export function toDateTimeLocal(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}

/** datetime-local → ISO в UTC (то, что ждёт backend). */
export function fromDateTimeLocal(value: string): string | null {
  if (!value) return null
  const d = new Date(value)
  return Number.isNaN(d.getTime()) ? null : d.toISOString()
}

export function initials(fullName?: string | null): string {
  if (!fullName) return '?'
  const parts = fullName.trim().split(/\s+/)
  return ((parts[0]?.[0] ?? '') + (parts[1]?.[0] ?? '')).toUpperCase()
}

export function shortName(fullName?: string | null): string {
  if (!fullName) return '—'
  const [last, first, middle] = fullName.trim().split(/\s+/)
  return [last, first?.[0] ? `${first[0]}.` : '', middle?.[0] ? `${middle[0]}.` : ''].filter(Boolean).join(' ')
}

// ------------------------------------------------------------------- словари
export const ORDER_TYPE_LABEL: Record<OrderType, string> = {
  HR: 'По личному составу',
  STUDENTS: 'По обучающимся',
  EDUCATION: 'Учебная деятельность',
  SAFETY: 'Охрана труда и безопасность',
  ADMIN: 'Административно-хозяйственный',
  OTHER: 'Прочее',
}

export const ORDER_STATUS_LABEL: Record<OrderStatus, string> = {
  DRAFT: 'Черновик',
  PUBLISHED: 'Опубликован',
  ARCHIVED: 'Архив',
}

export const ACK_LABEL: Record<AckStatus, string> = {
  PENDING: 'Не ознакомлен',
  ACKNOWLEDGED: 'Ознакомлен',
}

export const PLAN_STATUS_LABEL: Record<PlanStatus, string> = {
  DRAFT: 'Черновик',
  PUBLISHED: 'Опубликован',
  ARCHIVED: 'Архив',
}

/** «12.10.2026 – 17.10.2026» — диапазон недели плана. */
export function formatWeekRange(start: string, end: string): string {
  const f = (iso: string) => {
    const [y, m, d] = iso.split('-')
    return `${d}.${m}.${y}`
  }
  return `${f(start)} – ${f(end)}`
}

export const TASK_STATUS_LABEL: Record<EffectiveTaskStatus, string> = {
  NEW: 'Новая',
  IN_PROGRESS: 'В работе',
  DONE: 'Выполнена',
  OVERDUE: 'Просрочена',
}

export const PRIORITY_LABEL: Record<TaskPriority, string> = {
  LOW: 'Низкий',
  NORMAL: 'Обычный',
  HIGH: 'Высокий',
  URGENT: 'Срочный',
}

export const ROLE_LABEL_FULL: Record<Role, string> = {
  OWNER: 'Владелец',
  ADMIN: 'Администрация',
  TEACHER: 'Учитель',
}

export const ACTION_LABEL: Record<string, string> = {
  LOGIN: 'Вход в систему',
  LOGIN_FAILED: 'Неудачная попытка входа',
  LOGOUT: 'Выход',
  PASSWORD_CHANGE: 'Смена пароля',
  ORDER_CREATE: 'Создан приказ',
  ORDER_UPDATE: 'Изменён приказ',
  ORDER_PUBLISH: 'Опубликован приказ',
  ORDER_ARCHIVE: 'Приказ в архив',
  ORDER_DELETE: 'Удалён черновик',
  ORDER_FILE_UPLOAD: 'Загружен документ',
  ORDER_FILE_DELETE: 'Удалён документ',
  ORDER_ACK: 'Подтверждено ознакомление',
  ORDER_RECIPIENTS: 'Изменён круг ознакомления',
  TASK_CREATE: 'Создана задача',
  TASK_UPDATE: 'Изменена задача',
  TASK_STATUS: 'Сменён статус задачи',
  TASK_MARK: 'Отметка исполнителя «выполнено»',
  TASK_FILE: 'Прикреплён файл к задаче',
  TASK_FILE_DELETE: 'Удалён файл задачи',
  TASK_DELETE: 'Удалена задача',
  PLAN_CREATE: 'Создан план работы',
  PLAN_UPDATE: 'Изменён план работы',
  PLAN_PUBLISH: 'Опубликован план работы',
  PLAN_ARCHIVE: 'План работы архивирован',
  PLAN_DELETE: 'Удалён черновик плана',
  USER_CREATE: 'Создан пользователь',
  USER_UPDATE: 'Изменён пользователь',
  USER_DEACTIVATE: 'Заблокирован пользователь',
  SYSTEM_SEED: 'Инициализация демо-данных',
}
