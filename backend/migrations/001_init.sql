CREATE TABLE IF NOT EXISTS sources (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  provider_type TEXT NOT NULL,
  enabled BOOLEAN NOT NULL DEFAULT TRUE,
  mode TEXT NOT NULL DEFAULT 'both' CHECK (mode IN ('hot', 'new', 'both')),
  weight INTEGER NOT NULL DEFAULT 3 CHECK(weight >= 1 AND weight <= 5),
  last_fetch TIMESTAMPTZ,
  is_mock BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
ALTER TABLE sources ADD COLUMN IF NOT EXISTS mode TEXT NOT NULL DEFAULT 'both';
ALTER TABLE sources ADD COLUMN IF NOT EXISTS last_fetch TIMESTAMPTZ;
ALTER TABLE sources DROP CONSTRAINT IF EXISTS sources_mode_check;
ALTER TABLE sources ADD CONSTRAINT sources_mode_check CHECK (mode IN ('hot', 'new', 'both'));

CREATE TABLE IF NOT EXISTS raw_signals (
  id TEXT PRIMARY KEY,
  source_id TEXT NOT NULL REFERENCES sources(id),
  title TEXT NOT NULL,
  content TEXT,
  url TEXT NOT NULL,
  author TEXT,
  publish_time TIMESTAMPTZ NOT NULL,
  metrics JSONB NOT NULL DEFAULT '{}'::jsonb,
  extracted_keywords TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
  language TEXT NOT NULL DEFAULT 'zh',
  fingerprint TEXT NOT NULL,
  weak_fingerprint TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_raw_signals_publish_time ON raw_signals(publish_time DESC);
CREATE INDEX IF NOT EXISTS idx_raw_signals_source_id ON raw_signals(source_id);
CREATE INDEX IF NOT EXISTS idx_raw_signals_fingerprint ON raw_signals(fingerprint);
CREATE INDEX IF NOT EXISTS idx_raw_signals_weak_fingerprint ON raw_signals(weak_fingerprint);

CREATE TABLE IF NOT EXISTS events (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  summary TEXT NOT NULL,
  category TEXT NOT NULL,
  heat_score DOUBLE PRECISION NOT NULL,
  growth_rate DOUBLE PRECISION NOT NULL,
  first_seen_time TIMESTAMPTZ NOT NULL,
  last_updated_time TIMESTAMPTZ NOT NULL,
  source_count INTEGER NOT NULL,
  signals_count INTEGER NOT NULL,
  top_keywords TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
  is_breaking BOOLEAN NOT NULL DEFAULT FALSE,
  breaking_until TIMESTAMPTZ,
  source_breakdown JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_events_heat_score ON events(heat_score DESC);
CREATE INDEX IF NOT EXISTS idx_events_is_breaking ON events(is_breaking, heat_score DESC);
CREATE INDEX IF NOT EXISTS idx_events_category ON events(category, heat_score DESC);

CREATE TABLE IF NOT EXISTS event_signal_mapping (
  event_id TEXT NOT NULL REFERENCES events(id) ON DELETE CASCADE,
  signal_id TEXT NOT NULL REFERENCES raw_signals(id) ON DELETE CASCADE,
  PRIMARY KEY(event_id, signal_id)
);

CREATE TABLE IF NOT EXISTS event_heat_history (
  id BIGSERIAL PRIMARY KEY,
  event_id TEXT NOT NULL REFERENCES events(id) ON DELETE CASCADE,
  observed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  heat_score DOUBLE PRECISION NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_event_heat_history_event_time ON event_heat_history(event_id, observed_at DESC);

CREATE TABLE IF NOT EXISTS daily_snapshots (
  id BIGSERIAL PRIMARY KEY,
  snapshot_date DATE NOT NULL,
  version TEXT NOT NULL,
  payload JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE(snapshot_date, version)
);

CREATE TABLE IF NOT EXISTS pipeline_runs (
  id BIGSERIAL PRIMARY KEY,
  started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  finished_at TIMESTAMPTZ,
  status TEXT NOT NULL,
  message TEXT
);

INSERT INTO sources (id, name, provider_type, enabled, mode, weight, is_mock)
VALUES
  ('kr36', '36氪', 'rss_hot', TRUE, 'both', 4, FALSE),
  ('huxiu', '虎嗅', 'rss', TRUE, 'both', 3, FALSE),
  ('sspai', '少数派', 'rss', TRUE, 'both', 3, FALSE),
  ('zhihu_hot', '知乎热榜', 'hotlist', TRUE, 'hot', 4, FALSE),
  ('weibo_hot', '微博热榜', 'hotlist', TRUE, 'hot', 5, FALSE),
  ('jike_mock', '即刻(MOCK)', 'mock', TRUE, 'new', 3, TRUE),
  ('github_trending', 'GitHub Trending', 'tech_signal', TRUE, 'both', 4, FALSE),
  ('huggingface_trending', 'HuggingFace Trending', 'tech_signal', TRUE, 'both', 4, FALSE),
  ('bilibili_mock', 'B站科技(MOCK)', 'mock', TRUE, 'new', 3, TRUE),
  ('x_trending', 'X Trending', 'hotlist', TRUE, 'hot', 4, FALSE),
  ('mock_burst', '种子爆发信号(MOCK)', 'mock', TRUE, 'both', 5, TRUE)
ON CONFLICT(id) DO UPDATE SET
  name = EXCLUDED.name,
  provider_type = EXCLUDED.provider_type,
  mode = EXCLUDED.mode,
  updated_at = NOW();
