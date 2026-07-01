-- Migration: tournament prize-pool columns + view
-- Idempotent: every statement is safe to re-run.

ALTER TABLE tournaments ADD COLUMN IF NOT EXISTS prize_pool NUMERIC(12,2) DEFAULT 0;
ALTER TABLE tournaments ADD COLUMN IF NOT EXISTS winner_user_id TEXT;
ALTER TABLE tournaments ADD COLUMN IF NOT EXISTS platform_fee_pct NUMERIC(5,2) DEFAULT 10.00;
ALTER TABLE tournaments ADD COLUMN IF NOT EXISTS started_at TIMESTAMPTZ;
ALTER TABLE tournaments ADD COLUMN IF NOT EXISTS finished_at TIMESTAMPTZ;
ALTER TABLE tournaments ADD COLUMN IF NOT EXISTS metadata JSONB;

ALTER TABLE users ADD COLUMN IF NOT EXISTS wallet_balance NUMERIC(12,2) DEFAULT 0;

ALTER TABLE tournaments DROP CONSTRAINT IF EXISTS tournaments_status_check;

ALTER TABLE tournaments
  ADD CONSTRAINT tournaments_status_check
  CHECK (status IN ('open','waiting','in_progress','finished','cancelled','closed','running'))
  NOT VALID;

CREATE OR REPLACE VIEW v_tournament_summary AS
SELECT
  t.id, t.title, t.game_type, t.entry_fee, t.max_players, t.owner,
  t.status, t.prize_pool, t.winner_user_id, t.platform_fee_pct,
  t.created_at, t.started_at, t.finished_at,
  (SELECT COUNT(*) FROM tournament_participants tp
     WHERE tp.tournament_id = t.id AND tp.status = 'paid') AS paid_players
FROM tournaments t;
