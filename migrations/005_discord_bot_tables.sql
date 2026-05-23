-- Migration: Add Discord bot support
-- Created: 2025-05-03 (future)

CREATE TABLE IF NOT EXISTS discord_users (
    discord_id BIGINT PRIMARY KEY,
    username VARCHAR(255) NOT NULL,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS discord_guilds (
    guild_id BIGINT PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Mapping between VK and Discord users (optional)
CREATE TABLE IF NOT EXISTS user_platforms (
    user_id SERIAL PRIMARY KEY,
    vk_id BIGINT REFERENCES vk_users(vk_id),
    discord_id BIGINT REFERENCES discord_users(discord_id),
    telegram_id BIGINT,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(vk_id),
    UNIQUE(discord_id),
    UNIQUE(telegram_id)
);