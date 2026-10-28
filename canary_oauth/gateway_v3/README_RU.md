# C-Lab OAuth Gateway V1 — standalone, fail-closed read-only bridge

**Состояние на 28.10.2026: PrototypeCandidate / локальные интеграционные тесты PASS; НЕ production и НЕ сертификат реального Google OAuth.**

Gateway выступает одновременно OAuth 2.1 authorization server и MCP protected resource server. ChatGPT подключается к собственному issuer Gateway, а Gateway сам выполняет Google Authorization Code + S256 PKCE и запрашивает `access_type=offline`. При отсутствии Google refresh token выдача gateway-токенов запрещена. Для ChatGPT выпускаются собственные 5-минутные access tokens и 30-дневные rotating refresh tokens. Доступ к Google продлевается на сервере независимо, с шифрованным хранением Google refresh token.

## Изоляция

* Проект не меняет `c-lab-gcp-control`, C-Fabric или производственные инструменты. Входящий MCP предоставляет ТОЛЬКО `get_control_health`, `get_controller_status`, `get_fabric_health`; write-инструменты отвергаются до обращения к upstream.
* Upstream endpoint в production **прибит** к `https://c-lab-gcp-control-w7neqnzura-ew.a.run.app/mcp`. Не принимает произвольные URLs, tool names или аргументы.
* Google user допускается только по явно заданному email; OIDC `id_token` проверяется по подписи, audience, issuer, nonce, `email_verified`, sub.
* Каждая OAuth-транзакция одноразовая, в БД зашифрована, имеет TTL; client_id (ChatGPT CIMD), redirect и resource строго сверяются.
* Production **требует PostgreSQL**, секретный ключ Fernet, Google client secret, HTTPS base URL. Нет неявного SQLite или mock fallback.
* Токены gateway хранятся только в виде SHA-256, Google токены — как Fernet ciphertext. Предусмотрена реакция на повтор старого refresh: грант полностью отзывается.
* Таблицы production создаются ТОЛЬКО отдельной управляемой миграцией `python -m gateway.migrate`, не при каждом запуске.

## Запуск локального тестового корпуса

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt 'pytest>=8,<10'
PYTHONPATH=. pytest -q
```

Значения `tests/conftest.py` — исключительно фиктивные; они **не являются** действующими OAuth учётными данными.

## Декларация OAuth discovery

```
GET /.well-known/oauth-protected-resource
GET /.well-known/oauth-authorization-server
GET /authorize
GET /google/callback
POST /token
POST /revoke
POST /mcp
GET /health
```

Для ChatGPT используется CIMD `https://chatgpt.com/oauth/client.json`, `token_endpoint_auth_methods_supported:["none"]`, PKCE S256 и возвращаемый в authorization response `iss` (точное совпадение issuer). Redirect URI задаётся явным allowlist `CHATGPT_REDIRECT_URIS` по реальным данным регистрации; значение по умолчанию — исторический `https://chatgpt.com/connector_platform_oauth_redirect`, не доказательство его применимости к новому Gateway. Resource: `https://<gateway-host>/mcp`.

## Требуемые production-предпосылки

1. **Отдельная действующая PostgreSQL**, с TLS/приватным сетевым маршрутом, отдельной ролью, бэкапом и доступом к `migrate`. Без PostgreSQL deployment STOP.
2. **Новый HTTPS Gateway origin** и точный DNS/TLS сертификат. Новое значение `https://<gateway>/google/callback` должно быть разрешено в **существующем Google OAuth Web Client** или в отдельном одобренном тестовом Web Client. Без зарегистрированного redirect Google отклонит code exchange.
3. Google OAuth Client Secret и ключ Fernet — только Secret Manager и минимальный доступ тестовой service identity. Не записывать значения в ZIP, GitHub, `gcloud --set-env-vars`, чат или логи.
4. Утверждённый пользователь Google `ALLOWED_GOOGLE_EMAIL` (только в конфигурации среды). Не открывать шлюз произвольным пользователям.
5. Установить актуальный CIMD документ и список фактически разрешённых callback URI ChatGPT; нужен согласованный test-only plugin/connection. Создание новых App в ChatGPT может требовать действия пользователя, не входит в серверную сборку.
6. Проверка того, что canonical C-Lab принимает именно Google `access_token` от выбранного Google Web Client. Это не доказано локальным тестом; в случае несоответствия привязать протокол к ожидаемому виду токена, не ослабляя `aud`/issuer и не предоставляя больше инструментов.
7. Включить rate limiting/Cloud Armor, сетевую изоляцию базы, Secret Manager rotation, Cloud Logging без авторизационных кодов или bearer tokens. Исходный контейнер запускает uvicorn с `--no-access-log`.

## Минимальная среда (ИМЕНА ПЕРЕМЕННЫХ, без секретов)

```
GATEWAY_BASE_URL=https://gateway-test.example.com
UPSTREAM_MCP_URL=https://c-lab-gcp-control-w7neqnzura-ew.a.run.app/mcp
GOOGLE_CLIENT_ID=...apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=from Secret Manager
ALLOWED_GOOGLE_EMAIL=one approved email
GATEWAY_ENCRYPTION_KEY=from Secret Manager; Fernet 32 bytes base64
DATABASE_URL=postgresql+psycopg://... (Secret Manager)
CIMD_CLIENT_ID=https://chatgpt.com/oauth/client.json
CHATGPT_REDIRECT_URIS=https://chatgpt.com/connector_platform_oauth_redirect
GOOGLE_PROMPT_CONSENT=1
```

НЕ включать `ALLOW_SQLITE_DEV` или `ALLOW_MOCK_UPSTREAM` для облака.

## Gates

* Gate 0 / isolation: private DB, pinned Google & C-Lab destinations, external OAuth origin TLS, no high-privilege C-Lab tools.
* Gate 1 / end-to-end: реальный Google login, verified ID token, `refresh_token_issued=true`, receipt с `google_refresh_success`, отсроченное чтение 3 read-only MCP tools после истечения Google access token.
* Gate 2 / deployment: authenticated ChatGPT tool call and refresh after *ChatGPT access-token expiry*, repeatable sessions, cloud budget, backup+rollback, no production traffic drift, no data/secret leakage, external test certificate.

**Gate 0/1/2 cloud остаются OPEN**, пока секреты/БД/Google redirect/ChatGPT registration не проверены. Не подключать production C-Lab plugin к этому Gateway до этих проверок.

## Внешние спецификации

* https://developers.openai.com/plugins/build/auth
* https://github.com/modelcontextprotocol/modelcontextprotocol/blob/main/docs/specification/2025-11-25/basic/authorization.mdx
* https://developers.google.com/identity/protocols/oauth2/web-server
