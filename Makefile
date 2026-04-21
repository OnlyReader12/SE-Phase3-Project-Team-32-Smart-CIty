COMPOSE_FILE := infra/docker-compose.yml
K8S_DIR := infra/k8s
DOCKER := docker
KUBECTL := kubectl

.PHONY: help docker-build docker-up docker-down k8s-build k8s-up k8s-down build up down

help:
	@echo "Targets:"
	@echo "  docker-build  Build all Docker Compose services"
	@echo "  docker-up     Build and run Docker Compose stack"
	@echo "  docker-down   Stop Docker Compose stack"
	@echo "  k8s-build     Build local images used by Kubernetes manifests"
	@echo "  k8s-up        Apply Kubernetes manifests"
	@echo "  k8s-down      Delete Kubernetes manifests"
	@echo "  build         docker-build + k8s-build"
	@echo "  up            docker-up + k8s-up"
	@echo "  down          docker-down + k8s-down"

docker-build:
	$(DOCKER) compose -f $(COMPOSE_FILE) build

docker-up:
	$(DOCKER) compose -f $(COMPOSE_FILE) up --build -d

docker-down:
	$(DOCKER) compose -f $(COMPOSE_FILE) down

k8s-build:
	$(DOCKER) build -t smartcity/ingestion-engine:latest core_modules/IngestionEngine
	$(DOCKER) build -t smartcity/persistent-middleware:latest core_modules/PersistentMiddleware
	$(DOCKER) build -t smartcity/ehs-engine:latest core_modules/EHSEngine
	$(DOCKER) build -t smartcity/energy-engine:latest core_modules/EnergyEngine
	$(DOCKER) build -t smartcity/alerting-engine:latest core_modules/AlertingEngine
	$(DOCKER) build -t smartcity/privacy-rbac:latest core_modules/PrivacyRBACService

k8s-up:
	$(KUBECTL) apply -k $(K8S_DIR)

k8s-down:
	$(KUBECTL) delete -k $(K8S_DIR) --ignore-not-found=true

build: docker-build k8s-build

up: docker-up k8s-up

down: docker-down k8s-down
