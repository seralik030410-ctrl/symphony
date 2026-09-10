-- Vision 2 keeps the selected frame set on the attachment use, rather than on
-- the mutable pending attachment.  This makes the first send and every retry
-- reproducible even when the client has stopped a camera/screen capture.
ALTER TABLE attachment_uses ADD COLUMN ordinal INTEGER NOT NULL DEFAULT 0;
ALTER TABLE attachment_uses ADD COLUMN provenance_json TEXT NOT NULL DEFAULT '{}';
ALTER TABLE attachment_uses ADD COLUMN snapshot_json TEXT NOT NULL DEFAULT '{}';
ALTER TABLE attachment_uses ADD COLUMN estimated_tokens INTEGER NOT NULL DEFAULT 0 CHECK(estimated_tokens >= 0);

-- Old Stage 6 uses were stored in attachment creation order.  Preserve that
-- order when upgrading an existing database before new uses receive an
-- explicit ordinal from the request.
UPDATE attachment_uses
SET ordinal = (
    SELECT COUNT(*)
    FROM attachment_uses AS earlier
    JOIN attachments AS earlier_attachment ON earlier_attachment.id = earlier.attachment_id
    JOIN attachments AS current_attachment ON current_attachment.id = attachment_uses.attachment_id
    WHERE earlier.turn_id = attachment_uses.turn_id
      AND (earlier_attachment.created_at < current_attachment.created_at
           OR (earlier_attachment.created_at = current_attachment.created_at
               AND earlier.attachment_id <= attachment_uses.attachment_id))
) - 1;

CREATE UNIQUE INDEX attachment_uses_turn_ordinal ON attachment_uses(turn_id, ordinal);
CREATE INDEX attachment_uses_turn_frame ON attachment_uses(turn_id, image_mode, ordinal);
