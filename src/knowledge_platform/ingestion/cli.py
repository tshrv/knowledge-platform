"""Command-line interface entrypoint for triggering the ingestion pipeline."""

import argparse
import asyncio
import sys
from typing import Any

from loguru import logger
from motor.motor_asyncio import AsyncIOMotorClient
from qdrant_client import AsyncQdrantClient

from knowledge_platform.config import IngestionSettings, StorageSettings
from knowledge_platform.ingestion.db import MongoRepository
from knowledge_platform.ingestion.embeddings import VertexAIEmbeddingClient
from knowledge_platform.ingestion.models import ExecutionStatus
from knowledge_platform.ingestion.pipeline import IngestionPipeline
from knowledge_platform.ingestion.vector_store import QdrantVectorStore
from knowledge_platform.storage.client import AsyncStorageClient


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments for the ingestion CLI."""
    parser = argparse.ArgumentParser(
        description="Ingestion Pipeline: recursively browse object storage, convert PDFs to Markdown, chunk, and index into vector store."
    )
    parser.add_argument(
        "--directory",
        "-d",
        type=str,
        default="",
        help="Directory path / prefix to scan in object storage (e.g. 'manuals/hr/')",
    )
    parser.add_argument(
        "--bucket",
        "-b",
        type=str,
        default=None,
        help="Target object storage bucket name (default: configured MINIO_DEFAULT_BUCKET)",
    )
    parser.add_argument(
        "--reset-on-start",
        action="store_true",
        help="Purge all vector embeddings and MongoDB document records before ingestion",
    )
    return parser.parse_args()


async def main_async() -> int:
    """Async execution routine for the CLI runner."""
    args = parse_args()
    ingestion_settings = IngestionSettings()
    storage_settings = StorageSettings()

    target_bucket = args.bucket or ingestion_settings.default_bucket
    should_reset = args.reset_on_start or ingestion_settings.ingestion_reset_on_start

    logger.info(
        "Starting ingestion CLI: bucket='{bucket}', directory='{dir}', reset_on_start={reset}",
        bucket=target_bucket,
        dir=args.directory,
        reset=should_reset,
    )

    mongo_client: AsyncIOMotorClient[dict[str, Any]] = AsyncIOMotorClient(
        ingestion_settings.mongo_uri
    )
    qdrant_client = AsyncQdrantClient(
        url=ingestion_settings.qdrant_url, check_compatibility=False
    )

    try:
        async with AsyncStorageClient(settings=storage_settings) as storage_client:
            mongo_repo = MongoRepository(
                client=mongo_client,
                database_name=ingestion_settings.mongo_database,
            )
            vector_store = QdrantVectorStore(
                client=qdrant_client,
                collection_name=ingestion_settings.qdrant_collection_name,
                vector_size=768,
            )
            embedding_client = VertexAIEmbeddingClient(
                api_key=ingestion_settings.vertex_api_key,
                model_name=ingestion_settings.vertex_embedding_model,
                dimension=768,
                batch_size=ingestion_settings.vertex_batch_size,
                max_retries=ingestion_settings.vertex_max_retries,
                retry_base_delay=ingestion_settings.vertex_retry_base_delay,
            )

            pipeline = IngestionPipeline(
                storage_client=storage_client,
                mongo_repo=mongo_repo,
                vector_store=vector_store,
                embedding_client=embedding_client,
                settings=ingestion_settings,
            )

            execution = await pipeline.run(
                directory_path=args.directory,
                bucket=target_bucket,
                reset_on_start=should_reset,
            )

            logger.info("=== Ingestion Summary ===")
            logger.info("Execution ID:      {id}", id=execution.execution_id)
            logger.info("Final Status:      {status}", status=execution.status)
            logger.info("Total Discovered:  {count}", count=execution.discovered_count)
            logger.info("Created:           {count}", count=execution.created_count)
            logger.info("Updated:           {count}", count=execution.updated_count)
            logger.info("Deleted:           {count}", count=execution.deleted_count)
            logger.info("Unchanged:         {count}", count=execution.unchanged_count)
            logger.info("Failed:            {count}", count=execution.failed_count)

            if execution.status == ExecutionStatus.FAILED:
                return 1
            return 0

    except Exception as e:  # noqa: BLE001
        logger.exception("Fatal pipeline execution failure: {err}", err=str(e))
        return 1
    finally:
        mongo_client.close()
        await qdrant_client.close()


def main() -> None:
    """Synchronous entry point for module execution."""
    exit_code = asyncio.run(main_async())
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
