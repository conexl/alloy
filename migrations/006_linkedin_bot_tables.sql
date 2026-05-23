-- Migration: Add LinkedIn bot support
-- Created: 2025-05-03 (future)

CREATE TABLE IF NOT EXISTS linkedin_profiles (
    linkedin_id VARCHAR(255) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    email VARCHAR(255),
    company VARCHAR(255),
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS linkedin_conversations (
    conversation_id VARCHAR(255) PRIMARY KEY,
    participant_id VARCHAR(255) REFERENCES linkedin_profiles(linkedin_id),
    item_id INTEGER REFERENCES items(id),
    last_message_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);