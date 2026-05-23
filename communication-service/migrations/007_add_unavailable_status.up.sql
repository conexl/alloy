-- Add 'unavailable' status to orphan_emails
ALTER TABLE orphan_emails 
DROP CONSTRAINT IF EXISTS orphan_emails_status_check;

ALTER TABLE orphan_emails 
ADD CONSTRAINT orphan_emails_status_check 
CHECK (status IN ('pending', 'matched', 'expired', 'manual_review', 'unavailable'));
