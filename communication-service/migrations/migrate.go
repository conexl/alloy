package main

import (
	"flag"
	"fmt"
	"log"
	"os"

	"github.com/golang-migrate/migrate/v4"
	_ "github.com/golang-migrate/migrate/v4/database/postgres"
	_ "github.com/golang-migrate/migrate/v4/source/file"
	"github.com/joho/godotenv"
)

func main() {
	// Загрузка .env файла
	if err := godotenv.Load(); err != nil {
		log.Println("No .env file found")
	}

	// Параметры командной строки
	var (
		command        = flag.String("cmd", "up", "Migration command: up, down, force, version")
		version        = flag.Int("version", 0, "Version for force command")
		migrationsPath = flag.String("path", "migrations", "Path to migrations folder")
	)
	flag.Parse()

	// Получение DSN из переменной окружения
	dsn := os.Getenv("DB_DSN")
	if dsn == "" {
		dsn = "postgres://postgres:postgres@localhost:5432/communication?sslmode=disable"
	}

	// Создание мигратора
	m, err := migrate.New(
		fmt.Sprintf("file://%s", *migrationsPath),
		dsn,
	)
	if err != nil {
		log.Fatalf("Failed to create migrate instance: %v", err)
	}
	defer m.Close()

	// Выполнение команды
	switch *command {
	case "up":
		if err := m.Up(); err != nil && err != migrate.ErrNoChange {
			log.Fatalf("Failed to apply migrations: %v", err)
		}
		log.Println("Migrations applied successfully")

	case "down":
		if err := m.Down(); err != nil && err != migrate.ErrNoChange {
			log.Fatalf("Failed to rollback migrations: %v", err)
		}
		log.Println("Migrations rolled back successfully")

	case "force":
		if err := m.Force(*version); err != nil {
			log.Fatalf("Failed to force version: %v", err)
		}
		log.Printf("Forced version to %d", *version)

	case "version":
		ver, dirty, err := m.Version()
		if err != nil {
			log.Fatalf("Failed to get version: %v", err)
		}
		log.Printf("Current version: %d, dirty: %v", ver, dirty)

	default:
		log.Fatalf("Unknown command: %s", *command)
	}
}
