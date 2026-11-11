# Kelly Education · Broward County

Modern front desk based on the two-entry workflow of `rabermudezg13/kelly-app-v2`.

- Public visitor check-in: first name, last name, email, phone, ZIP.
- Password-protected staff and administrator workspaces.
- Current Monday–Friday week in America/New_York, arrival order, 50 records per page.
- Mark in progress / attended / reopen; updates every 30 seconds.
- Statistics for the current week, including unique visitors and attendance rate.
- Separate read-only historical query by week and/or name, paginated server-side.
- Admins create and manage Staff, Management and Admin accounts. Only Admin manages users; Management and Admin can permanently delete visits with confirmation. The primary administrator remains protected.
- Same-day duplicate check-ins are blocked by normalized email in America/New_York, including concurrent submissions. A visitor may return on another day.
- Successful check-in displays the requested Spanish welcome message.
- Password changes invalidate all sessions. Disabled accounts lose access immediately.

## Run

Python 3.13 recommended. `pip install -r backend/requirements.txt`.
Set `DATABASE_PATH` to a persistent SQLite path and `ADMIN_INITIAL_PASSWORD` to a strong initial password before the first boot. It only seeds the administrator if no account exists; changing the variable does not reset an existing password. Change the initial password through the app, then remove the bootstrap variable. Never commit passwords.

`gunicorn --chdir backend --bind 0.0.0.0:8080 --workers 1 --threads 4 app:app`

Backend also serves the frontend for local and recovery access. Use a single Railway replica and worker with persistent volume `/data`. SQLite WAL and parameterized queries are enabled. Do not scale horizontally with SQLite; migrate to managed PostgreSQL first. Rate limits are per process and reset after restarts. Configure platform rate limiting for larger traffic.

## Railway

Deploy repository main using root Dockerfile; attach persistent volume `/data`; `DATABASE_PATH=/data/broward.db`. `/health` is the health check. `FRONTEND_ORIGIN` is the comma-separated list of exact allowed frontend origins. No wildcard credentials or public data-list endpoint.

## Vercel

New static project with root directory `frontend`, framework Other, no build command, output directory `.`. Set `window.API_BASE` in `frontend/config.js` to the Railway HTTPS origin. `vercel.json` supplies security headers. The frontend stores an eight-hour bearer token in sessionStorage and removes it at logout; use a dedicated staff browser profile on shared reception devices.

## Verify

`cd backend && python -m unittest -v test_app.py`

Tests use a temporary SQLite database and fictitious records. Cover public validation and privacy, week bounds, arrival order, pagination, history, attendance changes, role permissions and access revocation. No production records are used.
