# ⚠️ CRITICAL: Production Deployment Issue & Fix

## The Problem

You deployed the backend to **Hugging Face Space** (`anil1515-chess-baackend.hf.space`) and noticed:

1. **Register works the first time** ✅
2. **Login returns "Invalid credentials"** ❌
3. **Old tournaments disappear** ❌
4. **Different devices see different data** ❌

## Root Cause

**Hugging Face Spaces use an ephemeral filesystem.** Every time the Space restarts (which happens regularly, and any time it's idle for a while), all data written to disk is wiped.

The current code falls back to a **local JSON file** (`data/users.json`) when `DATABASE_URL` is not configured:

```python
# app/models/user.py
def _use_local_user_store() -> bool:
    return not _database_url_is_valid()  # True when DATABASE_URL is missing
```

So users register, get saved to a JSON file, then **the file disappears on the next restart**, and they "no longer exist".

## The Fix (3 Steps)

### Step 1: Add a Persistent PostgreSQL Database to HF Space

Hugging Face Spaces support a free **Postgres** addon. Set it up:

1. Go to your Space: https://huggingface.co/spaces/anil1515/chess-baackend
2. Click **Settings** → **Variables and secrets**
3. Click **"+ Add a secret"** (NOT a variable — secrets are encrypted)
4. Add a new secret:
   - **Name:** `DATABASE_URL`
   - **Value (example):** `postgresql://user:password@host:5432/dbname?sslmode=require`

For the actual connection string, you have two options:

#### Option A: Use Supabase (free tier)
1. Sign up at https://supabase.com
2. Create a new project
3. Go to **Project Settings** → **Database** → **Connection string** → **URI**
4. Copy the connection string (it looks like `postgresql://postgres.[ref]:[password]@aws-0-[region].pooler.supabase.com:6543/postgres`)
5. Add it as the `DATABASE_URL` secret in your HF Space

#### Option B: Use HF's built-in Postgres (paid)
Only available on paid HF plans.

### Step 2: Run the Migrations

After the database is configured, the backend will be able to connect. But the tables won't exist yet. You have two options:

#### Option 2a: Add migrations to the Space startup
Edit your Space's `Dockerfile` or `app.py` startup to run the SQL:

```python
# chess_backend/main.py - add this inside the lifespan function, before yield
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Ludo Game Server...")
    try:
        await init_db()
        # NEW: Run SQL migrations
        await _run_migrations()
    except Exception as exc:
        logger.warning("Database initialization failed: %s", exc)
    yield
    # ... shutdown code
```

#### Option 2b: Run migrations manually (one time)
Connect to your database with `psql` and run `sql/create_tables.sql`, then `sql/payments_migration.sql`, then `sql/tournament_prizepool_migration.sql`:

```bash
psql "postgresql://user:pass@host:5432/dbname?sslmode=require" -f chess_backend/sql/create_tables.sql
psql "postgresql://user:pass@host:5432/dbname?sslmode=require" -f chess_backend/sql/payments_migration.sql
psql "postgresql://user:pass@host:5432/dbname?sslmode=require" -f chess_backend/sql/tournament_prizepool_migration.sql
```

### Step 3: Restart Your Space

After saving the new `DATABASE_URL` secret, the Space will restart automatically. Once it's back up, test:

```bash
curl https://anil1515-chess-baackend.hf.space/health
# Should return: {"status":"ok","message":"Ludo Game Server is running","version":"1.0.0"}
```

Then register a new user:

```bash
curl -X POST https://anil1515-chess-baackend.hf.space/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"alice","email":"a@x.com","first_name":"A","last_name":"L","password":"p123"}'
```

Wait 5 minutes (or restart the Space). The user should still be there.

## Why the eSewa Flow Works Emulator but Not Real Device

The eSewa WebView itself works the same on emulator and real device. The reason you might have seen different behavior:

1. **Emulator uses `http://10.0.2.2:7860`** → connects to your local backend
2. **Real device** → tries to connect to `https://anil1515-chess-baackend.hf.space`
3. If the HF backend's database is being wiped, payment records disappear too

After you add the persistent database, both emulator and real device will work consistently.

## Files That Were Already Fixed

I ran `fix_production.py` which applied these patches:

- ✅ `app/models/user.py` — better error messages ("No account found..." vs "Wrong password...")
- ✅ `main.py` — CORS middleware accepts any origin
- ✅ `app/api_routes.py` — added `/api/health` endpoint
- ✅ `lib/config/backend_config.dart` — config log enabled in release mode
- ✅ `android/app/src/main/res/xml/network_security_config.xml` — HTTPS-only by default
- ✅ `AndroidManifest.xml` — references the network config

## What You Still Need To Do

1. **Add `DATABASE_URL` secret to your HF Space** (most important!)
2. **Run the SQL migrations** against that database
3. **Rebuild & redeploy your Flutter APK** with the updated code
4. **Test from any device** — it should now work consistently

The eSewa prize-pool flow will work as designed once the database is persistent. Tournament creation, payments, and wallet credits will all be saved permanently.
