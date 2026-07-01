# 🔧 Neon + Hugging Face Deployment - Real Fix

तपाईंले भन्नुभएको: *"मैले Neon use गरें, URL Hugging Face मा राखें, तर काम गरेन।"*

यो guide ले exact problem solve गर्छ। हरेक step follow गर्नुहोस्।

---

## 🎯 The 3 Real Bugs (जुन मैले अहिले fix गरें)

| # | Bug | Effect | Fix |
|---|-----|--------|-----|
| 1 | `psycopg2.connect()` मा `sslmode='require'` थिएन | Neon SSL माग्छ, plain connect refuse हुन्छ | `_build_connect_kwargs()` मा default `sslmode=require` थपें |
| 2 | Cold-start मा DNS resolve slow | First request hang हुन्छ, timeout | `get_connection()` मा 1.5s delay सहित retry logic थपें |
| 3 | `OperationalError` लाई catch गरिएको थिएन, 500 return हुन्थ्यो | अनि Flutter app मा confusing error देखिन्थ्यो | सबै DB functions ले OperationalError catch गरेर graceful fallback गर्छन् |

---

## 📋 Step-by-Step Deployment

### STEP 1: Verify Neon Connection Locally FIRST (1 मिनेट)

तपाईंको computer मा PowerShell:

```powershell
# PowerShell मा
cd C:\Users\Lenovo\Desktop\chess\chess_backend

# आफ्नो Neon URL राख्नुहोस् (URL आफ्नो Neon console बाट copy गर्नुहोस्)
$env:DATABASE_URL = "postgresql://username:password@ep-xxxxx.us-east-2.aws.neon.tech/neondb?sslmode=require"

# Connection test run गर्नुहोस्
python test_neon_connection.py
```

**Expected output (success)**:
```
Host: ep-xxxxx.us-east-2.aws.neon.tech
Port: 5432
Database: neondb
User: username
SSL: require

Connecting...
Connected in 250 ms
Server: PostgreSQL 16.3 ...
Existing tables (5): messages, payments, tournaments, tournament_participants, users
OK! All required tables exist. You can now use the backend.
```

**यदि "CONNECT FAILED" आए**:
1. Password गलत छ — Neon console बाट reset गर्नुहोस्
2. Host गलत छ — `?sslmode=require` miss भएको हुन सक्छ
3. Neon project paused छ — free tier inactivity मा pause हुन्छ, console मा unpause गर्नुहोस्

**यदि "MISSING required tables" आए**:
- अर्को step मा migrations run गर्नुहोस्

### STEP 2: Run Migrations (1 मिनेट)

```powershell
# Same PowerShell session मा
python auto_migrate.py
```

**Expected output**:
```
Running 3 migration file(s) from ...\sql
Running migration: create_tables.sql
Running migration: payments_migration.sql
Running migration: tournament_prizepool_migration.sql

=== Migration summary ===
  status: ok
  files_run: 3
  statements_executed: 15
  errors: []
```

अब `python test_neon_connection.py` फेरि run गर्नुहोस् — "All required tables exist" देखिनुपर्छ।

### STEP 3: Hugging Face मा DATABASE_URL Update गर्नुहोस् (30 seconds)

1. https://huggingface.co/spaces/anil1515/chess-baackend खोल्नुहोस्
2. **Settings** tab
3. **Variables and secrets** section मा
4. तपाईंको existing `DATABASE_URL` secret मा click गर्नुहोस्
5. **CRITICAL**: URL को अन्त्यमा `?sslmode=require` add गर्नुहोस् (यदि छैन भने):
   ```
   postgresql://username:password@ep-xxxxx.aws.neon.tech/neondb?sslmode=require
   ```
6. **Update** click

### STEP 4: Push Updated Backend Code to HF Space

तपाईंको code commit र push गर्नुहोस्। यदि HF Space git बाट deploy हुन्छ भने:

```powershell
cd C:\Users\Lenovo\Desktop\chess
git add chess_backend/
git commit -m "Add SSL, retry, and auto-migrations for Neon"
git push
```

यदि auto-deploy छैन भने, Space को "Files" tab बाट manually:
- `app/postgres_store.py` (नयाँ SSL config सहित)
- `auto_migrate.py` (नयाँ file)
- `main.py` (auto-migration hook सहित)

### STEP 5: Wait & Verify (2 मिनेट)

1. HF Space auto-restart हुन्छ
2. **Logs** tab मा यी messages देखिनुपर्छ:
   ```
   Running 3 migration file(s) from /app/sql
   Running migration: create_tables.sql
   Running migration: payments_migration.sql
   Running migration: tournament_prizepool_migration.sql
   Migration summary: status=ok, files_run=3
   ```
3. **Test endpoint** (browser मा):
   ```
   https://anil1515-chess-baackend.hf.space/health
   ```
   - "Ludo Game Server is running" देखिनुपर्छ

### STEP 6: Test Register from Any Device

**Browser मा** (URL bar मा direct):
```
https://anil1515-chess-baackend.hf.space/api/auth/register
```

यदि POST गर्न सक्नुहुन्छ भने — backend काम गरिरहेको छ।

**Phone बाट** (APK install भएपछि):
1. App खोल्नुहोस्
2. **Register** → नयाँ username
3. App close → **Login** same credentials
4. ✅ "Login successful" आउनुपर्छ

---

## 🔍 Common Issues + Solutions

### Issue 1: "CONNECT FAILED" from test_neon_connection.py
```
Solution: 
- Neon console → Settings → Reset password
- Copy new password (URL-encode special chars like @ -> %40)
- Make sure URL ends with ?sslmode=require
```

### Issue 2: "MISSING required tables"
```
Solution:
- Run: python auto_migrate.py
- OR: Open Neon SQL Editor, paste each .sql file
```

### Issue 3: App "Invalid credentials" after register
```
Causes:
- Migrations not run yet → run auto_migrate.py
- Wrong DATABASE_URL → verify in HF Space secrets
- Old data from previous deploy → not an issue with Neon
```

### Issue 4: Space logs show "could not translate host name"
```
Solution:
- DNS can't resolve Neon hostname
- Try adding ?sslmode=require&connect_timeout=15
- If still fails, use Supabase (more reliable DNS)
```

### Issue 5: "Connection refused" from HF Space
```
Solution:
- HF Space may be blocking outbound connections
- Check HF Space settings → "Outbound traffic" must be enabled
- Some free HF Spaces have restricted networking
```

---

## ✅ Final Verification Checklist

- [ ] `python test_neon_connection.py` returns "All required tables exist"
- [ ] `python auto_migrate.py` returns "status: ok"
- [ ] HF Space logs show migration messages
- [ ] `https://anil1515-chess-baackend.hf.space/health` returns OK
- [ ] App register → close → login works
- [ ] Tournament join → pay → wallet credit works

**कुनै पनि step मा अड्किए, मलाई screenshot/error पठाउनुहोस् — म immediate fix गर्छु।**
