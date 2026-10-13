/** Профиль: данные учётной записи и набор прав роли.
 *  v1.2: смена пароля из профиля убрана — пароль выдаёт администратор при создании
 *  учётки и сбрасывает его в разделе «Пользователи» (для доменных учёток — в AD). */
import { useQuery } from '@tanstack/react-query'

import { metaApi } from '@/api/endpoints'
import { qk } from '@/api/query'
import { Avatar, Badge, Section } from '@/components/ui'
import { CAP, ROLE_LABEL } from '@/lib/permissions'
import { formatDateTime } from '@/lib/format'
import { authStore, useAuthStore } from '@/store/auth'

const CAPTION: Record<string, string> = {
  [CAP.ordersRead]: 'Просмотр опубликованных приказов',
  [CAP.ordersManage]: 'Создание и редактирование приказов, загрузка документов',
  [CAP.ordersAck]: 'Подтверждение ознакомления с приказами',
  [CAP.ordersAckReport]: 'Лист ознакомления и выгрузка в CSV',
  [CAP.tasksReadOwn]: 'Просмотр только своих задач',
  [CAP.tasksReadAll]: 'Просмотр всех задач школы',
  [CAP.tasksCreate]: 'Создание задач',
  [CAP.tasksAssign]: 'Назначение исполнителей и дедлайна',
  [CAP.tasksDelete]: 'Удаление задач',
  [CAP.plansRead]: 'Просмотр планов работы на неделю',
  [CAP.plansManage]: 'Создание, публикация и архивирование планов работы',
  [CAP.usersRead]: 'Просмотр справочника сотрудников',
  [CAP.usersManage]: 'Создание и редактирование учётных записей',
  [CAP.usersManageAdmins]: 'Управление администраторами и владельцем',
  [CAP.auditRead]: 'Чтение журнала событий',
  [CAP.dashboardGlobal]: 'Сводка по всей школе',
}

export function ProfilePage() {
  const user = useAuthStore((s) => s.user)!

  const { data: matrix } = useQuery({
    queryKey: qk('/meta/permissions'),
    queryFn: metaApi.permissions,
  })

  const allCaps = matrix?.capabilities.map((c) => c.capability) ?? Object.keys(CAPTION)
  const isLdap = user.auth_source === 'ldap'

  return (
    <div className="stack" style={{ gap: 16 }}>
      <div className="page-head">
        <div className="page-head__text">
          <h1>Мой профиль</h1>
          <div className="page-head__hint">Данные учётной записи и права, назначенные вашей ролью.</div>
        </div>
      </div>

      <div className="grid grid--2" style={{ alignItems: 'start' }}>
        <Section title="Учётная запись">
          <div className="row" style={{ gap: 14 }}>
            <Avatar name={user.full_name} size="lg" />
            <div>
              <div style={{ fontSize: 17, fontWeight: 650 }}>{user.full_name}</div>
              <div className="small muted">{user.position ?? 'должность не указана'}</div>
              <div style={{ marginTop: 6 }}>
                <Badge tone="brand">{ROLE_LABEL[user.role]}</Badge>
              </div>
            </div>
          </div>
          <dl className="stack" style={{ gap: 8, margin: '16px 0 0' }}>
            <Info label="E-mail" value={user.email} />
            <Info label="Телефон" value={user.phone ?? '—'} />
            <Info label="Роль в системе" value={ROLE_LABEL[user.role]} />
            <Info
              label="Источник учётки"
              value={isLdap ? `Active Directory${user.domain_account ? ` (${user.domain_account})` : ''}` : 'локальная (SchoolHub)'}
            />
            <Info label="Учётная запись" value={user.is_active ? 'активна' : 'заблокирована' } />
          </dl>
        </Section>

        {isLdap ? (
          <Section title="Пароль домена">
            <div className="stack" style={{ gap: 10 }}>
              <div className="alert alert--info small">
                Вы входите под доменной учётной записью{' '}
                <strong className="mono">{user.domain_account ?? user.email}</strong>. Пароль управляется
                в Active Directory: смените его комбинацией <strong>Ctrl+Alt+Del → «Сменить пароль»</strong>{' '}
                на рабочем компьютере или обратитесь к администратору домена.
              </div>
              {user.ad_groups && user.ad_groups.length > 0 && (
                <div>
                  <div className="field__label" style={{ marginBottom: 6 }}>Группы Active Directory</div>
                  <div className="row" style={{ gap: 6 }}>
                    {user.ad_groups.slice(0, 12).map((g) => (
                      <Badge key={g} tone="muted">{g}</Badge>
                    ))}
                    {user.ad_groups.length > 12 && <span className="tiny muted">+{user.ad_groups.length - 12}</span>}
                  </div>
                </div>
              )}
              {user.last_ad_sync_at && (
                <div className="tiny muted">Данные синхронизированы с AD: {formatDateTime(user.last_ad_sync_at)}</div>
              )}
            </div>
          </Section>
        ) : (
          <Section title="Пароль">
            <div className="alert alert--info small">
              Пароль локальной учётной записи выдаёт администратор при её создании. Если пароль нужно
              сбросить — обратитесь к администратору: он сделает это в разделе <strong>«Пользователи»</strong>.
            </div>
          </Section>
        )}
      </div>

      <Section title="Ваши права (capabilities)">
        <p className="small muted">
          Набор прав приходит с сервера вместе с профилем и управляет интерфейсом. Фактические проверки
          выполняются на API — даже при подмене клиента сервер вернёт 403.
        </p>
        <div className="grid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 8 }}>
          {allCaps.map((cap) => {
            const granted = user.capabilities.includes(cap)
            return (
              <div key={cap} className="row" style={{ gap: 8, padding: '7px 10px', borderRadius: 8, background: granted ? 'var(--ok-bg)' : 'var(--muted-bg)' }}>
                <span>{granted ? '✅' : '⛔'}</span>
                <div className="grow">
                  <div className="small strong">{CAPTION[cap] ?? cap}</div>
                  <div className="tiny muted mono">{cap}</div>
                </div>
              </div>
            )
          })}
        </div>
      </Section>

      <Section title="Сессия">
        <div className="row small muted">
          <span>Выход завершает сессию на этом устройстве: токены удаляются, событие пишется в журнал.</span>
          <span className="grow" />
          <button className="btn btn--sm" onClick={() => void authStore.logout()}>🚪 Выйти</button>
        </div>
      </Section>
    </div>
  )
}

function Info({ label, value }: { label: string; value: string }) {
  return (
    <div className="row" style={{ gap: 10 }}>
      <dt className="small muted" style={{ flex: '0 0 150px' }}>{label}</dt>
      <dd className="small strong" style={{ margin: 0, flex: 1 }}>{value}</dd>
    </div>
  )
}
