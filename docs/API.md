# API SchoolHub

Базовый URL: `/api/v1` · Интерактивная документация: **`/docs`** (Swagger UI) и `/openapi.json`.

В таблице доступа: **В** = Владелец, **А** = Администрация, **У** = Учитель.
`—` означает, что запрос будет отклонён с `403`.

---

## 0. Первоначальная настройка

До создания первого Владельца **весь API закрыт** (`503 SETUP_REQUIRED`), кроме
`/health` и `/setup/*` — приложение невозможно использовать «вслепую», но и
посторонний не может назначить себя администратором: нужен одноразовый код из
журнала контейнера.

| Метод | Путь | Доступ | Назначение |
|---|---|---|---|
| `GET` | `/setup/status` | 🔓 | Требуется ли настройка; название школы; кто завершил настройку |
| `POST` | `/setup/first-owner` | 🔓 + код | Создать первого Владельца |
| `POST` | `/setup/token` | только `localhost` | Показать код повторно (со внешнего адреса — `403`) |
| `GET` | `/setup/info` | 🔓 | Режим работы: `app_env`, источник `SECRET_KEY`, включён ли LDAP |
| `GET` | `/health` | 🔓 | Healthcheck |

**Запрос** `POST /setup/first-owner`

```json
{
  "setup_token": "VW88DT6V",
  "email": "admin@school.local",
  "password": "Школа2026!",
  "full_name": "Соколова Ирина Аркадьевна",
  "school_name": "ГБОУ Школа № 1472"
}
```

**Ответ 201** — карточка созданного Владельца (`role: "OWNER"`, `auth_source: "local"`),
после чего API немедленно разблокируется. Ошибки: `403` — неверный код/слабые данные,
`409` — система уже настроена (настройка выполняется один раз), `422` — пароль короче 8 символов.

Код настройки генерируется при первом старте (8 символов без неоднозначных знаков) и
печатается в журнал контейнера. Альтернатива без браузера:

```bash
docker exec -it schoolhub-backend python -m scripts.first_owner     --email admin@school.local --password 'Пароль12345' --name 'Администратор школы'
```

---

## 1. Аутентификация

| Метод | Путь | В | А | У | Назначение |
|---|---|:--:|:--:|:--:|---|
| `POST` | `/auth/login` | ✅ | ✅ | ✅ | Вход: **e-mail или доменная учётка** + пароль → access в теле, refresh в httpOnly-cookie |
| `GET` | `/auth/login-options` | 🔓 | 🔓 | 🔓 | Публично: включён ли вход через домен, подсказка о формате логина |
| `GET` | `/auth/ad/diagnostics` | ✅ | ✅ | — | Диагностика подключения к AD (конфиг без секретов + ping DC) |
| `POST` | `/auth/refresh` | ✅ | ✅ | ✅ | Обмен refresh-cookie на новый access **с ротацией** refresh |
| `GET` | `/auth/me` | ✅ | ✅ | ✅ | Профиль + `capabilities` (права для UI) |
| `POST` | `/auth/change-password` | ✅ | ✅ | ✅ | Смена пароля **локальной** учётки (для доменных — `403`); отзывает все сессии |
| `POST` | `/auth/logout` | ✅ | ✅ | ✅ | Выход: **отзыв refresh-сессии** на сервере + удаление cookie + запись в журнале |

**Запрос** `POST /auth/login`

```json
{ "email": "owner@schoolhub.ru", "password": "Demo1234!", "remember": true }
```

`remember: true` (по умолчанию) — refresh-cookie живёт 14 дней (`Max-Age`);
`false` — cookie сессионная и умирает при закрытии браузера.

Поле `email` принимает и **доменный логин** (если включена интеграция с AD):
`ivanov`, `ivanov@school.local`, `SCHOOL\ivanov`. Значение проходит строгую
валидацию набора символов и дополнительно экранируется перед попаданием в LDAP-фильтр.

**Ответ `GET /auth/login-options`** (без авторизации — используется экраном входа):

```json
{
  "ldap_enabled": true,
  "local_enabled": true,
  "login_hint": "Доменная учётная запись: ivanov или ivanov@school.local",
  "password_managed_by": "Active Directory"
}
```

**Ответ `GET /auth/ad/diagnostics`** (OWNER/ADMIN):

