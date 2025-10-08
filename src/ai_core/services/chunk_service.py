from typing import List, Optional, Union, Tuple
from functools import wraps

from src.ai_core.models.chunks import DocumentChunk
from src.ai_core.retriever import dense_vector_store
from src.db.elasticsearch import AVAElasticsearchStore


class ChunkService:
    def __init__(self):
        self.vector_store = dense_vector_store

    async def get_chunks(
        self,
        document_ids: Optional[List[str]] = None,
        chunk_ids: Optional[List[str]] = None,
        offset: int = 0,
        limit: int = 10,
        filters: Optional[List[dict]] = None
    ) -> Tuple[List[dict], int]:
        """
        Retrieves chunks from the database based on the provided filters.
        """
        
        chunks, total = await self.vector_store.get_chunks(document_ids, chunk_ids, offset, limit, filters)

        return chunks, total
    
    async def add_chunks(
        self,
        chunks: List[DocumentChunk]
    ):
        """
        Adds new chunks to the database.
        """
        documents = [c.to_langchain_model() for c in chunks]
        return await self.vector_store.aadd_documents(documents)
    
    async def update_metadata(
        self,
        metadata: List[dict]
    ):
        """
        Updates chunks in the database.
        """
        return await self.vector_store.update_metadata(metadata)
    
    async def delete_chunks(
        self,
        chunk_ids: List[str]
    ):
        """
        Deletes chunks from the database.
        """
        return self.vector_store.delete(chunk_ids)
