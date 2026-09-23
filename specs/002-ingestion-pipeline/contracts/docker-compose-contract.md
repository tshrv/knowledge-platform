# Infrastructure Contract: Docker Compose Services

**Feature**: `002-ingestion-pipeline`  
**Date**: 2026-09-22  
**Status**: Completed  

---

## 1. Overview

This contract specifies the containerized infrastructure additions in `docker-compose.yml` required to support vector storage (Qdrant) and metadata state tracking (MongoDB) alongside existing object storage (MinIO).

---

## 2. Service Definitions

### 2.1 Qdrant Vector Database (`qdrant`)

- **Image**: `qdrant/qdrant:v1.13.4`
- **Container Ports**:
  - `6333`: REST API & Web Management Console (`http://localhost:6333/dashboard`)
  - `6334`: gRPC API endpoint
- **Volumes**:
  - `qdrant_data:/qdrant/storage`
- **Environment Variables**:
  - `QDRANT__SERVICE__GRPC_PORT: 6334`
- **Health Check**:
  - Test: `["CMD-SHELL", "echo > /dev/tcp/127.0.0.1/6333 || exit 1"]`
  - Interval: `5s`, Timeout: `5s`, Retries: `5`, Start Period: `3s`
- **Restart Policy**: `unless-stopped`

### 2.2 MongoDB Metadata Database (`mongodb`)

- **Image**: `mongo:7.0`
- **Container Ports**:
  - `27017`: Standard MongoDB wire protocol port (`localhost:27017`)
- **Volumes**:
  - `mongo_data:/data/db`
- **Environment Variables**:
  - `MONGO_INITDB_ROOT_USERNAME: ${MONGO_ROOT_USER:-admin}`
  - `MONGO_INITDB_ROOT_PASSWORD: ${MONGO_ROOT_PASSWORD:-mongoadmin123}`
  - `MONGO_INITDB_DATABASE: ${MONGO_DATABASE:-knowledge_platform}`
- **Health Check**:
  - Test: `["CMD-SHELL", "mongosh --eval 'db.runCommand({ ping: 1 })' localhost:27017/test --quiet || exit 1"]`
  - Interval: `5s`, Timeout: `5s`, Retries: `5`, Start Period: `5s`
- **Restart Policy**: `unless-stopped`

---

## 3. Persistent Volumes

Named volumes defined in root `docker-compose.yml`:
```yaml
volumes:
  minio_data:
    driver: local
  qdrant_data:
    driver: local
  mongo_data:
    driver: local
```

---

## 4. Environment Variables Contract (`.env.example`)

```dotenv
# Object Storage (MinIO)
MINIO_ROOT_USER=admin
MINIO_ROOT_PASSWORD=minioadmin123
MINIO_HOST=localhost
MINIO_PORT=9000
MINIO_CONSOLE_PORT=9001
MINIO_DEFAULT_BUCKET=knowledge-source

# Vector Store (Qdrant)
QDRANT_HOST=localhost
QDRANT_PORT=6333
QDRANT_GRPC_PORT=6334
QDRANT_COLLECTION_NAME=document_chunks

# Metadata Database (MongoDB)
MONGO_HOST=localhost
MONGO_PORT=27017
MONGO_ROOT_USER=admin
MONGO_ROOT_PASSWORD=mongoadmin123
MONGO_DATABASE=knowledge_platform

# Vertex AI Embeddings
VERTEX_API_KEY=your_vertex_api_key_here
VERTEX_EMBEDDING_MODEL=gemini-embedding-001

# Ingestion Pipeline Settings
INGESTION_RESET_ON_START=false
```