```json
{
  "config": { "server": "dc01.school.local:636", "ssl": true, "base_dn": "DC=school,DC=local",
              "bind_dn": "CN=svc_schoolhub,…", "bind_password_set": true,
              "allowed_groups": ["SchoolStaff"], "admin_groups": ["SchoolAdmins"], "…": "…" },
  "problems": ["Не задан LDAP_CA_CERT — сертификат DC не будет проверен"],
  "ping": { "ok": true, "server": "dc01.school.local:636" },
  "requested_by": "admin@school.local"
}
```

Значение пароля сервисной учётки в ответ **не попадает** — только признак `bind_password_set`.

**Ответ 200** (refresh-токен в теле **не отдаётся** — он приходит в `Set-Cookie`)

```json
{ "access_token": "eyJhbGciOiJIUzI1NiIs…", "token_type": "bearer", "expires_in": 1800 }
```

```
Set-Cookie: schoolhub_refresh=eyJhbGci…; HttpOnly; Max-Age=1209600; Path=/api/v1/auth; SameSite=strict
```

`Secure` добавляется при `COOKIE_SECURE=true` (работа по HTTPS). `Path=/api/v1/auth`
ограничивает круг эндпоинтов, которым браузер отправляет cookie.

**Ответ `GET /auth/me`**

```json
{
  "id": "8b1c…", "email": "ivanov@schoolhub.ru",
  "full_name": "Иванов Пётр Сергеевич", "position": "Учитель математики",
  "role": "TEACHER", "is_active": true,
  "capabilities": ["orders:read", "orders:ack", "tasks:read-own", "plans:read"]
}
```

Токены: access — 30 минут (в SPA живёт только в памяти вкладки), refresh — 14 дней
(httpOnly-cookie); различаются claim'ом `typ`, каждый имеет `jti`.
Заголовок авторизации: `Authorization: Bearer <access_token>`.

Ошибки: `401` — неверная пара или истёк токен (сообщение одинаковое для «нет такого e-mail»
и «неверный пароль»), `403` — учётная запись заблокирована.

### Refresh-сессии: ротация и отзыв (v1.3)

Каждый выданный refresh-токен — строка `refresh_sessions` (`jti` уникален, `family_id`
объединяет токены одного входа). Правила:

* `POST /auth/refresh` **ротирует** токен: предъявленный `jti` помечается `superseded_at`,
  в ответе приходит новый access и новая cookie;
* предъявление уже заменённого токена **вне льготного окна** (`REFRESH_REUSE_GRACE_SEC`,
  по умолчанию 30 с — запас для гонок параллельных вкладок) трактуется как кража:
  всё семейство отзывается, в журнал пишется `TOKEN_REUSE_DETECTED`, ответ `401`;
* `POST /auth/logout` отзывает семейство предъявленной cookie;
* смена собственного пароля, сброс пароля администрацией и блокировка учётки
  отзывают **все** refresh-сессии пользователя (`revocation_reason` фиксирует причину);
* заблокированный пользователь дополнительно получает `403` на любой запрос с валидным
  access-токеном — `is_active` проверяется на каждом запросе.

Ошибки refresh: `401` — cookie отсутствует, токен неизвестен/отозван/истёк/ротация
скомпрометирована; ответ всегда без подробностей, пригодных для перечисления.

---

## 2. Приказы

