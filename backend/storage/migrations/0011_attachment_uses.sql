CREATE TABLE attachment_uses (
    attachment_id TEXT NOT NULL REFERENCES attachments(id),
    turn_id TEXT NOT NULL REFERENCES turns(id),
    message_id TEXT NOT NULL REFERENCES messages(id),
    image_mode TEXT NOT NULL DEFAULT 'vision' CHECK(image_mode IN ('vision','ocr')),
    PRIMARY KEY(attachment_id, turn_id)
);
INSERT INTO attachment_uses(attachment_id,turn_id,message_id)
SELECT id,turn_id,message_id FROM attachments WHERE turn_id IS NOT NULL;
CREATE INDEX attachment_uses_message ON attachment_uses(message_id);
