"""Configuration settings for knowledge platform services."""

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
    minio_host: str = Field(
        default="localhost",
        alias="MINIO_HOST",
        description="Hostname or container network alias for MinIO service",
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
        return f"http://{self.minio_host}:{self.minio_port}"

    @property
    def console_url(self) -> str:
        """Construct the local web console URL."""
        return f"http://{self.minio_host}:{self.minio_console_port}"
