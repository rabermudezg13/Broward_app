# Change log

## 2026-11-11 — Initial Broward front desk

Created public five-field visitor check-in, protected staff/admin workspaces, current Monday–Friday arrival queue, attendance actions, weekly statistics and a separate paginated historical query by week/name. Added Python/Flask API, Docker, SQLite persistent storage and arrival index, role enforcement, rate limiting and session revocation. Administrator: cculturausallc@gmail.com.

Validation: three backend integration tests passed against temporary SQLite, covering validation, access control, current-week boundaries, FIFO order, 50-record pagination, history and attendance. JavaScript syntax check passed. Browser verified local check-in and marking attended. Railway health, administrator login, weekly query, team access and logout checked successfully without creating production visitor records. Vercel frontend deployed and publicly returns HTTP 200.

Deployment: new Railway project `kelly-broward-front-desk`, service `broward-api`, persistent `/data` volume. Frontend: https://kelly-broward-front-desk.vercel.app. API: https://broward-api-production.up.railway.app. Initial password is delivered privately and absent from source control. Change it on first use. SQLite deployment uses one process/replica; move to PostgreSQL before horizontal scaling.
