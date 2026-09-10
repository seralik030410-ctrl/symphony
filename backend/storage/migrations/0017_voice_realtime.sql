ALTER TABLE voice_settings RENAME TO voice_settings_stage11;

CREATE TABLE voice_settings (
    session_id TEXT PRIMARY KEY REFERENCES sessions(id) ON DELETE CASCADE,
    mode TEXT NOT NULL DEFAULT 'auto' CHECK (mode IN ('auto','omni','modular')),
    realtime_profile_id TEXT REFERENCES provider_profiles(id) ON DELETE SET NULL,
    realtime_model TEXT NOT NULL DEFAULT 'gpt-realtime',
    input_codec TEXT NOT NULL DEFAULT 'pcm16',
    output_codec TEXT NOT NULL DEFAULT 'pcm16',
    sample_rate INTEGER NOT NULL DEFAULT 24000 CHECK (sample_rate BETWEEN 8000 AND 48000),
    server_vad INTEGER NOT NULL DEFAULT 1 CHECK (server_vad IN (0,1)),
    tool_support INTEGER NOT NULL DEFAULT 1 CHECK (tool_support IN (0,1)),
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

INSERT INTO voice_settings(
    session_id,mode,stt_profile_id,tts_profile_id,stt_model,tts_model,language,voice,
    input_device_id,output_device_id,vad_threshold,vad_silence_ms,save_audio,updated_at
) SELECT session_id,'auto',stt_profile_id,tts_profile_id,stt_model,tts_model,language,voice,
    input_device_id,output_device_id,vad_threshold,vad_silence_ms,save_audio,updated_at
FROM voice_settings_stage11;

DROP TABLE voice_settings_stage11;

ALTER TABLE voice_sessions ADD COLUMN requested_mode TEXT NOT NULL DEFAULT 'modular';
ALTER TABLE voice_sessions ADD COLUMN resolved_mode TEXT;
ALTER TABLE voice_sessions ADD COLUMN provider_profile_id TEXT REFERENCES provider_profiles(id) ON DELETE SET NULL;
ALTER TABLE voice_sessions ADD COLUMN provider_session_id TEXT;
ALTER TABLE voice_sessions ADD COLUMN input_audio_sequence INTEGER NOT NULL DEFAULT 0;
ALTER TABLE voice_sessions ADD COLUMN output_audio_sequence INTEGER NOT NULL DEFAULT 0;
ALTER TABLE voice_sessions ADD COLUMN first_audio_in_at TEXT;
ALTER TABLE voice_sessions ADD COLUMN first_transcript_at TEXT;
ALTER TABLE voice_sessions ADD COLUMN first_text_at TEXT;
ALTER TABLE voice_sessions ADD COLUMN first_audio_out_at TEXT;
ALTER TABLE voice_sessions ADD COLUMN usage_json TEXT;
