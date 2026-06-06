# ADR-0006: Upload files stored on imsor-web host filesystem

## Decision

Uploaded image files are written to a configured upload root directory on the imsor-web host, organised as `{upload_root}/{username}/{session_timestamp}/`. imsor-web registers each file with central-service using a path prefix that the existing path-mapping system resolves to that directory. Uploaded files are served through the existing `/serve/<image_id>` route with no new serving infrastructure.

## Context

Three alternatives were considered:

**Object storage (S3/R2/MinIO):** aligns with the long-term federation direction ("Image references will eventually need to be globally addressable URLs") but adds an external service dependency with no current consumer. No other part of the system is built around object storage yet; introducing it here would be the tail wagging the dog.

**Store in central-service, add a file-serving endpoint:** concentrates file ownership in the API layer but requires a new `/images/{id}/file` route in central-service and breaks the clean separation between the metadata API and file serving that the path-mapping model provides.

**Store on imsor-web host, fit into path-mapping (chosen):** no new services, no new serving routes, and the upload directory is just another entry in the path-mapping config. Migration to object storage is deferred to when federation becomes real scope.

## Consequence

Upload files are local to the imsor-web host that received the upload. They cannot be served from a different imsor-web instance. When federation becomes real scope, uploaded files will need to be migrated to a globally addressable store, and the `file_path` column will need to become a URL.
