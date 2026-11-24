.PHONY: up down migrate test shell seed chaos loadtest report lint

# Start all services
up:
	docker compose up -d

# Stop all services
down:
	docker compose down

# Run Django migrations
migrate:
	docker compose exec api python manage.py migrate

# Run full test suite
test:
	docker compose exec api python manage.py test --verbosity=2

# Django shell
shell:
	docker compose exec api python manage.py shell

# Seed data (5-10M ad events + sample campaigns)
seed:
	docker compose exec api python scripts/seed_campaigns.py
	docker compose exec api python scripts/seed_ad_events.py --count $(or $(EVENT_COUNT),5000000)

# Run chaos tests
chaos:
	python tests/chaos/chaos_test.py

# Run load tests with Locust
loadtest:
	cd tests/load && locust -f locustfile.py --host=http://localhost:8000

# Run the manual worker kill/restart exercise against a running full stack
chaos-integration:
	python tests/chaos/chaos_test.py

# Apply and check the production schema before starting the production API
migrate-prod:
	docker compose --env-file .env.prod -f docker-compose.prod.yml run --rm api python manage.py migrate --noinput

# Print latency report
report:
	docker compose exec api python manage.py test apps.analytics.tests.test_latency --verbosity=2

# Lint with ruff
lint:
	ruff check .
	ruff format --check .

# Create superuser
superuser:
	docker compose exec api python manage.py createsuperuser

# View logs
logs:
	docker compose logs -f

# Rebuild
rebuild:
	docker compose up -d --build
