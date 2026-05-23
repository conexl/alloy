-- Migration: Create user profiles table for VK bot
-- Order: must run after vk_users table (004)

CREATE TABLE IF NOT EXISTS user_profiles (
    vk_id BIGINT PRIMARY KEY REFERENCES vk_users(vk_id) ON DELETE CASCADE,
    company_name VARCHAR(500),
    inn VARCHAR(12),
    kpp VARCHAR(9),
    address TEXT,
    phone VARCHAR(20),
    email VARCHAR(255),
    contact_person VARCHAR(255),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_user_profiles_vk_id ON user_profiles(vk_id);