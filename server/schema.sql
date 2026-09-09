CREATE TABLE IF NOT EXISTS sessions (
  id text PRIMARY KEY, state jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS identities (
  token_hash text PRIMARY KEY, player_id text NOT NULL, session_id text NOT NULL REFERENCES sessions(id)
);
CREATE TABLE IF NOT EXISTS events (
  id bigserial PRIMARY KEY, session_id text NOT NULL REFERENCES sessions(id), command_id text NOT NULL,
  payload jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(session_id, command_id)
);
CREATE TABLE IF NOT EXISTS entities (
  session_id text NOT NULL REFERENCES sessions(id), id text NOT NULL, kind text NOT NULL, properties jsonb NOT NULL,
  PRIMARY KEY(session_id,id)
);
CREATE TABLE IF NOT EXISTS relationships (
  session_id text NOT NULL, source text NOT NULL, target text NOT NULL, kind text NOT NULL,
  PRIMARY KEY(session_id,source,target,kind),
  FOREIGN KEY(session_id,source) REFERENCES entities(session_id,id),
  FOREIGN KEY(session_id,target) REFERENCES entities(session_id,id)
);
CREATE TABLE IF NOT EXISTS ai_configs (
  version bigserial PRIMARY KEY, config jsonb NOT NULL, encrypted_key text,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS admin_tokens (
  token_hash text PRIMARY KEY, expires_at timestamptz NOT NULL
);
CREATE TABLE IF NOT EXISTS generated_scenarios (
  fingerprint text PRIMARY KEY, title_key text NOT NULL UNIQUE, title text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);