| Метод | Путь | В | А | У | Назначение |
|---|---|:--:|:--:|:--:|---|
| `GET` | `/orders` | ✅ | ✅ | ✅¹ | Реестр с фильтрами и пагинацией |
| `POST` | `/orders` | ✅ | ✅ | — | Создать черновик (`require_all` либо `recipient_ids`) |
| `GET` | `/orders/{id}` | ✅ | ✅ | ✅¹ | Карточка приказа |
| `PATCH` | `/orders/{id}` | ✅ | ✅ | — | Редактировать (кроме архивных) |
| `POST` | `/orders/{id}/publish` | ✅ | ✅ | — | Опубликовать (нужен файл; `?user_ids=` — явный круг) |
| `POST` | `/orders/{id}/archive` | ✅ | ✅ | — | В архив (read-only) |
| `DELETE` | `/orders/{id}` | ✅ | ✅ | — | Удалить **черновик** |
| `POST` | `/orders/{id}/files` | ✅ | ✅ | — | Загрузить PDF/DOCX (новая версия) |
| `DELETE` | `/orders/{id}/files/{file_id}` | ✅ | ✅ | — | Удалить файл черновика |
| `GET` | `/orders/{id}/file` | ✅ | ✅ | ✅¹ | Скачать/посмотреть документ |
| `GET` | `/orders/{id}/preview` | ✅ | ✅ | ✅¹ | Метаданные превью (`inline`/`download`) |
| `POST` | `/orders/{id}/acknowledgements` | ✅ | ✅ | ✅ | **Подтвердить ознакомление** |
| `GET` | `/orders/{id}/acknowledgements` | ✅ | ✅ | — | Лист ознакомления |
| `GET` | `/orders/{id}/ack-summary` | ✅ | ✅ | — | Прогресс + список неподписавших |
| `PUT` | `/orders/{id}/recipients` | ✅ | ✅ | — | Изменить круг ознакомления (подписи сохраняются) |
| `GET` | `/orders/export/ack-sheet.csv` | ✅ | ✅ | — | Выгрузка листа в CSV |

¹ Учитель видит только приказы в статусе `PUBLISHED`; запрос черновика/архива → `403`,
фильтр `status` для учителя отклоняется с `403`.

**Круг ознакомления** задаётся ещё в черновике: `require_all: true` (все активные сотрудники,
кроме Владельца) либо `require_all: false` + `recipient_ids: [uuid…]` (сохраняется на приказе
и применяется при публикации). После публикации круг меняется через `PUT /{id}/recipients`:
добавленные получают уведомление и строку «Не ознакомлен», неподписавшие убираются из листа,
уже подтверждённые подписи сохраняются. Подтверждение ознакомления сотрудником вне круга → `409`.

### Параметры `GET /orders`

| Параметр | Тип | Описание |
|---|---|---|
| `search` | string | Поиск по номеру, заголовку, описанию (регистронезависимый, Unicode) |
| `order_type` | enum | `HR`, `STUDENTS`, `EDUCATION`, `SAFETY`, `ADMIN`, `OTHER` |
| `status` | enum | `DRAFT`, `PUBLISHED`, `ARCHIVED` — только В/А |
| `date_from`, `date_to` | date | Период по дате приказа (`YYYY-MM-DD`) |
| `ack` | enum | `pending` / `acknowledged` — для В/А «есть неподписанные», для У — «мои» |
| `mine_pending` | bool | Только приказы, где я ещё не поставил подпись |
| `page`, `per_page` | int | Пагинация (по умолчанию 1 и 20, максимум 100) |

### Ответ `GET /orders` (фрагмент)

```json
{
  "items": [
    {
      "id": "0d0a…", "number": "112-к", "order_year": 2026,
      "title": "О приёме на работу и распределении учебной нагрузки",
      "order_type": "HR", "status": "PUBLISHED",
      "issued_on": "2026-10-03", "ack_deadline": "2026-10-17",
      "current_file": { "id": "a1…", "original_name": "prikaz_112-k.pdf",
                        "mime_type": "application/pdf", "size_bytes": 54298, "version": 1, "is_current": true },
      "ack_total": 6, "ack_done": 2,
      "my_ack": { "status": "PENDING", "acknowledged_at": null, "user": { "id": "…", "full_name": "…" } },
      "can_manage": false
    }
  ],
  "total": 4, "page": 1, "per_page": 20, "pages": 1
}
```

### Подтверждение ознакомления

`POST /orders/{id}/acknowledgements`

```json
{ "comment": "Ознакомлен, принято к исполнению" }
```

Ответ `200` — запись листа ознакомления со служебными полями:

```json
{
  "id": "…", "status": "ACKNOWLEDGED",
  "acknowledged_at": "2026-10-12T08:15:03.112155Z",
  "comment": "Ознакомлен, принято к исполнению",
  "ip_address": "10.0.12.34",
  "user": { "id": "…", "email": "ivanov@schoolhub.ru", "full_name": "Иванов Пётр Сергеевич" }
}
```

Ошибки: `409` — уже подтверждено ранее, приказ в архиве, или сотрудник не входит в круг
ознакомления; `403` — приказ не опубликован (для учителя).

### Загрузка документа

`POST /orders/{id}/files` — `multipart/form-data`, поле `file`.

