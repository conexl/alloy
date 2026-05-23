DROP TABLE IF EXISTS orphan_emails;
DROP TRIGGER IF EXISTS update_orphan_emails_updated_at ON orphan_emails;
ALTER TABLE email_ai_queue DROP COLUMN IF EXISTS attachments;
