"""Asynchronous Qdrant vector database manager for document chunks."""

from loguru import logger
from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models

from knowledge_platform.ingestion.models import VectorPayload


class QdrantVectorStore:
    """Manages asynchronous Qdrant collections, vector persistence, and payload filtering."""

    def __init__(
        self,
        client: AsyncQdrantClient,
        collection_name: str = "document_chunks",
        vector_size: int = 768,
    ) -> None:
        self.client = client
        self.collection_name = collection_name
        self.vector_size = vector_size

    async def ensure_collection_exists(self) -> None:
        """Create Qdrant collection and payload indexes if they do not already exist."""
        exists = await self.client.collection_exists(self.collection_name)
        if not exists:
            await self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=models.VectorParams(
                    size=self.vector_size,
                    distance=models.Distance.COSINE,
                ),
            )
            logger.info(
                "Created Qdrant collection: {name} (dim={dim}, distance=Cosine)",
                name=self.collection_name,
                dim=self.vector_size,
            )

        # Ensure payload indexes for rapid filtered retrieval and deletions
        payload_indexes = [
            ("document_id", models.PayloadSchemaType.KEYWORD),
            ("source_file_name", models.PayloadSchemaType.KEYWORD),
            ("storage_path", models.PayloadSchemaType.KEYWORD),
            ("chunk_index", models.PayloadSchemaType.INTEGER),
        ]
        for field_name, schema_type in payload_indexes:
            try:
                await self.client.create_payload_index(
                    collection_name=self.collection_name,
                    field_name=field_name,
                    field_schema=schema_type,
                )
            except Exception as e:  # noqa: BLE001
                # Index may already exist
                logger.debug(
                    "Payload index for {field} status: {err}",
                    field=field_name,
                    err=str(e),
                )

    async def recreate_collection(self) -> None:
        """Completely purge and recreate collection (used for reset_on_start)."""
        if await self.client.collection_exists(self.collection_name):
            await self.client.delete_collection(self.collection_name)
            logger.warning(
                "Deleted Qdrant collection: {name}", name=self.collection_name
            )
        await self.ensure_collection_exists()

    async def upsert_chunk_vectors(
        self,
        document_id: str,
        chunk_ids: list[str],
        vectors: list[list[float]],
        payloads: list[VectorPayload],
    ) -> None:
        """Upsert a batch of chunk vectors and associated metadata payloads."""
        if not chunk_ids:
            return

        points = [
            models.PointStruct(
                id=c_id,
                vector=vec,
                payload=payload.model_dump(by_alias=True, mode="python"),
            )
            for c_id, vec, payload in zip(chunk_ids, vectors, payloads, strict=True)
        ]

        await self.client.upsert(
            collection_name=self.collection_name,
            points=points,
        )
        logger.bind(document_id=document_id).info(
            "Upserted {count} vectors into Qdrant collection {collection}",
            count=len(points),
            collection=self.collection_name,
        )

    async def delete_vectors_by_document_id(self, document_id: str) -> None:
        """Delete all points associated with a specific document_id."""
        await self.client.delete(
            collection_name=self.collection_name,
            points_selector=models.FilterSelector(
                filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="document_id",
                            match=models.MatchValue(value=document_id),
                        )
                    ]
                )
            ),
        )
        logger.bind(document_id=document_id).info(
            "Purged vectors for document_id={doc_id} from Qdrant",
            doc_id=document_id,
        )

    async def count_vectors_by_document_id(self, document_id: str) -> int:
        """Return the count of vector points currently stored for a document."""
        result = await self.client.count(
            collection_name=self.collection_name,
            count_filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="document_id",
                        match=models.MatchValue(value=document_id),
                    )
                ]
            ),
        )
        return result.count

    async def get_points_by_document_id(self, document_id: str) -> list[models.Record]:
        """Retrieve all vector points associated with a specific document_id."""
        points, _ = await self.client.scroll(
            collection_name=self.collection_name,
            scroll_filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="document_id",
                        match=models.MatchValue(value=document_id),
                    )
                ]
            ),
            limit=1000,
            with_payload=True,
            with_vectors=True,
        )
        return points
