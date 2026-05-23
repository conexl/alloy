.PHONY: help build up down logs clean ps health

help:  ## Show this help message
	@echo 'Usage: make [target]'
	@echo ''
	@echo 'Available targets:'
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  %-15s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

build:  ## Build all Docker images
	docker-compose build

up:  ## Start all services
	docker-compose up -d
	@echo "Services starting..."
	@echo "Communication service: http://localhost:8080"
	@echo "Report service: http://localhost:8081"
	@echo "VK Bot: Long Poll (no HTTP port)"
	@echo "Supplier Finder: background worker"
	@echo "MailHog UI: http://localhost:8025"
	@echo "MailDev UI: http://localhost:1080"

down:  ## Stop all services
	docker-compose down

logs:  ## Show logs from all services
	docker-compose logs -f

logs-comm:  ## Show logs from communication service
	@docker-compose logs -f communication-service

logs-report:  ## Show logs from report service
	@docker-compose logs -f report-service

logs-vk:  ## Show logs from VK bot
	@docker-compose logs -f vk-bot

logs-supplier:  ## Show logs from supplier-finder
	@docker-compose logs -f supplier-finder

clean:  ## Remove all containers, volumes, and images
	docker-compose down -v
	docker-compose rm -f
	@echo "Cleaned up"

restart:  ## Restart all services
	docker-compose restart

ps:  ## Show running services
	docker-compose ps

db-shell:  ## Connect to PostgreSQL
	docker-compose exec postgres psql -U postgres -d tender

redis-cli:  ## Connect to Redis CLI
	docker-compose exec redis redis-cli

health:  ## Check health of all services
	@curl -s http://localhost:8080/health | jq || echo "communication-service not ready"
	@curl -s http://localhost:8081/health | jq || echo "report-service not ready"
	@curl -s http://localhost:8000/health | jq || echo "supplier-finder not ready"
	@docker-compose ps | grep -q "vk-bot.*Up" || echo "vk-bot not running"
	@docker-compose exec postgres pg_isready -U postgres || echo "postgres not ready"
	@docker-compose exec redis redis-cli ping || echo "redis not ready"