Ограничения: `application/pdf`, `application/vnd.openxmlformats-officedocument.wordprocessingml.document`,
`application/msword`; до 25 МБ; пустой файл отклоняется. Каждый вызов создаёт **новую версию**
(`version`, `is_current`), предыдущие сохраняются вместе с sha256.

```bash
curl -X POST http://localhost:8000/api/v1/orders/$ORDER_ID/files \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@prikaz.pdf;type=application/pdf"
```

### Жизненный цикл приказа

```
DRAFT ──publish──► PUBLISHED ──archive──► ARCHIVED
   │                    │
   └──delete (можно)    └── редактирование и новые версии файла (можно)
```

* публикация без загруженного документа → `409`;
* архивный приказ нельзя редактировать, догружать файлы и собирать подписи → `409`;
* удалить можно только черновик, опубликованный приказ — только в архив (требование к archivability).

---

## 3. Задачи

| Метод | Путь | В | А | У | Назначение |
|---|---|:--:|:--:|:--:|---|
| `GET` | `/tasks` | ✅ все | ✅ все | ✅ свои | Список с фильтрами + `status_counts` |
| `POST` | `/tasks` | ✅ | ✅ | — | Создать задачу (несколько исполнителей) |
| `GET` | `/tasks/status-counts` | ✅ | ✅ | ✅ (свои) | Счётчики по статусам, включая `OVERDUE` |
| `GET` | `/tasks/overdue-report` | ✅ | ✅ | — | Отчёт по просрочкам (в разрезе исполнителей) |
| `GET` | `/tasks/{id}` | ✅ | ✅ | ✅² | Карточка: исполнители с отметками, файлы, комментарии, история |
| `PATCH` | `/tasks/{id}` | ✅ | ✅ | ✅³ | Обновить задачу (`assignee_ids` — список) |
| `POST` | `/tasks/{id}/status` | ✅ | ✅ | ✅³ | Смена статуса (state machine) |
| `POST` | `/tasks/{id}/my-mark` | ✅⁴ | ✅⁴ | ✅⁴ | **Отметка «выполнено»** (своя часть задачи) |
| `DELETE` | `/tasks/{id}/my-mark` | ✅⁴ | ✅⁴ | ✅⁴ | Снять свою отметку |
| `POST` | `/tasks/{id}/files` | ✅ | ✅ | ✅² | Прикрепить вложение (офис/изображения/архивы, ≤25 МБ) |
| `GET` | `/tasks/{id}/files/{file_id}/download` | ✅ | ✅ | ✅² | Скачать вложение |
| `DELETE` | `/tasks/{id}/files/{file_id}` | ✅ | ✅ | ✅⁵ | Удалить вложение |
| `POST` | `/tasks/{id}/comments` | ✅ | ✅ | ✅² | Комментарий |
| `GET` | `/tasks/{id}/comments` | ✅ | ✅ | ✅² | Список комментариев |
| `DELETE` | `/tasks/{id}` | ✅ | ✅ | — | Удалить задачу |

² Только если сотрудник — исполнитель или постановщик задачи; иначе `403`.
³ Учитель может менять **только** `description` и `status`; попытка изменить `assignee_ids`,
`deadline`, `priority` или `title` → `403`.
⁴ Только исполнитель задачи; иначе `403`. Повторная отметка → `409`.
⁵ Загрузивший файл, постановщик задачи или администрация.

### Отметки «выполнено» (несколько исполнителей)

У задачи может быть несколько исполнителей (`assignee_ids`), у каждого — своя отметка
(`task_assignees.done_at`). Автоматика статусов:

* первая отметка (задача `NEW`) → `IN_PROGRESS`;
* отметки поставили **все** исполнители → `DONE` (`completed_at` заполняется, постановщик
  получает уведомление «все исполнители отметились»);
* снятие отметки у закрытой задачи → `IN_PROGRESS` (`completed_at` очищается).

Администрация по-прежнему может менять статус вручную (state machine) — включая досрочное
закрытие задачи. Ответ элемента списка содержит `assignees[]` (с `done_at` каждого),
`marks_done`, `can_mark`, `my_done`, `files_count`.

### Параметры `GET /tasks`

