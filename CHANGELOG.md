\# Changelog



All notable changes to this project will be documented in this file.



The format is based on Keep a Changelog  

and this project adheres to Semantic Versioning.



Code Job Orchestrator

Mandescu Victor-Ioan 342C4

Pasca Robert-Paul 342C4

\---



\## \[Unreleased]



\### Added

\- Ongoing improvements and bug fixes



\### Planned

\- Docker Swarm deployment:

&#x20; - Convert Docker Compose setup to Swarm stack

&#x20; - Enable service scaling and orchestration



\- CI/CD pipeline:

&#x20; - Automated build and deployment using GitLab CI/CD (or similar)

&#x20; - Build Docker images and push to registry

&#x20; - Automatic deployment to cluster



\- Frontend integration improvements:

&#x20; - Full integration with backend services through Kong

&#x20; - Improved job management UI (job submission, status, logs)



\- Monitoring enhancements:

&#x20; - Configure Prometheus to collect metrics from services

&#x20; - Create Grafana dashboards for:

&#x20;   - service health

&#x20;   - job processing metrics

&#x20;   - system performance



\- Observability improvements:

&#x20; - Add centralized logging across services

&#x20; - Improve visibility of worker execution and errors



\---



\## \[0.2.0] - 2026-04-22



\### Added

\- Implemented Worker Service:

&#x20; - Consumes jobs from Redis queue

&#x20; - Executes jobs using subprocess

&#x20; - Supports job cancellation and status updates



\- Added Redis for asynchronous job queue



\- Integrated all services through Kong API Gateway:

&#x20; - `/api/auth` → Authentication Service

&#x20; - `/api/service` → Job API Service

&#x20; - `/` → Frontend



\---



\### Changed

\- Refactored service communication to use internal Docker networking

\- Improved worker execution logic and logging



\---



\### Fixed

\- Fixed worker not processing jobs due to incorrect endpoint paths

\- Fixed argument passing issues to job scripts

\- Fixed initial request latency



\---



\## \[0.1.3] - 2026-04-19



\### Added

\- Implemented Persistence Service:

&#x20; - PostgreSQL integration

&#x20; - Job lifecycle management (queued, running, completed, failed)

&#x20; - Cancel flag and retry functionality



\---



\### Changed

\- Standardized API routes using `/persistence/...`

\- Improved database schema and job state handling



\---



\## \[0.1.2] - 2026-04-16



\### Added

\- Implemented Job API Service:

&#x20; - Create, cancel, retry, delete jobs

&#x20; - Role-based access (admin vs user)

&#x20; - Integration with Persistence Service

&#x20; - Integration with Redis queue



\---



\### Changed

\- Improved API structure and endpoint consistency

\- Cleaned up environment variable configuration



\---



\## \[0.1.1] - 2026-04-13



\### Added

\- Implemented Authentication Service:

&#x20; - User registration and login

&#x20; - JWT-based authentication

&#x20; - Refresh token mechanism



\---



\## \[0.1.0] - 2026-04-06



\### Added

\- Initial version of frontend:

&#x20; - Minimal configuration with Flask and HTML/CSS/JS



\- Connected frontend to Kong API Gateway for job management



\- All services deployed and managed via Portainer



\- Added monitoring stack:

&#x20; - Prometheus

&#x20; - Grafana

