# Service Contract: Docker Compose Object Storage

**Feature**: `001-local-object-storage`  
**Target File**: `docker-compose.yml`  
**Status**: Completed & Refined  

---

## 1. Overview
Defines the containerized local object storage service using MinIO and an automated, idempotent initialization container (`minio-create-bucket`) to provision the default `knowledge-source` bucket.

---

## 2. Environment Variables Contract (`.env` / `.env.example`)

| Variable Name | Required | Default Value | Description |
|---|---|---|---|
| `MINIO_ROOT_USER` | Yes | `admin` | Administrator username for MinIO API and Web Console |
| `MINIO_ROOT_PASSWORD` | Yes | `minioadmin123` | Administrator password (minimum 8 characters) |
| `MINIO_PORT` | No | `9000` | Host port mapped to MinIO S3 API |
| `MINIO_CONSOLE_PORT` | No | `9001` | Host port mapped to MinIO Web Management Console |
| `MINIO_DEFAULT_BUCKET`| No | `knowledge-source` | Canonical bucket created on initial startup |

---

## 3. Service Definitions Specification

### 3.1 Service: `minio`
- **Image**: `minio/minio:RELEASE.2024-11-07T00-52-19Z`
- **Command**: `server /data --console-address ":9001"`
- **Ports**:
  - `"${MINIO_PORT:-9000}:9000"` (S3 API)
  - `"${MINIO_CONSOLE_PORT:-9001}:9001"` (Web Console UI)
- **Environment**:
  - `MINIO_ROOT_USER: ${MINIO_ROOT_USER:-admin}`
  - `MINIO_ROOT_PASSWORD: ${MINIO_ROOT_PASSWORD:-minioadmin123}`
- **Volumes**:
  - `minio_data:/data`
- **Healthcheck**:
  - `test: ["CMD-SHELL", "echo > /dev/tcp/127.0.0.1/9000 || exit 1"]`
  - `interval: 5s`
  - `timeout: 5s`
  - `retries: 5`
  - `start_period: 3s`
- **Restart Policy**: `unless-stopped`

### 3.2 Service: `minio-create-bucket` (Init Container)
- **Image**: `minio/mc:RELEASE.2024-11-05T11-41-28Z`
- **Depends On**:
  - `minio`: `condition: service_started`
- **Entrypoint**: `/bin/sh`
- **Command**:
  ```sh
  -c "
  echo 'Waiting for MinIO service to become ready...';
  until mc alias set local http://minio:9000 \"$$MINIO_ROOT_USER\" \"$$MINIO_ROOT_PASSWORD\"; do
    sleep 1;
  done;
  echo 'MinIO is ready. Provisioning default bucket...';
  mc mb --ignore-existing local/\"$${MINIO_DEFAULT_BUCKET:-knowledge-source}\";
  echo 'Default bucket ready.';
  exit 0;
  "
  ```
- **Environment**:
  - `MINIO_ROOT_USER: ${MINIO_ROOT_USER:-admin}`
  - `MINIO_ROOT_PASSWORD: ${MINIO_ROOT_PASSWORD:-minioadmin123}`
  - `MINIO_DEFAULT_BUCKET: ${MINIO_DEFAULT_BUCKET:-knowledge-source}`
- **Restart Policy**: `on-failure`

### 3.3 Named Volumes
```yaml
volumes:
  minio_data:
    driver: local
```
