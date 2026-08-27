# Nightingale — care-note prototype

A compact Python/PostgreSQL framework for a shared longitudinal care note. It uses **synthetic data only** and demonstrates clinic-scoped RBAC, immutable audit metadata, revisions/revert, traceable highlights, deterministic concurrent updates, and lightweight importance learning.

## Quick start

These instructions create a **new local-only** database, load all migrations, seed English synthetic data, and create the demo sign-in accounts. They work on macOS and Windows as long as PostgreSQL is running on port `5432`.

### 1. Install prerequisites

- Install [Anaconda or Miniconda](https://docs.conda.io/projects/conda/en/latest/user-guide/install/).
- Install PostgreSQL 14 or newer and start its database server. On Windows, the PostgreSQL installer includes the command-line tools. On macOS, Postgres.app or Homebrew PostgreSQL both work.
- Open a new terminal in this project folder and confirm that `psql --version` and `conda --version` both print a version. If `psql` is not found on macOS with Postgres.app, add its `bin` directory to `PATH` or run its `psql`/`createdb` binaries by full path.

You need the credentials of a local PostgreSQL **administrator**. The usual Windows administrator name is `postgres`; Postgres.app/Homebrew commonly uses the macOS account name. This is not an application login.

### 2. Create the Conda environment

Run this once from the project root. The environment uses Python 3.12 because supported prebuilt packages are available on both Windows and macOS.

```text
conda env create -f environment.yml
conda activate Nightingale
```

If the environment already exists, use `conda env update -n Nightingale -f environment.yml --prune` instead of the first command.

### 3. Initialise PostgreSQL — macOS (Terminal / zsh)

Replace `postgres` below with your PostgreSQL administrator username, and replace the password value with that administrator's password. If your local administrator has no password, leave the `PGPASSWORD` line out. The password is deliberately placed in an environment variable, rather than inside a URL, so characters such as `@` and `!` work correctly.

```bash
export PGHOST=127.0.0.1
export PGPORT=5432
export PGUSER=postgres
export PGPASSWORD='YOUR_POSTGRES_ADMIN_PASSWORD'

createdb -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" nightingale
psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d nightingale -f db/bootstrap_local.sql

export DATABASE_OWNER_URL="postgresql://${PGUSER}@${PGHOST}:${PGPORT}/nightingale"
export DATABASE_URL='postgresql://nightingale_app:nightingale_local@127.0.0.1:5432/nightingale'

python -m db.apply_migrations
psql "$DATABASE_OWNER_URL" -f db/seed_synthetic.sql
python -m db.seed_demo_accounts
```

### 4. Initialise PostgreSQL — Windows (PowerShell)

Use this alternative to the macOS block. Replace `postgres` and the password as described above. Keep the `$env:` prefix: it makes the values available to both Python and PostgreSQL command-line tools.

```powershell
$env:PGHOST = '127.0.0.1'
$env:PGPORT = '5432'
$env:PGUSER = 'postgres'
$env:PGPASSWORD = 'YOUR_POSTGRES_ADMIN_PASSWORD'

createdb -h $env:PGHOST -p $env:PGPORT -U $env:PGUSER nightingale
psql -h $env:PGHOST -p $env:PGPORT -U $env:PGUSER -d nightingale -f db\bootstrap_local.sql

$env:DATABASE_OWNER_URL = "postgresql://$($env:PGUSER)@$($env:PGHOST):$($env:PGPORT)/nightingale"
$env:DATABASE_URL = 'postgresql://nightingale_app:nightingale_local@127.0.0.1:5432/nightingale'

python -m db.apply_migrations
psql $env:DATABASE_OWNER_URL -f db\seed_synthetic.sql
python -m db.seed_demo_accounts
```

`db/bootstrap_local.sql` creates the restricted local application database account (`nightingale_app`) and grants it database access. Row-level security remains active, so these grants do not bypass Nightingale's role checks. The fixed `nightingale_local` password is only suitable for this local synthetic demo.

If `createdb` reports that `nightingale` already exists, do not run the seed command against it unless you are happy to replace its synthetic data. For an existing database, back it up first and then run the bootstrap and migration commands; `db/seed_synthetic.sql` intentionally truncates the demo tables.

### 5. Verify and start

In the same terminal (with the two `DATABASE_*` variables still set), run:

```text
python -m unittest discover -s tests -v
python -m nightingale.web
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000). Stop the development server with `Ctrl+C`; this frees port `8000` before you start it again.

### Setup troubleshooting

- **`conda activate` is not recognised:** close and reopen the terminal after installing Conda, run `conda init zsh` (macOS) or `conda init powershell` (Windows), then open a new terminal. On Windows, Anaconda Prompt is also a suitable terminal.
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

The server uses CUDA when available and otherwise uses CPU. This is the reliable default for the 0.5B model on the current macOS/PyTorch runtime; the Conda environment includes `accelerate` for compatible Transformers loading.

The demo seeds a synthetic patient timeline and prints the consult Glance View. `PostgresStore` is the application repository; its migration turns on PostgreSQL row-level security (RLS). The in-memory `CareService` is retained solely as a fast, deterministic unit-test double.

## Design choices

- **Server-side authorization:** production requests set database-local `app.clinic_id`, `app.role`, and `app.user_id` inside each transaction; RLS checks these claims in PostgreSQL. The service layer separately limits which sections a role may write. The UI is never the authorization boundary.
- **Eight record types:** `system_generated_event`, `ai_scribe_log`, `doctor_patient_consult`, `nurse_patient_consult`, `ai_patient_consult`, `staff_manual_log`, `clinician_manual_log`, and `patient_facing_log` are the only accepted record types.
- **Clinical subtypes:** doctors may write Doctor–Patient Consults, clinician manual logs, and patient-facing logs; nurses have the equivalent permission with Nurse–Patient Consults. Both clinical subtypes can read the complete clinic-scoped timeline. A consult automatically creates a short system-owned AI scribe log with a trusted link back to its source entry.
- **Protected content:** patients are read-only and receive only `patient_facing_log` records. Staff can read, create, and edit only `staff_manual_log` records. Clinicians cannot edit AI scribe logs or AI–Patient Consults. Clinicians and admins may highlight keywords in any record they can view, select and delete individual highlights from Glance View, or right-click a selected timeline keyword to remove its highlight; the underlying entry is unchanged. Patients and staff cannot create or delete highlights. Admins can read, create, and edit every record type.
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
