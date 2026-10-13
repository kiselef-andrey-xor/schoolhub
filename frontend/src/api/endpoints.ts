/**
 * Типизированные вызовы API (тонкая обёртка над http-клиентом).
 * Один модуль = одна точка правки при изменении контракта.
 */
import { http } from './client'
import type {
  Acknowledgement,
  ADImportResult,
  ADUser,
  AppNotification,
  AuditEntry,
  SetupStatus,
  Dashboard,
  LoginOptions,
  Me,
  OrderDetail,
  OrderListItem,
  OrderStatus,
  OrderType,
  Page,
  QueryParams,
  Role,
  Plan,
  PlanListItem,
  PlanStatus,
  Task,
  TaskComment,
  TaskDetail,
  TaskPage,
  TaskPriority,
  TaskStatusStored,
  TokenPair,
  User,
} from '@/types'

export interface OrderFilters {
  search?: string
  order_type?: OrderType | ''
  status?: OrderStatus | ''
  date_from?: string
  date_to?: string
  ack?: 'all' | 'pending' | 'acknowledged' | ''
  mine_pending?: boolean
  page?: number
  per_page?: number
}

export interface TaskFilters {
  status?: TaskStatusStored | 'OVERDUE' | ''
  assignee_id?: string
  creator_id?: string
  priority?: TaskPriority | ''
  search?: string
  due_before?: string
  due_after?: string
  sort?: 'deadline' | 'created' | 'priority' | 'title' | 'updated'
  order?: 'asc' | 'desc'
  page?: number
  per_page?: number
}

export interface TaskPayload {
  title: string
  description?: string | null
  assignee_ids?: string[]
  deadline?: string | null
  priority: TaskPriority
  status?: TaskStatusStored
}

export interface OrderPayload {
  number: string
  order_year: number
  title: string
  description?: string | null
  order_type: OrderType
  issued_on: string
  ack_deadline?: string | null
  require_all?: boolean
  recipient_ids?: string[] | null
}

export interface PlanContentPayload {
  duty?: { klass?: string | null; teacher_id?: string | null }
  notes?: string[]
  month_items?: { text: string; place?: string | null; resp: string[] }[]
  week_items?: { text: string; place?: string | null; resp: string[] }[]
  days?: { date: string; events: { title: string; time?: string | null; place?: string | null; resp: string[] }[] }[]
}

export interface PlanPayload {
  week_start: string
  content?: PlanContentPayload
}

/** Публичные вызовы первоначальной настройки (до создания первого Владельца). */
export const setupApi = {
  status: () => http.public.get<SetupStatus>('/setup/status'),
  info: () => http.public.get<Record<string, unknown>>('/setup/info'),
}

export const authApi = {
  /** Публичный эндпоинт: какие способы входа доступны (домен / локально). */
  loginOptions: () => http.public.get<LoginOptions>('/auth/login-options'),
  login: (email: string, password: string, remember = true) =>
    http.public.post<TokenPair>('/auth/login', { email, password, remember }),
  /** обновление access-токена по httpOnly-cookie (тело не нужно) */
  refresh: () => http.public.post<TokenPair>('/auth/refresh'),
  me: () => http.get<Me>('/auth/me'),
  logout: () => http.post<void>('/auth/logout'),
  adDiagnostics: () => http.get<Record<string, unknown>>('/auth/ad/diagnostics'),
}

export const ordersApi = {
  list: (filters: OrderFilters = {}) => http.get<Page<OrderListItem>>('/orders', filters as QueryParams),
  detail: (id: string) => http.get<OrderDetail>(`/orders/${id}`),
  create: (payload: OrderPayload) => http.post<OrderDetail>('/orders', payload),
  update: (id: string, payload: Partial<OrderPayload> & { status?: OrderStatus }) =>
    http.patch<OrderDetail>(`/orders/${id}`, payload),
  publish: (id: string) => http.post<OrderDetail>(`/orders/${id}/publish`),
  archive: (id: string) => http.post<OrderDetail>(`/orders/${id}/archive`),
  remove: (id: string) => http.delete<void>(`/orders/${id}`),
  uploadFile: (id: string, file: File) => {
    const form = new FormData()
    form.append('file', file)
    return http.upload<OrderDetail>(`/orders/${id}/files`, form)
  },
  deleteFile: (id: string, fileId: string) => http.delete<OrderDetail>(`/orders/${id}/files/${fileId}`),
  previewMeta: (id: string) =>
    http.get<{ order_id: string; file_id: string; original_name: string; mime_type: string; preview: 'inline' | 'download'; url: string; converter?: string | null }>(
      `/orders/${id}/preview`,
    ),
  acknowledge: (id: string, comment?: string) =>
    http.post<Acknowledgement>(`/orders/${id}/acknowledgements`, { comment: comment ?? null }),
  acknowledgements: (id: string, status?: 'PENDING' | 'ACKNOWLEDGED') =>
    http.get<Acknowledgement[]>(`/orders/${id}/acknowledgements`, { status }),
  ackSummary: (id: string) =>
    http.get<{
      order_id: string
      total: number
      acknowledged: number
      pending: number
      progress: number
      ack_deadline: string | null
      pending_users: { id: string; full_name: string; email: string }[]
    }>(`/orders/${id}/ack-summary`),
  setRecipients: (id: string, user_ids: string[]) => http.put<OrderDetail>(`/orders/${id}/recipients`, { user_ids }),
  filePath: (id: string, fileId?: string, inline = true) =>
    `/orders/${id}/file?inline=${inline}${fileId ? `&file_id=${fileId}` : ''}`,
  exportAckSheet: () => '/orders/export/ack-sheet.csv',
}

