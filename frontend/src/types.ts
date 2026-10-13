/**
 * Контракт API (зеркалит pydantic-схемы backend'а).
 * При изменении схем на сервере — обновлять здесь (см. /api/v1/openapi.json).
 */

export type Role = 'OWNER' | 'ADMIN' | 'TEACHER'

export type OrderType = 'HR' | 'STUDENTS' | 'EDUCATION' | 'SAFETY' | 'ADMIN' | 'OTHER'
export type OrderStatus = 'DRAFT' | 'PUBLISHED' | 'ARCHIVED'
export type AckStatus = 'PENDING' | 'ACKNOWLEDGED'

/** Хранимые статусы задачи + вычисляемый OVERDUE (просрочена). */
export type TaskStatusStored = 'NEW' | 'IN_PROGRESS' | 'DONE'
export type EffectiveTaskStatus = TaskStatusStored | 'OVERDUE'
export type TaskPriority = 'LOW' | 'NORMAL' | 'HIGH' | 'URGENT'

export type AuthSource = 'local' | 'ldap'

export interface User {
  id: string
  email: string
  full_name: string
  position?: string | null
  phone?: string | null
  role: Role
  is_active: boolean
  created_at: string
  last_login_at?: string | null
  /** 'local' — пароль SchoolHub, 'ldap' — учётная запись домена (Active Directory) */
  auth_source: AuthSource
  domain_account?: string | null
  ad_groups?: string[] | null
  last_ad_sync_at?: string | null
}

export interface Me extends Omit<User, 'created_at' | 'last_login_at'> {
  capabilities: string[]
}

export interface SetupStatus {
  is_configured: boolean
  setup_required: boolean
  school_name?: string | null
  completed_by?: string | null
  hint?: string
}

export interface LoginOptions {
  ldap_enabled: boolean
  local_enabled: boolean
  login_hint: string
  password_managed_by: string
}

export interface ADUser {
  username: string
  full_name: string
  email: string
  position?: string | null
  phone?: string | null
  dn?: string | null
  disabled: boolean
  groups: string[]
}

export interface ADImportResult {
  created: string[]
  skipped: string[]
  failed: { username: string; error: string }[]
  total: number
}

export interface OrderFile {
  id: string
  original_name: string
  mime_type: string
  size_bytes: number
  version: number
  is_current: boolean
  checksum?: string | null
  created_at: string
  uploaded_by?: User | null
}

export interface Acknowledgement {
  id: string
  status: AckStatus
  acknowledged_at?: string | null
  comment?: string | null
  ip_address?: string | null
  user: User
}

export interface OrderListItem {
  id: string
  number: string
  order_year: number
  title: string
  order_type: OrderType
  status: OrderStatus
  issued_on: string
  ack_deadline?: string | null
  published_at?: string | null
  created_by?: User | null
  current_file?: OrderFile | null
  ack_total: number
  ack_done: number
  my_ack?: Acknowledgement | null
  can_manage: boolean
}

export interface OrderDetail extends OrderListItem {
  description?: string | null
  require_all: boolean
  recipient_ids: string[]
  created_at: string
  updated_at: string
  files: OrderFile[]
}

export interface TaskAssignee {
  id: string
  user: User
  /** личная отметка «выполнено» (null — отметки нет) */
  done_at?: string | null
}

export interface TaskFile {
  id: string
  original_name: string
  mime_type: string
  size_bytes: number
  checksum?: string | null
  created_at: string
  uploaded_by?: User | null
}

export interface Task {
  id: string
  title: string
  description?: string | null
  status: TaskStatusStored
  effective_status: EffectiveTaskStatus
  priority: TaskPriority
  deadline?: string | null
  created_at: string
  updated_at: string
  completed_at?: string | null
  creator?: User | null
  assignees: TaskAssignee[]
  is_overdue: boolean
  days_left: number | null
  can_edit: boolean
  can_mark: boolean
  my_done: boolean
  marks_done: number
  files_count: number
}

export interface TaskComment {
  id: string
  body: string
  created_at: string
  author?: User | null
}

export interface TaskHistoryItem {
  id: string
  from_status: string | null
  to_status: string
  note?: string | null
  created_at: string
  actor?: User | null
}

export interface TaskDetail extends Task {
  comments: TaskComment[]
  history: TaskHistoryItem[]
  files: TaskFile[]
}

// ------------------------------------------------- план работы на неделю
export type PlanStatus = 'DRAFT' | 'PUBLISHED' | 'ARCHIVED'

export interface PlanDuty {
  klass?: string | null
  teacher?: User | null
}

export interface PlanItem {
  text: string
  place?: string | null
  resp: User[]
}

export interface PlanEvent {
  title: string
  time?: string | null
  place?: string | null
  resp: User[]
}

export interface PlanDay {
  date: string
  weekday: string
  events: PlanEvent[]
}

export interface PlanContent {
  duty: PlanDuty
  notes: string[]
  month_items: PlanItem[]
  week_items: PlanItem[]
  days: PlanDay[]
}

export interface Plan {
  id: string
  week_start: string
  week_end: string
  status: PlanStatus
  content: PlanContent
  created_by?: User | null
  published_at?: string | null
  created_at: string
  updated_at: string
  events_total: number
  responsibles_total: number
  my_items: number
  can_manage: boolean
}

export interface PlanListItem {
  id: string
  week_start: string
  week_end: string
  status: PlanStatus
  duty_class?: string | null
  events_total: number
  responsibles_total: number
  my_items: number
  published_at?: string | null
  created_by?: User | null
  can_manage: boolean
}

export interface Page<T> {
  items: T[]
  total: number
  page: number
  per_page: number
  pages: number
}

export interface TaskPage extends Page<Task> {
  status_counts: Record<EffectiveTaskStatus | 'all', number>
}

export interface AppNotification {
  id: string
  type: string
  title: string
  body?: string | null
  entity_type?: 'order' | 'task' | 'plan' | null
  entity_id?: string | null
  is_read: boolean
  created_at: string
}

export interface AuditEntry {
  id: string
  actor_id?: string | null
  actor_email?: string | null
  actor_role?: Role | null
  action: string
  entity_type?: string | null
  entity_id?: string | null
  changes?: Record<string, unknown> | null
  ip_address?: string | null
  created_at: string
}

export interface Dashboard {
  current_plan?: Plan | null
  summary: {
    scope: 'personal' | 'global'
    orders: { total: number; published: number; drafts: number; pending_ack: number }
    tasks: { total: number; new: number; in_progress: number; done: number; overdue: number }
    users?: { total: number; teachers: number; admins: number; active: number } | null
  }
  pending_acks: OrderListItem[]
  my_tasks: Task[]
  recent_orders: OrderListItem[]
  recent_tasks: Task[]
}

export interface TokenPair {
  access_token: string
  token_type: string
  expires_in?: number
  /** refresh-токен в теле НЕ отдаётся — живёт в httpOnly-cookie */
}

export type QueryParams = Record<string, string | number | boolean | undefined | null>
