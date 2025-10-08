import functools
import logging
import copy
from typing import (
    Any,
    Text,
    Callable,
    Tuple,
    Optional,
    List
)
from src.ai_core.models.chunks import DocumentChunk
from src.ai_core.api.schemas.chunks import UpdateChunkRequest, OperationChunkResponse
from src.ai_core.services import (
    chunk_service,
    search_service
)

logger = logging.getLogger("Controller")


class ChunkManager():
    async def get_chunks(
        self,
        document_ids: Optional[List[str]] = None,
        chunk_ids: Optional[List[str]] = None,
        offset: int = 0,
        limit: int = 10,
        filters: Optional[List[dict]] = None
    ) -> Tuple[List[dict], int]:
        
        return await chunk_service.get_chunks(
            document_ids=document_ids,
            chunk_ids=chunk_ids,
            offset=offset,
            limit=limit,
            filters=filters
        )
    
    async def add_chunks(
        self,
        chunks: List[DocumentChunk]
    ) -> OperationChunkResponse:
        err_ids = await chunk_service.add_chunks(
            chunks=chunks
        )
        if err_ids:
            success_ids = [chunk.id for chunk in chunks if chunk.id not in err_ids]
            return OperationChunkResponse(
                success_ids=success_ids,
                failed_ids=err_ids
            )
        return OperationChunkResponse(
            success_ids=[chunk.id for chunk in chunks],
            failed_ids=[]
        )
        
    async def update_metadata(
        self,
        metadata: List[dict]
    ) -> OperationChunkResponse:
        err_ids = await chunk_service.update_metadata(
            metadata=metadata
        )
        if err_ids:
            success_ids = [m["id"] for m in metadata if m["id"] not in err_ids]
            return OperationChunkResponse(
                success_ids=success_ids,
                failed_ids=err_ids
            )
        return OperationChunkResponse(
            success_ids=[m["id"] for m in metadata],
            failed_ids=[]
        )
    
    async def update_chunks(
        self,
        chunks: List[UpdateChunkRequest],
        existing_chunks: List[DocumentChunk]
    ) -> OperationChunkResponse:
        # Create map of existing chunks for easy access
        chunks_map = {chunk.id: chunk for chunk in existing_chunks}

        # Process updates
        updated_chunks= []
        for update in chunks:
            if update.id not in chunks_map:
                continue
            
            current_chunk = chunks_map[update.id]
            update_chunk = copy.deepcopy(current_chunk)
            for key, value in update.model_dump().items():
                if value is not None:
                    setattr(update_chunk, key, value)
            
            # if update_chunk.content_hash != current_chunk.content_hash:
            #     add_chunks.append(update_chunk)
            # else:
            updated_chunks.append(update_chunk)
            
        err_ids = await chunk_service.add_chunks(
            chunks=updated_chunks
        )
        if err_ids:
            success_ids = [chunk.id for chunk in chunks if chunk.id not in err_ids]
            return OperationChunkResponse(
                success_ids=success_ids,
                failed_ids=err_ids
            )
        return OperationChunkResponse(
            success_ids=[chunk.id for chunk in chunks],
            failed_ids=[]
        )
        
    async def delete_chunks(
        self,
        chunk_ids: List[str]
    ) -> OperationChunkResponse:
        err_ids = await chunk_service.delete_chunks(
            chunk_ids=chunk_ids
        )
        if err_ids:
            success_ids = [_id for _id in chunk_ids if _id not in err_ids]
            return OperationChunkResponse(
                success_ids=success_ids,
                failed_ids=err_ids
            )
        return OperationChunkResponse(
            success_ids=[_id for _id in chunk_ids],
            failed_ids=[]
        )
    
    async def search(
        self,
        app_id: str,
        query: str,
        top_k: int = 5,
        score_threshold = 0.5
    ):
        return await search_service.search(
            app_id=app_id,
            query=query,
            top_k=top_k,
            score_threshold=score_threshold
        )
