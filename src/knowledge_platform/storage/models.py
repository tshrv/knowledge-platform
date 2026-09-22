"""Data models for object storage entities."""

from datetime import datetime

from pydantic import BaseModel, Field


class DocumentMetadata(BaseModel):
    """Metadata describing an object in a storage bucket."""

    key: str = Field(
        ...,
        min_length=1,
        max_length=1024,
        description="Object key or filename",
    )
    bucket: str = Field(..., description="Parent bucket name")
    size_bytes: int = Field(..., ge=0, description="Size of document in bytes")
    content_type: str = Field(..., description="Detected MIME content type of document")
    etag: str = Field(..., description="ETag / MD5 content checksum")
    last_modified: datetime = Field(
        ..., description="Last modification timestamp in UTC"
    )


class BucketStatus(BaseModel):
    """Status report for a verified storage bucket."""

    name: str = Field(..., description="Bucket name")
    exists: bool = Field(..., description="Whether the bucket currently exists")
    total_objects: int = Field(
        default=0, ge=0, description="Number of objects present in bucket"
    )
