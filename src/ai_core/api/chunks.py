import time
import uuid
import traceback
from fastapi import FastAPI, Query, HTTPException
from typing import List, Optional
from fastapi import APIRouter, Path, Body
from src.ai_core.api.schemas.chunks import (
    GetChunkResponse,
    OperationChunkResponse,
    CreateChunkRequest,
    UpdateChunkRequest,
    SearchRequest,
)
from src.ai_core.api.chunk_manager import ChunkManager
from src.ai_core.models.chunks import SearchResult


chunk_manager = ChunkManager()

router = APIRouter()

@router.post("/search", response_model=List[SearchResult])
async def search(
    app_id: str = Query(None, description="StringUUID of the agent"),
    search_request: SearchRequest = Body(
        ...,
        description= "Request body to search chunks based on query, top_k, score_threshold and env"
    ),
):
    """
    Tìm kiếm chunks theo query, top_k, score_threshold và env.
    """
    try:
        start_time = time.time()
        chunks = await chunk_manager.search(
            app_id=app_id,
            **search_request.model_dump()
        )
        execution_time = time.time() - start_time
        print(f"Execution get_chunks time: {execution_time}")
        return chunks
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@router.get("/chunks", response_model=GetChunkResponse)
async def get_chunks(
    chunk_ids: Optional[List[str]] = Query(None, description="List of chunk IDs, chunk ID is a string UUID"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    limit: int = Query(10, ge=1, description="Number of items to return"),
):
    """
    Lấy danh sách các chunks theo chunk_ids, offset và limit.
    """
    try:
        start_time = time.time()
        chunks, total = await chunk_manager.get_chunks(
            chunk_ids=chunk_ids,
            offset=offset,
            limit=limit,
        )
        execution_time = time.time() - start_time
        print(f"Execution get_chunks time: {execution_time}")
        return GetChunkResponse(chunks=chunks, total=total)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e: 
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@router.post("/chunks", response_model=OperationChunkResponse)
async def add_chunks(
    chunks: List[CreateChunkRequest] = Body(
        ...,
        description="List of chunks to create.Maximum number of chunks per request is 20",
    ),
):
    """
    Tạo/Embedding 1 hoặc nhiều chunks theo tenant id.Lưu ý: Đầu vào được phép tối đa 20 phần tử.
    """
    try:
        if len(chunks) > 20:
            raise HTTPException(
                status_code=400, detail="Maximum number of chunks per request is 20"
            )

        print(f"\n=== ADD CHUNKS REQUEST ===")
        print(f"Number of chunks: {len(chunks)}")
        
        start_time = time.time()
        
        # Convert to DB models
        db_chunks = [c.to_db_model(embedding_status=True) for c in chunks]
        
        res = await chunk_manager.add_chunks(chunks=db_chunks)
        
        execution_time = time.time() - start_time
        print(f"\nExecution create_chunks time: {execution_time}")
        print(f"Result - Success: {len(res.success_ids)}, Failed: {len(res.failed_ids)}")
        if res.failed_ids:
            print(f"Failed IDs: {res.failed_ids}")
        print(f"=== END ADD CHUNKS REQUEST ===\n")

        return res

    except ValueError as e:
        print(f"\n=== ValueError in add_chunks ===")
        print(f"Error: {str(e)}")
        print(traceback.format_exc())
        print(f"=== END ValueError ===\n")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        print(f"\n=== Exception in add_chunks ===")
        print(f"Error type: {type(e).__name__}")
        print(f"Error message: {str(e)}")
        print(f"Number of chunks in request: {len(chunks)}")
        for idx, chunk in enumerate(chunks):
            print(f"\nChunk {idx + 1} data:")
            print(f"  {chunk.model_dump()}")
        print(traceback.format_exc())
        print(f"=== END Exception ===\n")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.put("/chunks", response_model=OperationChunkResponse)
async def update_chunks(
    chunks: List[UpdateChunkRequest] = Body(
        ...,
        description="List of chunks to create.Maximum number of chunks per request is 20",
    ),
):
    """
    Cập nhật 1 hoặc nhiều chunk của tenant id.Lưu ý: Đầu vào được phép tối đa 20 phần tử
    """
    try:
        if len(chunks) > 20:
            raise HTTPException(
                status_code=400, detail="Maximum number of chunks per request is 20"
            )
        start_time = time.time()

        # First fetch existing chunks
        chunk_ids = [update.id for update in chunks]
        existing_chunks, _ = await chunk_manager.get_chunks(
            chunk_ids=chunk_ids, offset=0, limit=len(chunk_ids)
        )

        if not existing_chunks:
            raise HTTPException(
                status_code=404, detail="No chunks found for the provided IDs"
            )
        
        # Perform update in database
        res = await chunk_manager.update_chunks(chunks, existing_chunks)

        execution_time = time.time() - start_time
        print(f"Execution update_chunks time: {execution_time}")

        return res

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
    
@router.delete("/chunks")
async def delete_chunks(
    chunk_ids: Optional[List[str]] = Body(..., description="List of chunk IDs to delete"),
):
    """
    Xóa một hoặc nhiều chunk(tài liệu) của tenant id
    Lưu ý: Đầu vào: 
    - chunk_ids: tối đa 20 phần tử
    """
    try:
        if len(chunk_ids) > 20:
            raise HTTPException(
                status_code=400, detail="Maximum number of chunk_ids per request is 20"
            )
        start_time = time.time()
        existing_chunks, _ = await chunk_manager.get_chunks(
            chunk_ids=chunk_ids, offset=0, limit=10000
        )

        if not existing_chunks: 
            raise HTTPException(
                status_code=404, detail="No chunks found for the provided IDs"
            )
        ids = [chunk["id"] for chunk in existing_chunks]
        res = await chunk_manager.delete_chunks(ids)
        execution_time = time.time() - start_time
        print(f"Execution delete_chunks time: {execution_time}")
        return res
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e: 
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