export const tasksApi = {
  list: (filters: TaskFilters = {}) => http.get<TaskPage>('/tasks', filters as QueryParams),
  detail: (id: string) => http.get<TaskDetail>(`/tasks/${id}`),
  create: (payload: TaskPayload) => http.post<Task>('/tasks', payload),
  update: (id: string, payload: Partial<TaskPayload>) => http.patch<Task>(`/tasks/${id}`, payload),
  changeStatus: (id: string, status: TaskStatusStored, note?: string) =>
    http.post<Task>(`/tasks/${id}/status`, { status, note }),
  comment: (id: string, body: string) => http.post<TaskComment>(`/tasks/${id}/comments`, { body }),
  comments: (id: string) => http.get<TaskComment[]>(`/tasks/${id}/comments`),
  remove: (id: string) => http.delete<void>(`/tasks/${id}`),
  counts: () => http.get<Record<string, number>>('/tasks/status-counts'),
  overdueReport: () => http.get<{ items: OverdueRow[] }>('/tasks/overdue-report'),

  /** отметка «выполнено» текущего пользователя (исполнителя задачи) */
  markMyDone: (id: string) => http.post<Task>(`/tasks/${id}/my-mark`),
  clearMyMark: (id: string) => http.delete<Task>(`/tasks/${id}/my-mark`),

  uploadFile: (id: string, file: File) => {
    const form = new FormData()
    form.append('file', file)
    return http.upload<TaskDetail>(`/tasks/${id}/files`, form)
  },
  removeFile: (id: string, fileId: string) => http.delete<TaskDetail>(`/tasks/${id}/files/${fileId}`),
  fileDownloadPath: (id: string, fileId: string) => `/tasks/${id}/files/${fileId}/download`,
}

export interface OverdueRow {
  id: string
  title: string
  assignees: string[]
  assignee_ids: string[]
  deadline?: string | null
  overdue_by_days?: number | null
  status: string
  priority: string
}

export const plansApi = {
  list: (params: { status?: PlanStatus | ''; year?: number; page?: number; per_page?: number } = {}) =>
    http.get<Page<PlanListItem>>('/plans', params as QueryParams),
  detail: (id: string) => http.get<Plan>(`/plans/${id}`),
  current: () => http.get<Plan | null>('/plans/current'),
  create: (payload: PlanPayload) => http.post<Plan>('/plans', payload),
  update: (id: string, payload: Partial<PlanPayload>) => http.patch<Plan>(`/plans/${id}`, payload),
  publish: (id: string) => http.post<Plan>(`/plans/${id}/publish`),
  archive: (id: string) => http.post<Plan>(`/plans/${id}/archive`),
  remove: (id: string) => http.delete<void>(`/plans/${id}`),
}

export const usersApi = {
  list: (params: { search?: string; role?: Role | ''; is_active?: boolean; page?: number; per_page?: number } = {}) =>
    http.get<Page<User>>('/users', params as QueryParams),
  options: (role?: Role) => http.get<User[]>('/users/options', { role }),
  detail: (id: string) => http.get<User>(`/users/${id}`),
  create: (payload: {
    email: string
    password: string
    full_name: string
    role: Role
    position?: string
    phone?: string
  }) => http.post<User>('/users', payload),
  update: (
    id: string,
    payload: Partial<{
      full_name: string
      position: string
      phone: string
      email: string
      role: Role
      is_active: boolean
      password: string
    }>,
  ) => http.patch<User>(`/users/${id}`, payload),
  deactivate: (id: string) => http.delete<void>(`/users/${id}`),

  /** Active Directory: поиск в каталоге и импорт учётных записей. */
  adSearch: (q: string, limit = 50) => http.get<ADUser[]>('/users/ad/search', { q, limit }),
  adImport: (usernames: string[], role?: Role | null) =>
    http.post<ADImportResult>('/users/ad/import', { usernames, role: role ?? null }),
}

export const notificationsApi = {
  list: (params: { unread_only?: boolean; page?: number; per_page?: number } = {}) =>
    http.get<Page<AppNotification>>('/notifications', params as QueryParams),
  unreadCount: () => http.get<{ unread: number }>('/notifications/unread-count'),
  markRead: (id: string) => http.post<void>(`/notifications/${id}/read`),
  markAllRead: () => http.post<void>('/notifications/read-all'),
}

export const auditApi = {
  list: (
    params: {
      action?: string
      entity_type?: string
      actor_id?: string
      date_from?: string
      date_to?: string
      page?: number
      per_page?: number
    } = {},
  ) => http.get<Page<AuditEntry>>('/audit', params as QueryParams),
  actions: () => http.get<string[]>('/audit/actions'),
}

export const dashboardApi = {
  summary: () => http.get<Dashboard>('/dashboard'),
}

export const metaApi = {
  enums: () =>
    http.get<Record<string, { value: string; label: string }[]>>('/meta/enums'),
  permissions: () =>
    http.get<{ roles: string[]; capabilities: { capability: string; grants: Record<string, boolean> }[] }>(
      '/meta/permissions',
    ),
}