| Параметр | Тип | Описание |
|---|---|---|
| `status` | enum | `NEW`, `IN_PROGRESS`, `DONE`, `OVERDUE` (вычисляемый) |
| `assignee_id` | uuid | Фильтр по исполнителю (учитель может передать только свой id) |
| `creator_id` | uuid | Фильтр по постановщику |
| `priority` | enum | `LOW`, `NORMAL`, `HIGH`, `URGENT` |
| `search` | string | По названию и описанию |
| `due_before`, `due_after` | datetime | Окно по дедлайну (ISO 8601) |
| `sort` | enum | `deadline` (по умолчанию), `created`, `priority`, `title`, `updated` |
| `order` | enum | `asc` / `desc` |
| `page`, `per_page` | int | Пагинация |

### Статусы

| Значение | Хранится в БД | Смысл |
|---|:--:|---|
| `NEW` | ✅ | Новая |
| `IN_PROGRESS` | ✅ | В работе |
| `DONE` | ✅ | Выполнена (`completed_at` заполняется автоматически) |
| `OVERDUE` | ⛔ вычисляется | `status != DONE AND deadline < now()` — отдаётся в `effective_status` |

Разрешённые переходы: `NEW → IN_PROGRESS | DONE`, `IN_PROGRESS → DONE | NEW`, `DONE → IN_PROGRESS`.
Прочие переходы → `409`. Просроченная задача остаётся в своём хранимом статусе, но в ответах
приходит `effective_status: "OVERDUE"`, `is_overdue: true`, `days_left: -2`.

### Пример ответа элемента списка

```json
{
  "id": "…", "title": "Подготовить кабинет №12 к проверке",
  "status": "NEW", "effective_status": "OVERDUE", "priority": "URGENT",
  "deadline": "2026-10-11T14:00:00Z", "is_overdue": true, "days_left": -1,
  "assignees": [
    { "id": "…", "done_at": null, "user": { "id": "…", "full_name": "Иванов Пётр Сергеевич", "role": "TEACHER" } },
    { "id": "…", "done_at": null, "user": { "id": "…", "full_name": "Смирнов Алексей Игоревич", "role": "TEACHER" } }
  ],
  "marks_done": 0, "my_done": false, "can_mark": true, "files_count": 1,
  "creator": { "id": "…", "full_name": "Гаврилов Сергей Николаевич", "role": "ADMIN" },
  "can_edit": true
}
```

---

## 4. План работы на неделю

Электронный аналог школьного Word-документа «План работы ДД.ММ–ДД.ММ». Один план на неделю
(`week_start` — понедельник, уникален). Содержимое — структурированный JSON-документ `content`:
дежурный класс (`duty`), строки шапки (`notes`), блоки «в течение месяца/недели»
(`month_items`, `week_items`), мероприятия по дням пн–сб (`days[].events[]`).
Ответственные (`resp`, `duty.teacher_id`) — UUID сотрудников, в ответах отдаются карточками `User`.

| Метод | Путь | В | А | У | Назначение |
|---|---|:--:|:--:|:--:|---|
| `GET` | `/plans` | ✅ все | ✅ все | ✅ без черновиков | Список планов (`status`, `year`, пагинация) |
| `GET` | `/plans/current` | ✅ | ✅ | ✅ | План текущей недели (или последний опубликованный) |
| `POST` | `/plans` | ✅ | ✅ | — | Создать черновик (`week_start` — обязательно понедельник) |
| `GET` | `/plans/{id}` | ✅ | ✅ | ✅⁶ | Документ целиком (+ `events_total`, `my_items`) |
| `PATCH` | `/plans/{id}` | ✅ | ✅ | — | Изменить (не архив); можно перенести неделю |
| `POST` | `/plans/{id}/publish` | ✅ | ✅ | — | Опубликовать: уведомление всем ответственным |
| `POST` | `/plans/{id}/archive` | ✅ | ✅ | — | В архив (read-only) |
| `DELETE` | `/plans/{id}` | ✅ | ✅ | — | Удалить **черновик** |

⁶ Учитель получает `403` на черновик. Дубли недели → `409`; пустой план не публикуется → `400`;
не-понедельник в `week_start` → `422`; несуществующий/заблокированный ответственный → `400`.

**Запрос** `POST /plans` (фрагмент)

