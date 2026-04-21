# Smart City Deployment Layout

This folder standardizes deployment while preserving existing service logic.

## What Was Organized

- Kept core services separate in their existing module folders.
- Added service-level Dockerfiles for consistent image builds.
- Added Docker Compose for local multi-service orchestration.
- Added Kubernetes manifests for cluster orchestration.
- Added root Makefile for one-command build, up, and down operations.
- Added placeholder services for Energy, Alerting, and Privacy/RBAC.
- Kept all existing Python functionality unchanged by default.

## Folder Placement

```text
infra/
  docker-compose.yml
  README.md
  k8s/
    namespace.yaml
    rabbitmq.yaml
    influxdb.yaml
    persistent-middleware.yaml
    ingestion-engine.yaml
    ehs-engine.yaml
    energy-engine.yaml
    alerting-engine.yaml
    privacy-rbac.yaml
    kustomization.yaml
```

## One-Command Operations (Makefile)

From repository root:

```bash
make docker-build
make docker-up
make docker-down

make k8s-build
make k8s-up
make k8s-down
```

Combined targets are also available:

```bash
make build
make up
make down
```

## Run Locally With Docker Compose

From repository root:

```bash
docker compose -f infra/docker-compose.yml up --build
```

## Run On Kubernetes

1. Build images and load/push them to your cluster registry:

```bash
docker build -t smartcity/ingestion-engine:latest core_modules/IngestionEngine
docker build -t smartcity/persistent-middleware:latest core_modules/PersistentMiddleware
docker build -t smartcity/ehs-engine:latest core_modules/EHSEngine
docker build -t smartcity/energy-engine:latest core_modules/EnergyEngine
docker build -t smartcity/alerting-engine:latest core_modules/AlertingEngine
docker build -t smartcity/privacy-rbac:latest core_modules/PrivacyRBACService
```

2. Apply manifests:

```bash
kubectl apply -k infra/k8s
```

## Compatibility Notes

- API chain remains: Ingestion API -> Persistent Middleware API.
- MQTT chain remains: IoT publishers -> Ingestion MQTT broker; EHS consumes via MQTT topic.
- AMQP chain remains: Persistent Middleware publishes telemetry to RabbitMQ.
- Existing localhost defaults are preserved for non-container local runs.
- Placeholder services are intentionally lightweight and do not alter existing business logic.