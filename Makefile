# Variables
IMAGE_NAME = smart-backup:v1.0.0
NETWORK = smart-backup_default

# A variable for tracking files
SOURCES = main.py manager.py cloud_manager.py scanner.py utils.py

# WINPATH by default. In CI GitHub Actions, this will be the current directory.
WINPATH ?= $(PWD)

.PHONY: prepare build local-build run api down logs clean

# Automation: download dependencies if there is no wheels folder
prepare:
	@if [ ! -d "wheels" ] || [ -z "$$(ls -A wheels)" ]; then \
		echo "Wheels not found. Downloading dependencies..."; \
		mkdir -p wheels; \
		pip install --upgrade pip; \
		pip download -r requirements.txt -d wheels --require-hashes; \
	fi

# Building an image
# The build will run automatically only if the files have changed
build: prepare $(SOURCES)
	docker-compose build

# The command for unbiased verification locally
local-build:
	docker build --no-cache --pull -t $(IMAGE_NAME) .

# Infrastructure Startup (MinIO) in the background
run: build
	@if [ -t 0 ]; then \
		read -p "Enter full Windows path: " winpath; \
	else \
		winpath=$(WINPATH); \
	fi; \
	WINPATH="$$winpath" docker-compose up minio -d; \
	echo "Waiting for MinIO to start..."; \
	until docker-compose exec minio curl -sf http://localhost:9000/minio/health/live > /dev/null 2>&1; do \
		echo -n "."; sleep 1; \
	done; \
	echo " MinIO is ready!"; \
	docker-compose run --rm -v "$$winpath:/data" smart-backup

# Start API service alongside MinIO
api: build
	docker-compose up minio api -d
	@echo "API running at http://localhost:8000"
	@echo "Health: http://localhost:8000/health"

# Stopping Everything
down:
	docker-compose down

# View the MinIO logs if something is not connected
logs:
	docker-compose logs minio

# Complete cleaning (removal of the MinIO image and data)
clean:
	docker-compose down -v
	docker rmi $(IMAGE_NAME) 2>/dev/null || true
	docker image prune -f
	rm -rf wheels
