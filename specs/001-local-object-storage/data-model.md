# Data Model: Local Object Storage

**Feature**: `001-local-object-storage`  
**Date**: 2026-09-21  
**Status**: Completed & Refined  

---

## 1. Conceptual Model

The local object storage domain consists of three core logical entities:
1. **StorageBucket**: An isolated storage container within the object store.
2. **StoredDocument**: A discrete file or artifact residing inside a bucket.
3. **StorageSettings**: Authentication and network configuration governing access to the storage service and web console.

```
+---------------------------------------+
|            StorageSettings            |
|---------------------------------------|
| minio_root_user: str                  |
| minio_root_password: str              |
| minio_port: int                       |
| minio_console_port: int               |
| minio_default_bucket: str             |
+-------------------+-------------------+
                    |
                    | authenticates
                    v
+---------------------------------------+
|             StorageBucket             |
|---------------------------------------|
| name: str ("knowledge-source")        |
| created_at: datetime                  |
+-------------------+-------------------+
                    |
                    | contains 0..*
                    v
+---------------------------------------+
|            StoredDocument             |
|---------------------------------------|
| key: str                              |
| bucket: str                           |
| size_bytes: int                       |
| content_type: str                     |
| etag: str                             |
| last_modified: datetime               |
+---------------------------------------+
```

---

## 2. Entities & Schema Specifications

### 2.1 StorageBucket
Represents an S3-compatible bucket. In this feature, the system automatically initializes the default bucket `knowledge-source`.

| Field | Type | Required | Description | Validation Rules |
|---|---|---|---|---|
| `name` | `str` | Yes | Canonical identifier of the bucket | DNS-compliant: lowercase alphanumeric and hyphens; length 3–63 chars (`^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$`) |
| `created_at` | `datetime` | Yes | Timestamp of bucket creation in UTC | ISO 8601 format |

### 2.2 StoredDocument
Represents a source file uploaded by a user via the MinIO Web Console or retrieved programmatically.

| Field | Type | Required | Description | Validation Rules |
|---|---|---|---|---|
| `key` | `str` | Yes | Unique object path/identifier within bucket | Non-empty; max 1024 characters; must not contain consecutive slashes |
| `bucket` | `str` | Yes | Name of parent bucket | Must match an existing bucket (`knowledge-source`) |
| `size_bytes` | `int` | Yes | Content length in bytes | `size_bytes >= 0`; max single file upload limit: 5GB |
| `content_type` | `str` | Yes | MIME type of document | Valid MIME format (`application/pdf`, `text/plain`, `text/markdown`, etc.) |
| `etag` | `str` | Yes | Entity tag / MD5 checksum representation | Non-empty hexadecimal or quoted hash string |
| `last_modified` | `datetime` | Yes | Last modification timestamp in UTC | ISO 8601 format |

### 2.3 StorageSettings (Pydantic Configuration)
Pydantic model representing environment configuration for the storage service, auto-loading from `.env`.

```python
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class StorageSettings(BaseSettings):
    """Configuration settings for local MinIO object storage."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    minio_root_user: str = Field(
        default="admin",
        min_length=3,
        alias="MINIO_ROOT_USER",
        description="Root administrative username for MinIO",
    )
    minio_root_password: str = Field(
        default="minioadmin123",
        min_length=8,
        alias="MINIO_ROOT_PASSWORD",
        description="Root administrative password for MinIO",
    )
    minio_port: int = Field(
        default=9000,
        ge=1024,
        le=65535,
        alias="MINIO_PORT",
        description="Port for S3 API endpoint",
    )
    minio_console_port: int = Field(
        default=9001,
        ge=1024,
        le=65535,
        alias="MINIO_CONSOLE_PORT",
        description="Port for MinIO Web Console",
    )
    minio_default_bucket: str = Field(
        default="knowledge-source",
        pattern=r"^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$",
        alias="MINIO_DEFAULT_BUCKET",
        description="Canonical default bucket for source documents",
    )

    @property
    def endpoint_url(self) -> str:
        """Construct the local S3 endpoint URL."""
        return f"http://localhost:{self.minio_port}"

    @property
    def console_url(self) -> str:
        """Construct the local web console URL."""
        return f"http://localhost:{self.minio_console_port}"
```

---

## 3. Lifecycle & State Transitions

### Bucket Lifecycle:
```
[Environment Start] ──> Check if bucket exists
                           │
             ┌─────────────┴─────────────┐
             ▼                           ▼
        [Exists]                   [Not Found]
             │                           │
             │                     Create bucket (mc mb)
             │                           │
             └─────────────┬─────────────┘
                           ▼
                 [Bucket Active & Ready]
```

### Stored Document Lifecycle:
```
[User Drag-and-Drop in Web UI]
               │
               ▼
   [Validation in MinIO Console]
               │
               ▼
[Persisted to Named Volume (`minio_data`)]
               │
               ▼
   [Available for S3 Retrieval]
```
