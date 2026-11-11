# Change log

## 2026-11-11 — Initial Broward front desk

Created public five-field visitor check-in, protected staff/admin workspaces, current Monday–Friday arrival queue, attendance actions, weekly statistics and a separate paginated historical query by week/name. Added Python/Flask API, Docker, SQLite persistent storage and arrival index, role enforcement, rate limiting and session revocation. Administrator: cculturausallc@gmail.com.

Validation: three backend integration tests passed against temporary SQLite, covering validation, access control, current-week boundaries, FIFO order, 50-record pagination, history and attendance. JavaScript syntax check passed. Browser verified local check-in and marking attended. Railway health, administrator login, weekly query, team access and logout checked successfully without creating production visitor records. Vercel frontend deployed and publicly returns HTTP 200.

Deployment: new Railway project `kelly-broward-front-desk`, service `broward-api`, persistent `/data` volume. Frontend: https://kelly-broward-front-desk.vercel.app. API: https://broward-api-production.up.railway.app. Initial password is delivered privately and absent from source control. Change it on first use. SQLite deployment uses one process/replica; move to PostgreSQL before horizontal scaling.

## 11-11-2026 — Welcome cover

Added the user-provided Broward school illustration as the welcome-page cover, optimized for web delivery. Desktop uses a cover beside the welcome text and entry cards; mobile shows the full illustration above the entry controls. Preserved visitor/staff routes and MM-DD-YYYY dates. JavaScript syntax checked; deployment and browser visual review follow.

## 11-11-2026 — Header logo

Replaced the upper-left text logo with the image supplied by the user, retaining the Broward County label and home link. Responsive sizing preserves the logo proportions.

## 11-11-2026 — Roles, repeat check-ins and visit deletion

Added Staff, Management and Admin assignment at account creation and editing, with server-side role validation. Only Admin manages accounts. The primary admin and current administrator cannot lose their own access. Role changes revoke existing sessions. Management and Admin can permanently delete individual visits from current and historical lists after an explicit confirmation; Staff cannot delete. Duplicate check-ins by normalized email are rejected within the same Eastern calendar day using a serialized database transaction, while subsequent days remain allowed. Successful registration now shows the requested Spanish welcome message.

Validation: four backend integration tests pass, covering existing flows, all three roles, deletion permissions, invalid roles, primary admin protection, case-insensitive duplicates and repeat visits on different days. Frontend JavaScript syntax passes. No production visitor records used in tests.

## 11-11-2026 — Password length

Removed the 12-character minimum for account creation and password changes at the user's request. Passwords remain required, with the existing 128-character maximum. Removed frontend minlength and outdated hints; updated backend validation messages. Five integration tests pass, including short-password creation, login and change, plus empty-password rejection. JavaScript syntax check passes.

## 11-11-2026 — Visit reason dropdown

Added required Reason for visit dropdown: Badge Pickup, Fingerprinting, Talent Advisor Question, Speak with My Onboarder, Incident Question, Other. API validates the exact options and persists visit_reason. Idempotent additive SQLite migration retains old visits with a blank reason, displayed as an em dash. Current-week, statistics and historical tables display the reason. Six backend integration tests and frontend syntax check pass, including all six accepted reasons, rejection of missing/invalid reasons, and persistence.
