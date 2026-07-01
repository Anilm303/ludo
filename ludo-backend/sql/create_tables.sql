-- Create tables for chess backend
-- Run this against the `chess_db` database

-- users
CREATE TABLE IF NOT EXISTS users (
  id SERIAL PRIMARY KEY,
  username TEXT UNIQUE NOT NULL,
  email TEXT,
  first_name TEXT,
  last_name TEXT,
  password_hash TEXT,
  profile_image TEXT,
  bio TEXT,
  fcm_token TEXT,
  friends JSONB,
  friend_requests JSONB,
  profile JSONB,
  created_at TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE users ADD COLUMN IF NOT EXISTS profile_image TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS bio TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS fcm_token TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS friends JSONB DEFAULT '[]'::jsonb;
ALTER TABLE users ADD COLUMN IF NOT EXISTS friend_requests JSONB DEFAULT '[]'::jsonb;
ALTER TABLE users ADD COLUMN IF NOT EXISTS profile JSONB;
ALTER TABLE users ADD COLUMN IF NOT EXISTS last_seen TIMESTAMPTZ;
ALTER TABLE users ALTER COLUMN created_at SET DEFAULT now();

-- messages
CREATE TABLE IF NOT EXISTS messages (
  id TEXT PRIMARY KEY,
  sender TEXT NOT NULL,
  receiver TEXT NOT NULL,
  message_type TEXT,
  text TEXT,
  media_url TEXT,
  thumbnail_url TEXT,
  reply_to_id TEXT,
  status TEXT DEFAULT 'sent',
  is_read BOOLEAN DEFAULT FALSE,
  reactions JSONB,
  metadata JSONB,
  timestamp TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE messages ALTER COLUMN id TYPE TEXT USING id::text;
ALTER TABLE messages ALTER COLUMN id DROP DEFAULT;

ALTER TABLE messages ADD COLUMN IF NOT EXISTS media_url TEXT;
ALTER TABLE messages ADD COLUMN IF NOT EXISTS thumbnail_url TEXT;
ALTER TABLE messages ADD COLUMN IF NOT EXISTS reply_to_id TEXT;
ALTER TABLE messages ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'sent';
ALTER TABLE messages ADD COLUMN IF NOT EXISTS is_read BOOLEAN DEFAULT FALSE;
ALTER TABLE messages ADD COLUMN IF NOT EXISTS reactions JSONB DEFAULT '{}'::jsonb;
ALTER TABLE messages ADD COLUMN IF NOT EXISTS metadata JSONB;
ALTER TABLE messages ADD COLUMN IF NOT EXISTS timestamp TIMESTAMPTZ;

DROP TABLE IF EXISTS group_call_history;
DROP TABLE IF EXISTS group_messages;
DROP TABLE IF EXISTS groups;

-- groups
CREATE TABLE IF NOT EXISTS groups (
  id TEXT PRIMARY KEY,
  name TEXT,
  avatar TEXT,
  created_by TEXT,
  admins JSONB,
  members JSONB,
  created_at TIMESTAMPTZ,
  updated_at TIMESTAMPTZ,
  last_message TEXT,
  last_message_time TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS group_messages (
  id TEXT PRIMARY KEY,
  group_id TEXT NOT NULL,
  sender TEXT NOT NULL,
  text TEXT,
  message_type TEXT,
  media_url TEXT,
  thumbnail_url TEXT,
  timestamp TIMESTAMPTZ,
  seen_by JSONB,
  FOREIGN KEY (group_id) REFERENCES groups (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS group_call_history (
  id TEXT PRIMARY KEY,
  group_id TEXT NOT NULL,
  started_by TEXT,
  call_type TEXT,
  participants JSONB,
  status TEXT,
  started_at TIMESTAMPTZ,
  ended_at TIMESTAMPTZ,
  FOREIGN KEY (group_id) REFERENCES groups (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS stories (
  id TEXT PRIMARY KEY,
  username TEXT NOT NULL,
  media_url TEXT,
  thumbnail_url TEXT,
  media_type TEXT,
  timestamp TIMESTAMPTZ,
  viewers JSONB,
  reactions JSONB,
  reaction_details JSONB
);

CREATE TABLE IF NOT EXISTS notes (
  id TEXT PRIMARY KEY,
  username TEXT NOT NULL,
  text_content TEXT,
  media_url TEXT,
  thumbnail_url TEXT,
  media_type TEXT,
  timestamp TIMESTAMPTZ,
  viewers JSONB
);

CREATE TABLE IF NOT EXISTS auth_token_blocklist (
  jti TEXT PRIMARY KEY,
  token_type TEXT,
  revoked_at TIMESTAMPTZ,
  expires_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS password_reset_tokens (
  token TEXT PRIMARY KEY,
  username TEXT NOT NULL,
  expires_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS game_rooms (
  room_id TEXT PRIMARY KEY,
  room_data JSONB NOT NULL,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS audit_events (
  id BIGSERIAL PRIMARY KEY,
  event_type TEXT NOT NULL,
  payload JSONB,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS media_files (
  id TEXT PRIMARY KEY,
  category TEXT NOT NULL,
  filename TEXT NOT NULL,
  content_type TEXT,
  data BYTEA NOT NULL,
  created_at TIMESTAMPTZ DEFAULT now()
);

-- payments table for tournament/in-app purchases
CREATE TABLE IF NOT EXISTS payments (
  id BIGSERIAL PRIMARY KEY,
  pid TEXT UNIQUE NOT NULL,
  user_id TEXT,
  tournament_id TEXT,
  amount NUMERIC(12,2) NOT NULL,
  currency TEXT DEFAULT 'NPR',
  status TEXT DEFAULT 'pending', -- pending, paid, failed
  esewa_ref_id TEXT,
  raw_response JSONB,
  created_at TIMESTAMPTZ DEFAULT now(),
  verified_at TIMESTAMPTZ
);

-- tournaments
CREATE TABLE IF NOT EXISTS tournaments (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  game_type TEXT NOT NULL, -- 'chess' or 'ludo'
  entry_fee NUMERIC(12,2) DEFAULT 0,
  max_players INT DEFAULT 2,
  owner TEXT,
  status TEXT DEFAULT 'open', -- open, closed, running, finished
  metadata JSONB,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS tournament_participants (
  id BIGSERIAL PRIMARY KEY,
  tournament_id TEXT NOT NULL REFERENCES tournaments(id) ON DELETE CASCADE,
  user_id TEXT NOT NULL,
  status TEXT DEFAULT 'pending', -- pending, paid, joined
  payment_pid TEXT,
  joined_at TIMESTAMPTZ
);

-- Performance Indexes for Messaging Optimization
CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages(sender, receiver, timestamp);
CREATE INDEX IF NOT EXISTS idx_messages_sync ON messages(receiver, timestamp);
CREATE INDEX IF NOT EXISTS idx_group_messages_query ON group_messages(group_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_users_online ON users(username) WHERE last_seen > now() - interval '5 minutes';
