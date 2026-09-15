# Changelog

All notable changes to the FaceDeep API will be documented in this file.

## [2.0.0] - 2026-09-15

### Added
- **API Versioning**: URL-based versioning (`/api/v1/`, `/api/v2/`) with deprecation headers
- **Image Upload Optimization**: Presigned upload URLs, chunked uploads, server-side image processing (resize, WebP conversion, EXIF stripping)
- **Webhooks**: Event-driven webhook system with HMAC signature verification, exponential backoff retry, CRUD management
- **Observability**: Structured JSON logging, Prometheus metrics endpoint, liveness/readiness/startup probes
- **Security Hardening**: API key rotation, IP allowlist, CSP headers, HSTS, audit logging
- **Billing & Metering**: Real-time Redis-backed metering, usage alerts at 80%/90%/100%, auto-throttle
- **Multi-tenancy**: Organizations, teams, RBAC (admin/editor/viewer), team-scoped API keys, data isolation
- **SLA Endpoints**: Status page, SLA info, data retention policies, compliance documentation
- **v2 Face Endpoints**: Richer responses with `processing_time_ms`, `model_version`, `similarity`, `LivenessInfo`, pagination
- **Docker Compose**: Added Redis service, security hardening (read-only, no-new-privileges)
- **CI/CD**: GitHub Actions workflow for lint, test, build, deploy
- **Kubernetes**: Helm chart with HPA auto-scaling, ingress, health probes

### Changed
- Upgraded FastAPI app version to 2.0.0
- CORS lockdown in production mode
- Middleware stack now includes SecurityHeadersMiddleware and APIVersioningMiddleware

## [1.0.0] - 2026-01-01

### Added
- Initial release with face recognition, enrollment, matching
- Authentication (JWT + API key)
- OAuth (Google, Apple)
- Rate limiting (per API key, tier-based)
- Redis caching with graceful fallback
- Async worker pool for background jobs
- Stripe billing integration
- ArcFace model with liveness detection
- ChromaDB vector store
