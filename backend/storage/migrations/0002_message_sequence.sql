ALTER TABLE messages ADD COLUMN sequence INTEGER;

UPDATE messages
SET sequence = (
    SELECT COUNT(*)
    FROM messages AS earlier
    WHERE earlier.session_id = messages.session_id
      AND (
          earlier.created_at < messages.created_at
          OR (earlier.created_at = messages.created_at AND earlier.id <= messages.id)
      )
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_messages_session_sequence
    ON messages(session_id, sequence);

