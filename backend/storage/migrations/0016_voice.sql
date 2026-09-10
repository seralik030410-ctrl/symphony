CREATE TABLE voice_settings (
    session_id TEXT PRIMARY KEY REFERENCES sessions(id) ON DELETE CASCADE,
    mode TEXT NOT NULL DEFAULT 'modular' CHECK (mode IN ('modular')),
    stt_profile_id TEXT REFERENCES provider_profiles(id) ON DELETE SET NULL,
    tts_profile_id TEXT REFERENCES provider_profiles(id) ON DELETE SET NULL,
    stt_model TEXT NOT NULL DEFAULT 'mock-stt',
    tts_model TEXT NOT NULL DEFAULT 'mock-tts',
    language TEXT NOT NULL DEFAULT 'ru',
    voice TEXT NOT NULL DEFAULT 'default',
    input_device_id TEXT,
    output_device_id TEXT,
    vad_threshold REAL NOT NULL DEFAULT 0.025 CHECK (vad_threshold BETWEEN 0.001 AND 1),
    vad_silence_ms INTEGER NOT NULL DEFAULT 900 CHECK (vad_silence_ms BETWEEN 200 AND 5000),
    save_audio INTEGER NOT NULL DEFAULT 0 CHECK (save_audio IN (0,1)),
    updated_at TEXT NOT NULL
);

CREATE TABLE voice_sessions (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    status TEXT NOT NULL CHECK (status IN ('idle','listening','transcribing','thinking','speaking','interrupted','cancelled','error')),
    turn_id TEXT REFERENCES turns(id) ON DELETE SET NULL,
    transcript TEXT NOT NULL DEFAULT '',
    transcript_final INTEGER NOT NULL DEFAULT 0 CHECK (transcript_final IN (0,1)),
    error_code TEXT,
    error_message TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    finished_at TEXT
);

CREATE INDEX idx_voice_sessions_scope ON voice_sessions(session_id, created_at DESC);
CREATE UNIQUE INDEX idx_voice_sessions_turn ON voice_sessions(turn_id) WHERE turn_id IS NOT NULL;

CREATE TABLE voice_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    voice_session_id TEXT NOT NULL REFERENCES voice_sessions(id) ON DELETE CASCADE,
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    sequence INTEGER NOT NULL,
    type TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(voice_session_id, sequence)
);

CREATE INDEX idx_voice_events_sequence ON voice_events(voice_session_id, sequence);