```json
{
  "week_start": "2026-10-12",
  "content": {
    "duty": { "klass": "9 «Б»", "teacher_id": "…" },
    "notes": ["В столовой дежурят 7-ые классы."],
    "month_items": [{ "text": "Контроль адаптации 1-х классов.", "resp": ["…"] }],
    "week_items": [{ "text": "Школьный этап ВсОШ.", "place": "Кабинеты", "resp": ["…"] }],
    "days": [
      { "date": "2026-10-12", "events": [
        { "title": "«Разговоры о важном».", "time": "08.00", "place": "Кл. каб.", "resp": ["…"] }
      ]}
    ]
  }
}
```

---

## 5. Пользователи

| Метод | Путь | В | А | У | Назначение |
|---|---|:--:|:--:|:--:|---|
| `GET` | `/users` | ✅ все | ✅ без Владельца | — | Список с поиском и фильтром по роли |
| `GET` | `/users/options` | ✅ | ✅ | — | Компактный список для селектов (исполнители) |
| `GET` | `/users/{id}` | ✅ | ✅ (не Владельца) | — | Карточка |
| `POST` | `/users` | ✅ любая роль | ⚠️ только `TEACHER` | — | Создать учётную запись |
| `PATCH` | `/users/{id}` | ✅ | ⚠️ только Учителя | — | Изменить данные/роль/активность/пароль |
| `DELETE` | `/users/{id}` | ✅ | — | — | Заблокировать (мягкое удаление) |
| `GET` | `/users/ad/search?q=` | ✅ | ✅ | — | Поиск пользователей в каталоге домена |
| `POST` | `/users/ad/import` | ✅ | ⚠️ роль ≤ своей | — | Импорт учётных записей из AD (до их первого входа) |

**Поля доменной интеграции** в ответах `/users*` и `/auth/me`:
`auth_source` (`local` / `ldap`), `domain_account` (sAMAccountName), `ad_groups`
(список групп AD), `last_ad_sync_at`.

**Запрос** `POST /users/ad/import`

```json
{ "usernames": ["zavuch", "ivanov"], "role": "ADMIN" }
```

**Ответ 200**

```json
{ "created": ["zavuch@school.local"], "skipped": ["ivanov"], "failed": [], "total": 1 }
```

Гарантии целостности:

* свою роль и свою активность изменить нельзя (`409`);
* в школе всегда остаётся хотя бы один активный Владелец (`409`);
* Администрация не может выдать роль `ADMIN`/`OWNER` и не видит учётку Владельца (`403`);
* e-mail уникален (`409` при дубликате); пароль — от 8 символов;
* для учётки с `auth_source=ldap` смена/установка пароля невозможна (`409`) — им управляет AD;
* импорт из AD идемпотентен: существующие учётки попадают в `skipped`, дубли внутри
  одного запроса игнорируются; роль выше собственной назначить нельзя (`403`).

---

## 6. Уведомления, журнал, дашборд, справочники

| Метод | Путь | В | А | У | Назначение |
|---|---|:--:|:--:|:--:|---|
| `GET` | `/notifications` | ✅ | ✅ | ✅ | Мои уведомления (фильтр `unread_only`) |
| `GET` | `/notifications/unread-count` | ✅ | ✅ | ✅ | Счётчик для бейджа |
| `POST` | `/notifications/{id}/read` | ✅ | ✅ | ✅ | Отметить прочитанным |
| `POST` | `/notifications/read-all` | ✅ | ✅ | ✅ | Отметить все |
| `GET` | `/audit` | ✅ | ✅ | — | Журнал: `action`, `entity_type`, `actor_id`, период |
| `GET` | `/audit/actions` | ✅ | ✅ | — | Справочник действий для фильтра |
| `GET` | `/dashboard` | ✅ | ✅ | ✅ | Сводка: `scope=global` для В/А, `personal` для У |
| `GET` | `/meta/enums` | ✅ | ✅ | ✅ | Справочники со значениями и подписями на русском |
| `GET` | `/meta/permissions` | ✅ | ✅ | ✅ | Матрица «возможность × роль» |
| `GET` | `/health` | 🔓 | 🔓 | 🔓 | Healthcheck (без авторизации) |

Типы уведомлений: `ORDER_PUBLISHED`, `ORDER_UPDATED`, `ORDER_ACK_DEADLINE`,
`TASK_ASSIGNED`, `TASK_STATUS_CHANGED`, `TASK_MARK`, `TASK_COMMENT`,
`PLAN_PUBLISHED`, `PLAN_UPDATED`. `entity_type` уведомления: `order` | `task` | `plan`.

