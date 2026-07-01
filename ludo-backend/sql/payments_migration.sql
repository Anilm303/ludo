-- Migration: payment + participant columns
-- Run against the configured PostgreSQL. Idempotent: every statement is
-- safe to re-run.

ALTER TABLE payments ADD COLUMN IF NOT EXISTS currency TEXT DEFAULT 'NPR';
ALTER TABLE payments ADD COLUMN IF NOT EXISTS esewa_ref_id TEXT;
ALTER TABLE payments ADD COLUMN IF NOT EXISTS raw_response JSONB;
ALTER TABLE payments ADD COLUMN IF NOT EXISTS verified_at TIMESTAMPTZ;
ALTER TABLE payments ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT now();
ALTER TABLE payments ALTER COLUMN status SET DEFAULT 'pending';

CREATE INDEX IF NOT EXISTS idx_payments_user ON payments (user_id);
CREATE INDEX IF NOT EXISTS idx_payments_tournament ON payments (tournament_id);
CREATE INDEX IF NOT EXISTS idx_payments_user_tournament_status
  ON payments (user_id, tournament_id, status);

ALTER TABLE tournament_participants
  ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'pending';
ALTER TABLE tournament_participants
  ADD COLUMN IF NOT EXISTS payment_pid TEXT;
ALTER TABLE tournament_participants
  ADD COLUMN IF NOT EXISTS joined_at TIMESTAMPTZ;

CREATE UNIQUE INDEX IF NOT EXISTS uq_tournament_participant_per_tournament
  ON tournament_participants (tournament_id, user_id);

CREATE OR REPLACE VIEW v_user_payments AS
SELECT
  p.pid,
  p.user_id,
  p.tournament_id,
  t.title AS tournament_title,
  p.amount,
  p.currency,
  p.status,
  p.esewa_ref_id,
  p.created_at,
  p.verified_at
FROM payments p
LEFT JOIN tournaments t ON t.id = p.tournament_id;
