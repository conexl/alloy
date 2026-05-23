package config

import (
	"os"
	"strconv"
	"strings"
	"time"

	"github.com/joho/godotenv"
)

type Config struct {
	// Redis
	RedisURL string

	// PostgreSQL
	DBDSN string

	// SMTP
	SMTPHost  string
	SMTPPort  int
	SMTPUser  string
	SMTPPass  string
	SMTPFrom  string
	SMTPDelay time.Duration

	// IMAP
	IMAPHost         string
	IMAPPort         int
	IMAPUser         string
	IMAPPass         string
	IMAPPollInterval time.Duration
	IMAPFolder       string
	IMAPExtraFolders []string // дополнительные папки: Spam, Junk и т.д.

	// OpenRouter
	OpenRouterAPIKey string
	OpenRouterModel  string

	// Поведение
	MaxEmailsPerItem int
}

func Load() (*Config, error) {
	godotenv.Load()

	smtpPort, _ := strconv.Atoi(getEnv("SMTP_PORT", "587"))
	smtpDelay, _ := time.ParseDuration(getEnv("SMTP_DELAY", "1s"))
	imapPort, _ := strconv.Atoi(getEnv("IMAP_PORT", "993"))
	imapPollInterval, _ := time.ParseDuration(getEnv("IMAP_POLL_INTERVAL", "300s"))
	maxEmailsPerItem, _ := strconv.Atoi(getEnv("MAX_EMAILS_PER_ITEM", "5"))

	extraFolders := []string{}
	if extra := getEnv("IMAP_EXTRA_FOLDERS", ""); extra != "" {
		for _, f := range strings.Split(extra, ",") {
			f = strings.TrimSpace(f)
			if f != "" {
				extraFolders = append(extraFolders, f)
			}
		}
	}

	return &Config{
		RedisURL:         getEnv("REDIS_URL", "redis://localhost:6379"),
		DBDSN:            getEnv("DB_DSN", "postgres://postgres:postgres@localhost:5432/communication?sslmode=disable"),
		SMTPHost:         getEnv("SMTP_HOST", "localhost"),
		SMTPPort:         smtpPort,
		SMTPUser:         getEnv("SMTP_USER", ""),
		SMTPPass:         getEnv("SMTP_PASS", ""),
		SMTPFrom:         getEnv("SMTP_FROM", "noreply@localhost"),
		SMTPDelay:        smtpDelay,
		IMAPHost:         getEnv("IMAP_HOST", "localhost"),
		IMAPPort:         imapPort,
		IMAPUser:         getEnv("IMAP_USER", ""),
		IMAPPass:         getEnv("IMAP_PASS", ""),
		IMAPPollInterval: imapPollInterval,
		IMAPFolder:       getEnv("IMAP_FOLDER", "INBOX"),
		IMAPExtraFolders: extraFolders,
		OpenRouterAPIKey: getEnv("OPENROUTER_API_KEY", ""),
		MaxEmailsPerItem: maxEmailsPerItem,
		OpenRouterModel:  getEnv("OPENROUTER_MODEL", "openai/gpt-5.2"),
	}, nil
}

func getEnv(key, defaultValue string) string {
	if value := os.Getenv(key); value != "" {
		return value
	}
	return defaultValue
}