Действия журнала: `LOGIN`, `LOGIN_FAILED`, `LOGOUT`, `PASSWORD_CHANGE`, `ORDER_CREATE`,
`ORDER_UPDATE`, `ORDER_PUBLISH`, `ORDER_ARCHIVE`, `ORDER_DELETE`, `ORDER_FILE_UPLOAD`,
`ORDER_FILE_DELETE`, `ORDER_ACK`, `ORDER_RECIPIENTS`, `TASK_CREATE`, `TASK_UPDATE`,
`TASK_STATUS`, `TASK_MARK`, `TASK_FILE`, `TASK_FILE_DELETE`, `TASK_DELETE`,
`PLAN_CREATE`, `PLAN_UPDATE`, `PLAN_PUBLISH`, `PLAN_ARCHIVE`, `PLAN_DELETE`,
`USER_CREATE`, `USER_UPDATE`, `USER_DEACTIVATE`, `TOKEN_REUSE_DETECTED`, `SYSTEM_SEED`.

Дашборд (`GET /dashboard`) дополнительно возвращает `current_plan` — план текущей недели
(или последний опубликованный) для виджета на главной.

---

## 7. Формат ошибок

```json
{ "detail": "Недостаточно прав", "code": "FORBIDDEN" }
```

| HTTP | Когда |
|---|---|
| `400` | Неверные данные или файл (MIME, размер, пустой файл, `date_from > date_to`) |
| `401` | Нет/истёк/неверный токен; неверный пароль (локальный или доменный) |
| `403` | Недостаточно прав (роль или точечное правило доступа) |
| `404` | Сущность не найдена |
| `409` | Конфликт: дубликат номера приказа, повторное ознакомление, недопустимый переход статуса, защита единственного Владельца |
| `422` | Ошибка валидации схемы (сообщения собираются в одну строку) |
| `429` | Превышен лимит неудачных попыток входа (защита доменных учёток от блокировки) |
| `503` | Контроллер домена недоступен (`code: AD_ERROR`) |
| `500` | Внутренняя ошибка (детали — только в логах сервера) |

---

## 8. Пример сквозного сценария (bash)

```bash
API=http://localhost:8000/api/v1

# 1) вход администрации
TOKEN=$(curl -s -X POST $API/auth/login -H 'Content-Type: application/json' \
  -d '{"email":"admin@schoolhub.ru","password":"Demo1234!"}' | python3 -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')
AUTH="Authorization: Bearer $TOKEN"

# 2) черновик приказа
ORDER=$(curl -s -X POST $API/orders -H "$AUTH" -H 'Content-Type: application/json' -d '{
  "number":"900-к","order_year":2026,"title":"О проведении педсовета",
  "order_type":"EDUCATION","issued_on":"2026-10-12","ack_deadline":"2026-10-20"}' \
  | python3 -c 'import sys,json;print(json.load(sys.stdin)["id"])')

# 3) загрузка PDF и публикация
curl -s -X POST $API/orders/$ORDER/files -H "$AUTH" -F "file=@prikaz.pdf;type=application/pdf" > /dev/null
curl -s -X POST $API/orders/$ORDER/publish -H "$AUTH" | python3 -m json.tool | head -8

# 4) учитель подтверждает ознакомление
TT=$(curl -s -X POST $API/auth/login -H 'Content-Type: application/json' \
  -d '{"email":"ivanov@schoolhub.ru","password":"Demo1234!"}' | python3 -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')
curl -s -X POST $API/orders/$ORDER/acknowledgements -H "Authorization: Bearer $TT" \
  -H 'Content-Type: application/json' -d '{"comment":"Ознакомлен"}' | python3 -m json.tool

# 5) лист ознакомления глазами администрации
curl -s "$API/orders/$ORDER/ack-summary" -H "$AUTH" | python3 -m json.tool
```

---

## 9. Версии и совместимость

* Версия API зашита в префикс `/api/v1`; breaking-изменения — только в новом префиксе.
* OpenAPI-схема генерируется из кода (`app.openapi()`), поэтому документация не расходится с реализацией.
* Клиентский контракт продублирован в `frontend/src/types.ts`; при изменении схем его нужно синхронизировать
  (в перспективе — генерация `openapi-typescript`).
