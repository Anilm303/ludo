<#
neon_import_helper.ps1

Helper to backup Neon DB, optionally truncate tables, and import a data-only SQL dump.

USAGE (PowerShell):
  Run from project root or provide full path. The script will prompt for Neon host/port/db/user
  and a hidden password, plus the path to your local `chess_data_only.sql` dump.

This script will NOT print or store passwords. It uses the environment variable PGPASSWORD
for pg tools during execution and clears it at the end.
#>

param()

function Read-Secure($prompt) {
    $sec = Read-Host -AsSecureString $prompt
    return [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec))
}


Write-Host "Neon import helper - backup, optional truncate, and import" -ForegroundColor Cyan

$dbHost = Read-Host "Neon HOST (eg ep-abc123.neon.tech)"
$port = Read-Host "Neon PORT (eg 5432)"
$db   = Read-Host "Neon database name (eg neondb)"
$user = Read-Host "Neon user (eg neondb_owner)"
$pw   = Read-Secure "Neon password (hidden)"

$dumpPath = Read-Host "Local data-only SQL dump path (eg C:\Users\Lenovo\Desktop\chess_data_only.sql)"
$backupPath = Read-Host "Output backup file path (eg C:\Users\Lenovo\Desktop\neon_pre_import.dump)"

if (-not (Test-Path $dumpPath)) {
    Write-Error "Dump file not found: $dumpPath"; exit 1
}

$pgBin = "C:\Program Files\PostgreSQL\18\bin"
$pgDump = Join-Path $pgBin "pg_dump.exe"
$psql = Join-Path $pgBin "psql.exe"


if (-not (Test-Path $pgDump)) { Write-Error "pg_dump not found at $pgDump"; exit 1 }
if (-not (Test-Path $psql)) { Write-Error "psql not found at $psql"; exit 1 }

$env:PGPASSWORD = $pw

# 1) Backup (custom format)
Write-Host "Creating backup to $backupPath..."
& $pgDump -h $dbHost -p $port -U $user -Fc -f $backupPath $db
if ($LASTEXITCODE -ne 0) { Write-Error "pg_dump failed (exit $LASTEXITCODE)"; $env:PGPASSWORD = $null; exit 1 }
Write-Host "Backup complete." -ForegroundColor Green

# 2) Ensure missing column 'media_path' if not exists
Write-Host "Ensuring 'media_path' column exists in 'messages'..."
& $psql -h $dbHost -p $port -U $user -d $db -c "ALTER TABLE messages ADD COLUMN IF NOT EXISTS media_path text;"
if ($LASTEXITCODE -ne 0) { Write-Warning "ALTER TABLE returned non-zero exit code ($LASTEXITCODE) - check manually." }

# 3) Ask user whether to TRUNCATE tables (destructive)
$doTrunc = Read-Host "Truncate target tables before import? This will DELETE existing rows (yes/no)"
if ($doTrunc -match '^(y|Y|yes)$') {
    Write-Host "Truncating tables (this is destructive)..." -ForegroundColor Yellow
    $truncateSql = "BEGIN; TRUNCATE TABLE group_messages, messages, media_files, game_rooms, groups, stories, notes, password_reset_tokens, auth_token_blocklist, audit_events, users RESTART IDENTITY CASCADE; COMMIT;"
    & $psql -h $dbHost -p $port -U $user -d $db -c $truncateSql
    if ($LASTEXITCODE -ne 0) { Write-Error "TRUNCATE failed (exit $LASTEXITCODE)"; $env:PGPASSWORD = $null; exit 1 }
    Write-Host "Truncate complete." -ForegroundColor Green
} else {
    Write-Host "Skipping TRUNCATE - proceeding to import (may produce duplicates/constraint errors)." -ForegroundColor Yellow
}

# 4) Run data-only import
Write-Host "Importing data from $dumpPath ..." -ForegroundColor Cyan
& $psql -h $dbHost -p $port -U $user -d $db -f $dumpPath
if ($LASTEXITCODE -ne 0) { Write-Warning "Import finished with non-zero exit code ($LASTEXITCODE). Check errors in output." }

# 5) Verification counts
Write-Host "Running quick verification counts..."
$verifySql = @"
SELECT 'users', count(*) FROM users;
SELECT 'groups', count(*) FROM groups;
SELECT 'messages', count(*) FROM messages;
SELECT 'game_rooms', count(*) FROM game_rooms;
SELECT 'media_files', count(*) FROM media_files;
SELECT 'audit_events', count(*) FROM audit_events;
"@
& $psql -h $dbHost -p $port -U $user -d $db -c $verifySql

$env:PGPASSWORD = $null
Write-Host "Done. Review the counts above and errors during import." -ForegroundColor Green
