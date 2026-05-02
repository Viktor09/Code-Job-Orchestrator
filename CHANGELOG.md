# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Ongoing improvements and bug fixes

### Planned

- Observability improvements:
    - Add centralized logging across services
    - Improve visibility of worker execution and errors



---
## \[0.5.0] - 2026-04-27
### Added
- CI/CD pipeline:
    - Automated build and deployment using GitHub Actions
    - Build Docker images and push to registry
    - Automatic deployment to cluster
- Grafana exported dashboard
### Fixed
- Frontend was not properly returning errors at login and registration endpoints
### Changed
- Updated Grafana dashboards to include metrics from Kong

## \[0.4.0] - 2026-04-26
### Changed
- Docker Swarm deployment:
    - Enable service scaling and orchestration

## \[0.3.0] - 2026-04-25
### Added

- Monitoring enhancements:
    - Configure Prometheus to collect metrics from services
    - Create Grafana dashboards for:
        - service health
        - job processing metrics
        - system performance
- Frontend integration improvements:
    - Full integration with backend services through Kong
    - Improved job management UI (job submission, status, logs)
- Docker Swarm deployment:
    - Convert Docker Compose setup to Swarm stack


## \[0.2.0] - 2026-04-22

### Added
- Implemented Worker Service:
    - Consumes jobs from Redis queue
    - Executes jobs using subprocess
    - Supports job cancellation and status updates
- Added Redis for asynchronous job queue
- Integrated all services through Kong API Gateway:
    - `/api/auth` → Authentication Service
    - `/api/service` → Job API Service
    - `/` → Frontend

---

### Changed
- Refactored service communication to use internal Docker networking
- Improved worker execution logic and logging

---

### Fixed
- Fixed worker not processing jobs due to incorrect endpoint paths
- Fixed argument passing issues to job scripts
- Fixed initial request latency

---

## \[0.1.3] - 2026-04-19

### Added
- Implemented Persistence Service:
    - PostgreSQL integration
    - Job lifecycle management (queued, running, completed, failed)
    - Cancel flag and retry functionality

---

### Changed
- Standardized API routes using `/persistence/...`
- Improved database schema and job state handling

---

## \[0.1.2] - 2026-04-16

### Added
- Implemented Job API Service:
    - Create, cancel, retry, delete jobs
    - Role-based access (admin vs user)
    - Integration with Persistence Service
    - Integration with Redis queue

---

### Changed
- Improved API structure and endpoint consistency
- Cleaned up environment variable configuration

---

## \[0.1.1] - 2026-04-13

### Added
- Implemented Authentication Service:
    - User registration and login
    - JWT-based authentication
    - Refresh token mechanism

---

## \[0.1.0] - 2026-04-06

### Added
- Initial version of frontend:
    - Minimal configuration with Flask and HTML/CSS/JS
- Connected frontend to Kong API Gateway for job management
- All services deployed and managed via Portainer
- Added monitoring stack:
    - Prometheus
    - Grafana
