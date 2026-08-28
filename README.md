# Nightingale — care-note prototype

A compact Python/PostgreSQL framework for a shared longitudinal care note. It uses **synthetic data only** and demonstrates clinic-scoped RBAC, immutable audit metadata, revisions/revert, traceable highlights, deterministic concurrent updates, and lightweight importance learning.

## Quick start

Follow this section from top to bottom on a new computer. It creates the Conda environment, a local PostgreSQL database, the complete schema, two English synthetic patients, eight example timeline entries, and all six demo accounts. No real patient data is included.

The verified environment currently uses Python 3.14, PyTorch 2.13, Transformers 5.15, Accelerate 1.13, and Phileas 1.0. `environment.yml` installs compatible patch releases for Windows x64 or Apple Silicon macOS; you do not need to install Python separately. Intel Mac is outside the tested support matrix.

### 1. Install prerequisites

- Install [Anaconda or Miniconda](https://docs.conda.io/projects/conda/en/latest/user-guide/install/). Reopen the terminal after installation.
- Install PostgreSQL 14 or newer, configure it to use port `5432`, and start it. [Postgres.app](https://postgresapp.com/) is the simplest macOS option; the standard [PostgreSQL Windows installer](https://www.postgresql.org/download/windows/) includes the server and command-line tools.
- Download/clone this project and open a terminal in the folder containing this README.
- Allow approximately 4 GB of free disk space for the Conda environment and local Qwen model. The first AI request also requires internet access.

Confirm both tools are available:

```text
conda --version
psql --version
```

You also need the username/password of a local PostgreSQL **administrator**. Windows commonly uses `postgres`. Postgres.app commonly uses the macOS account name and may not require a password. These are database setup credentials, not Nightingale demo-account credentials.

### 2. Create the Conda environment

Run these commands from the project root:

```bash
conda env create -f environment.yml
conda activate Nightingale
python --version
python -c "import psycopg, torch, transformers, accelerate, phileas; print('Nightingale dependencies OK')"
```

`python --version` should report Python 3.14.x. On an existing installation, synchronize it with the checked-in environment instead:

```text
conda env update -n Nightingale -f environment.yml --prune
conda activate Nightingale
```

### 3. Initialise PostgreSQL — macOS (Terminal / zsh)

Use this section on macOS; Windows users should skip to section 4. Replace `YOUR_POSTGRES_ADMIN` and the password. If Postgres.app accepts your macOS username without a password, use that username and omit the `PGPASSWORD` line.

```bash
export PGHOST=127.0.0.1
export PGPORT=5432
export PGUSER='YOUR_POSTGRES_ADMIN'
export PGPASSWORD='YOUR_POSTGRES_ADMIN_PASSWORD'

# Confirm the server and administrator login before changing anything.
psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d postgres -c "SELECT version();"

createdb -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" nightingale
psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d nightingale -f db/bootstrap_local.sql

export DATABASE_OWNER_URL="postgresql://${PGUSER}@${PGHOST}:${PGPORT}/nightingale"
export DATABASE_URL='postgresql://nightingale_app:nightingale_local@127.0.0.1:5432/nightingale'

python -m db.apply_migrations
psql "$DATABASE_OWNER_URL" -f db/seed_synthetic.sql
python -m db.seed_demo_accounts
```

With Postgres.app, if `psql` is not on `PATH`, first run:

```bash
export PATH="/Applications/Postgres.app/Contents/Versions/latest/bin:$PATH"
```

### 4. Initialise PostgreSQL — Windows (PowerShell)

Run PowerShell or Anaconda PowerShell Prompt as a normal user. Replace the administrator username/password below. Keep the `$env:` prefix so Python and PostgreSQL inherit the values.

```powershell
$env:PGHOST = '127.0.0.1'
$env:PGPORT = '5432'
$env:PGUSER = 'YOUR_POSTGRES_ADMIN'
$env:PGPASSWORD = 'YOUR_POSTGRES_ADMIN_PASSWORD'

# Confirm the server and administrator login before changing anything.
psql -h $env:PGHOST -p $env:PGPORT -U $env:PGUSER -d postgres -c "SELECT version();"

createdb -h $env:PGHOST -p $env:PGPORT -U $env:PGUSER nightingale
psql -h $env:PGHOST -p $env:PGPORT -U $env:PGUSER -d nightingale -f db\bootstrap_local.sql

$env:DATABASE_OWNER_URL = "postgresql://$($env:PGUSER)@$($env:PGHOST):$($env:PGPORT)/nightingale"
$env:DATABASE_URL = 'postgresql://nightingale_app:nightingale_local@127.0.0.1:5432/nightingale'

python -m db.apply_migrations
psql $env:DATABASE_OWNER_URL -f db\seed_synthetic.sql
python -m db.seed_demo_accounts
```

The order is important: create database → bootstrap application role → migrations → synthetic timeline → demo accounts. `db/bootstrap_local.sql` creates the restricted `nightingale_app` database role. PostgreSQL RLS remains active, so these grants do not bypass Nightingale authorization. The fixed password is suitable only for this local synthetic demo.

If `createdb` reports that `nightingale` already exists, do not run `db/seed_synthetic.sql` unless you intend to replace its Nightingale data. The seed script deliberately resets patients, entries, versions, comments, highlights, mentions, sessions, audit rows, and demo users.

### 5. Verify the seeded demo

Run this in the same terminal:

macOS:

```bash
psql "$DATABASE_OWNER_URL" -c "SELECT (SELECT count(*) FROM patients) AS patients, (SELECT count(*) FROM care_entries) AS entries, (SELECT count(*) FROM app_users) AS users;"
```

Windows PowerShell:

```powershell
psql $env:DATABASE_OWNER_URL -c "SELECT (SELECT count(*) FROM patients) AS patients, (SELECT count(*) FROM care_entries) AS entries, (SELECT count(*) FROM app_users) AS users;"
```

Expected counts are `patients = 2`, `entries = 8`, and `users = 6`. The example patients are “Ava Morgan (Synthetic)” and “Noah Chen (Synthetic)”.

Then run the non-database and PostgreSQL integration tests:

macOS:

```bash
python -m unittest discover -s tests -v
export NIGHTINGALE_TEST_DATABASE_URL="$DATABASE_URL"
python -m unittest -v tests.test_postgres_integration
```

Windows PowerShell:

```powershell
python -m unittest discover -s tests -v
$env:NIGHTINGALE_TEST_DATABASE_URL = $env:DATABASE_URL
python -m unittest -v tests.test_postgres_integration
```

### 6. Start Nightingale

```text
python -m nightingale.web
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000) and sign in with a demo account from the table below or [DEMO_ACCOUNTS.txt](DEMO_ACCOUNTS.txt). A clinician/admin/system page automatically requests an AI Glance, so the first such login may spend several minutes downloading and warming Qwen. Patient and staff pages do not automatically invoke Qwen.

Stop the server with `Ctrl+C` before starting it again; that releases port `8000`.

### Reset to the clean synthetic demo later

This intentionally destroys all Nightingale demo records and sessions in the `nightingale` database, then restores the same two-patient baseline:

macOS:

```bash
psql "$DATABASE_OWNER_URL" -v ON_ERROR_STOP=1 -f db/seed_synthetic.sql
python -m db.seed_demo_accounts
```

Windows PowerShell:

```powershell
psql $env:DATABASE_OWNER_URL -v ON_ERROR_STOP=1 -f db\seed_synthetic.sql
python -m db.seed_demo_accounts
```

### Run the required micro-tests

Activate the Conda environment from the project root. These unit tests use the deterministic in-memory `CareService` test double, so they do not require PostgreSQL or the web server to be running.

Run the entire test suite:

```text
conda run -n Nightingale python -m unittest discover -s tests -v
```

Run only the four required micro-test modules:

```text
conda run -n Nightingale python -m unittest -v \
  tests.test_rbac_scope \
  tests.test_revision_history \
  tests.test_highlight_provenance \
  tests.test_concurrent_edits
```

The same command on Windows PowerShell is:

```powershell
conda run -n Nightingale python -m unittest -v tests.test_rbac_scope tests.test_revision_history tests.test_highlight_provenance tests.test_concurrent_edits
```

- `test_rbac_scope.py` checks cross-role write/edit restrictions and confirms a patient cannot read internal staff or raw AI-scribe content.
- `test_revision_history.py` checks version increments, reverting, and metadata-only audit events.
- `test_highlight_provenance.py` checks that an AI-scribed-entry highlight resolves to its provenance source.
- `test_concurrent_edits.py` checks independent record edits and deterministic optimistic-lock conflict rejection for a stale same-record edit.

#### Run the PostgreSQL integration tests

The micro-tests above use the in-memory test double. `test_postgres_integration.py` repeats the critical checks against the real repository and PostgreSQL RLS, including genuinely concurrent edits through separate database connections.

Use a fully migrated **synthetic test database** accessed through the restricted `nightingale_app` role. Never point this variable at a database containing real clinical data. The tests create a uniquely named clinic/patient and register cleanup immediately, so their records are removed even when a later setup assertion fails.

macOS (Terminal / zsh):

```bash
export NIGHTINGALE_TEST_DATABASE_URL='postgresql://nightingale_app:nightingale_local@127.0.0.1:5432/nightingale'
conda run -n Nightingale python -m unittest -v tests.test_postgres_integration
```

Windows (PowerShell):

```powershell
$env:NIGHTINGALE_TEST_DATABASE_URL = 'postgresql://nightingale_app:nightingale_local@127.0.0.1:5432/nightingale'
conda run -n Nightingale python -m unittest -v tests.test_postgres_integration
```

When `NIGHTINGALE_TEST_DATABASE_URL` is unset, these database tests are reported as skipped; the unit-test suite still runs normally. To run every unit and integration test together, set the variable first and use:

```text
conda run -n Nightingale python -m unittest discover -s tests -v
```

### Setup troubleshooting

- **`conda activate` is not recognised:** close and reopen the terminal after installing Conda, run `conda init zsh` (macOS) or `conda init powershell` (Windows), then open a new terminal. On Windows, Anaconda Prompt is also a suitable terminal.
- **Conda asks you to accept channel Terms of Service:** follow the URL and acceptance command printed by Conda, then repeat `conda env create -f environment.yml`. This can occur on a new Anaconda installation before its first package download.
- **`psql` or `createdb` is not recognised:** add PostgreSQL's `bin` directory to `PATH` and open a new terminal. The usual Windows location is `C:\Program Files\PostgreSQL\<version>\bin`; Postgres.app provides the equivalent directory inside the app bundle.
- **Connection refused on `127.0.0.1:5432`:** start PostgreSQL and confirm that it is configured to listen on port `5432`. Do not start the Nightingale server until this connection works: `psql -h 127.0.0.1 -p 5432 -U <admin-user> -d postgres`.
- **Password authentication failed:** check `PGUSER` and `PGPASSWORD`; they are for the PostgreSQL administrator, not any of the demo web accounts. Clear and re-enter `PGPASSWORD` if it was copied with extra quotation marks.
- **Port 8000 is already in use:** stop the prior Nightingale terminal with `Ctrl+C`, then start it again. You can also choose a different temporary port with `PORT=8001 python -m nightingale.web` on macOS or `$env:PORT = '8001'; python -m nightingale.web` in PowerShell.

## Running application

Start the local full-stack application with:

```text
conda activate Nightingale
python -m nightingale.web
```

This assumes you have completed Quick Start in the same terminal, or have set `DATABASE_URL` to your local application connection. Then open [http://localhost:8000](http://localhost:8000). This is a working browser app, not a static mockup: creating a patient creates a database record; creating/editing a note creates PostgreSQL version snapshots; comments and version restores use the same API.

### Mentions and notifications

Open an entry's **Comments** panel to mention another authorised clinic user. Click a suggested `@username` chip or type it into the comment, then post the comment. A durable unread notification is created for every mentioned user. The header badge opens `/notifications.html`, where the recipient can mark the mention as read and jump directly to the patient, timeline entry, and comment.

Mention targets are enforced by the server and PostgreSQL: the target must be an active user in the same clinic and must be able to read the referenced entry and its internal comments. Patients and system accounts cannot be mentioned. Staff can be mentioned only on staff manual logs; clinicians and admins can be mentioned on any entry visible within their clinic. Invalid or cross-scope `@username` values reject the whole comment transaction.

### Local demo sign-in

The login page creates a server-side session in an HttpOnly cookie. API identity is resolved from that session; client-supplied role headers are ignored.

| Role | Username | Password |
|---|---|---|
| Patient | `patient_demo` | `Patient123!` |
| Staff | `staff_demo` | `Staff1234!` |
| Doctor | `doctor_demo` | `Doctor123!` |
| Nurse | `nurse_demo` | `Nurse1234!` |
| Admin | `admin_demo` | `Admin1234!` |
| System | `system_demo` | `System123!` |

These credentials are for the local synthetic demonstration only and must be replaced before deployment.

## Qwen AI-scribe and Glance View

The application uses `Qwen/Qwen2.5-0.5B-Instruct` locally through Transformers for AI-scribed summaries and AI Glance View.

```bash
conda run -n Nightingale python -m nightingale.web
```

The first AI request downloads the public Qwen model into the current user's Hugging Face cache, so it needs an internet connection and can take several minutes. Later requests reuse that cache. Before every model invocation, `redact_for_llm()` applies the local [Phileas](https://github.com/philterd/phileas-python) policy and blocks the request if redaction cannot run; it never falls back to sending raw text. The policy redacts built-in PII types plus Singapore NRIC/FIN values, Singapore phone numbers, and honorific-prefixed names. The server then creates a distinct system-owned `ai_scribed` timeline entry with a session provenance pointer. AI output is a draft for clinician confirmation—not diagnostic or treatment advice. Qwen’s model card documents Transformers use and lists the model as Apache-2.0 licensed. [Model card](https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct)

The checked-in adapter uses Transformers with Accelerate device mapping and a CPU-compatible pipeline, matching the current verified Conda environment. Qwen runs locally; generated clinical text is not sent to a hosted inference API.

The demo seed creates a synthetic patient timeline that appears immediately after login. `PostgresStore` is the application repository; its migrations turn on PostgreSQL row-level security (RLS). The in-memory `CareService` is retained solely as a fast, deterministic unit-test double.

## Security boundaries: PHI redaction and RBAC

### Where PHI redaction happens

PHI redaction happens in the server API handler, immediately before any text crosses into `generate_scribe()` or `generate_glance()`:

```text
authorised database record(s) → redact_for_llm() / Phileas → Qwen → AI draft or Glance View
```

The three protected paths are automatic consult summaries, explicit AI-scribe generation, and AI Glance View generation. In each path, `nightingale/web.py` passes the source text through `nightingale.redaction.redact_for_llm()` before calling the Qwen adapter. `redact_for_llm()` creates a short-lived Phileas `FilterService`, applies the Nightingale policy, and returns only redacted text. For Glance View, each entry's clinical text is redacted separately and its validated, non-PHI `Source Entry ID` is appended afterward; this preserves provenance citations without exempting clinical text from redaction. If Phileas or its policy cannot run, it raises an error and the API blocks the model request; there is no raw-text fallback. The original entry remains in PostgreSQL and is never placed in the model prompt by application code.

### How RBAC is enforced

RBAC is enforced on the server and again in PostgreSQL; the browser only reflects the resulting permissions.

1. **Authentication:** `/api/auth/login` verifies the password hash and returns an HttpOnly, `SameSite=Strict` session cookie. Each request resolves that cookie to an active user record; client-supplied role headers are ignored.
2. **Server-side authorization:** the server builds an `Actor` from the session, then validates record-type, clinician-subtype, edit, highlight, and patient-deletion rules in the repository/service layer. For example, doctors and nurses may create only their respective consult types; patients cannot write records or highlights.
3. **Database enforcement:** for every repository transaction, `PostgresStore.request()` sets transaction-local `app.clinic_id`, `app.role`, `app.user_id`, and `app.clinician_kind`. PostgreSQL RLS is enabled and forced on patient, entry, revision, comment, highlight, audit, and feedback tables. The policies use those transaction-local claims to constrain clinic scope, patient-facing visibility, and permitted writes.
4. **Safe derived views:** the timeline supplied to AI Glance View is already RLS-filtered. Source-entry buttons and highlight links are emitted only when that same actor can read the referenced entry.

The UI hides unavailable controls for clarity, but hiding a control is not the authorization mechanism. Direct API requests remain subject to the session-derived checks and PostgreSQL RLS policies.

## Design choices

- **Server-side authorization:** production requests set database-local `app.clinic_id`, `app.role`, and `app.user_id` inside each transaction; RLS checks these claims in PostgreSQL. The service layer separately limits which sections a role may write. The UI is never the authorization boundary.
- **Eight record types:** `system_generated_event`, `ai_scribe_log`, `doctor_patient_consult`, `nurse_patient_consult`, `ai_patient_consult`, `staff_manual_log`, `clinician_manual_log`, and `patient_facing_log` are the only accepted record types.
- **Clinical subtypes:** doctors may write Doctor–Patient Consults, clinician manual logs, and patient-facing logs; nurses have the equivalent permission with Nurse–Patient Consults. Both clinical subtypes can read the complete clinic-scoped timeline. A consult automatically creates a short system-owned AI scribe log with a trusted link back to its source entry.
- **Protected content:** patients are read-only and receive only `patient_facing_log` records. Staff can read, create, and edit only `staff_manual_log` records. Clinicians cannot edit AI scribe logs or AI–Patient Consults. Clinicians and admins may highlight keywords in any record they can view, select and delete individual highlights from Glance View, or right-click a selected timeline keyword to remove its highlight; the underlying entry is unchanged. Patients and staff cannot create or delete highlights. Admins can read, create, and edit every record type.
- **Private mentions:** comment mentions are stored per recipient with an independent read timestamp. Notification queries are restricted to the authenticated recipient and disappear if that recipient can no longer read the source entry.
- **Revision integrity:** each edit produces an immutable `Version` snapshot and audit record. Revert creates a new version rather than deleting history.
- **Provenance:** a highlight stores `entry_id`, optional character span, and source session pointer. `resolve_provenance()` resolves it to the source-of-truth timeline entry.
- **Privacy:** `redact_for_llm()` uses Phileas before every LLM boundary and fails closed if it is unavailable. The policy covers built-in PII and local Singapore NRIC/FIN, telephone, and honorific-name patterns. Do not send raw clinical text to an external model. Use TLS in transit and encrypted storage in a production deployment.
- **Latency:** a warm in-memory Glance calculation is measured in `demo.py`; the target is p95 ≤300ms. In production, precompute/cache per-patient glance projections after each write.

## Suggested production deployment

Use a Python API service, Postgres with clinic and role claims enforced through RLS, and an append-only audit table. Store recordings/transcripts separately with short-lived signed URLs. AI requests pass through the redaction pipeline; source session IDs, not raw source payloads, are retained in highlight pointers.

## Project layout

`db/migrations/` contains the ordered PostgreSQL schema/RLS migrations; `db/apply_migrations.py` records and applies them; `db/bootstrap_local.sql` prepares the local application role. `nightingale/postgres.py` is the transaction-scoped PostgreSQL repository; `nightingale/domain.py` contains application data types; `importance.py` contains transparent scoring + feedback weights. Tests map to the requested micro-tests.

## Limitations of this prototype

Authentication and local Qwen inference are included for the synthetic demo, but this is not a production-ready clinical system. It lacks production secret management, HTTPS/TLS termination, rate limiting, backups, monitoring, deployment hardening, and a clinical safety review. Database integration tests require a local PostgreSQL URL.
