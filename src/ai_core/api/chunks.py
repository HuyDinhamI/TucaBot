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
    ChunksStatusResponse,
    GetStatusRequest,
    UpdateStatusRequest,
    Status,
    SearchRequest,
    VBPLStatusResponse
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
    Tìm kiếm chunks theo query, top_k, scsearchore_threshold và env.
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
    document_ids: Optional[List[str]] = Query(None, description="List of document IDs, document ID is a string UUID"),
    chunk_ids: Optional[List[str]] = Query(None, description="List of chunk IDs, chunk ID is a string UUID"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    limit: int = Query(10, ge=1, description="Number of items to return"),
):
    """
    Lấy danh sách các chunks theo document_ids, chunk_ids, offset và limit.
    """
    try:
        start_time = time.time()
        chunks, total = await chunk_manager.get_chunks(
            document_ids=document_ids,
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
    
@router.post("/chunks/status", response_model=List[ChunksStatusResponse])
async def get_chunks_status(
    status_request: GetStatusRequest = Body(
        ...,
        description= "Request body to get status of chunks based on document_ids and chunk_ids"
    ),
):
    """
    Lấy trạng thái embedding của chunks theo list document id hoặc list chunk id
    """
    try:
        start_time = time.time()
        chunks, _ = await chunk_manager.get_chunks(
            document_ids=status_request.document_ids,
            # chunk_ids=status_request.chunk_ids,
            limit=10000
        )
        chunks_status = []
        for chunk in chunks:
            chunks_status.append(ChunksStatusResponse(
                chunk_id=chunk["id"],
                document_id=chunk["document_id"],
                embedding_status=chunk["embedding_status"]
            ))
        execution_time = time.time() - start_time
        print(f"Execution get_chunks time: {execution_time}")
        return chunks_status
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("/chunks", response_model=OperationChunkResponse)
async def add_chunks(
    chunks: List[CreateChunkRequest] = Body(
        ...,
        description="List of chunks to create. Maximum number of chunks per request is 20",
    ),
):
    """
    Tạo/Embedding 1 hoặc nhiều chunks theo tenant id. Lưu ý: Đầu vào được phép tối đa 20 phần tử.
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
        
        # Log thông tin chunks trước khi add
        for idx, chunk in enumerate(db_chunks):
            print(f"\nChunk {idx + 1}:")
            print(f"  ID: {chunk.id}")
            print(f"  Title: {chunk.title}")
            print(f"  Content length: {len(chunk.content)}")
            print(f"  Document ID: {chunk.document_id}")
            print(f"  App IDs: {chunk.app_ids}")
            print(f"  Chunk index: {chunk.chunk_index}")
            print(f"  Char count: {chunk.char_count} (type: {type(chunk.char_count).__name__})")
            print(f"  Content hash: {chunk.content_hash}")
        
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
        description="List of chunks to create. Maximum number of chunks per request is 20",
    ),
):
    """
    Cập nhật 1 hoặc nhiều chunk của tenant id. Lưu ý: Đầu vào được phép tối đa 20 phần tử
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
    document_ids: Optional[List[str]] = Body(..., description="List of document IDs to delete"),
    chunk_ids: Optional[List[str]] = Body(..., description="List of chunk IDs to delete"),
):
    """
    Xóa một hoặc nhiều chunk(tài liệu) của tenant id
    Lưu ý: Đầu vào:
    - document_ids: tối đa 20 phần tử
    - chunk_ids: tối đa 20 phần tử
    """
    try:
        if len(chunk_ids) > 20:
            raise HTTPException(
                status_code=400, detail="Maximum number of chunk_ids per request is 20"
            )
        if len(document_ids) > 20:
            raise HTTPException(
                status_code=400, detail="Maximum number of document_ids per request is 20"
            )
        start_time = time.time()
        existing_chunks, _ = await chunk_manager.get_chunks(
            document_ids=document_ids, chunk_ids=chunk_ids, offset=0, limit=10000
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


# publish chunk by list document_ids
@router.put("/documents/status")
async def update_document_status(
    status_update_request: UpdateStatusRequest = Body(..., description="Request containing the list of document IDs and the action (publish, unpublish, etc.) to perform on them"),
):
    """
    Cập nhật trạng thái của tài liệu.
    Chú ý giá trị của action thể hiện như sau:
    0: UNPUBLISHED - Thu hồi tài liệu đã phát hành,
    1: PUBLISHED - Phát hành tài liệu,
    2: DISABLED - Tắt trạng thái sử dụng của tài liệu,
    3: ENABLED - Bật trạng thái sử dụng tài liệu
    """
    try:
        if len(status_update_request.document_ids) > 20:
            raise HTTPException(
                status_code=400, detail="Maximum number of document_ids per request is 20"
            )
        start_time = time.time()
        existing_chunks, _ = await chunk_manager.get_chunks(
            document_ids=status_update_request.document_ids, offset=0, limit=10000
        )

        if not existing_chunks:
            raise HTTPException(
                status_code=404, detail="No chunks found for the provided IDs"
            )
        updated_metadata = []
        if status_update_request.action == Status.PUBLISHED:
            updated_metadata = [{"id": chunk["id"], "metadata": {"published": True}} for chunk in existing_chunks]
        elif status_update_request.action == Status.UNPUBLISHED:
            updated_metadata = [{"id": chunk["id"], "metadata": {"published": False}} for chunk in existing_chunks]
        elif status_update_request.action == Status.ENABLED:
            updated_metadata = [{"id": chunk["id"], "metadata": {"enabled": True}} for chunk in existing_chunks]
        elif status_update_request.action == Status.DISABLED:
            updated_metadata = [{"id": chunk["id"], "metadata": {"enabled": False}} for chunk in existing_chunks]
        else:
            raise HTTPException(
                status_code=400, detail="Action is not valid, must be one of the following: 0, 1, 2, 3"
            )
        res = await chunk_manager.update_metadata(updated_metadata)
        execution_time = time.time() - start_time
        print(f"Execution publish_chunks time: {execution_time}")
        return res
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/vbpl/status", response_model=VBPLStatusResponse)
async def get_vbpl_status(
    app_id: str = Query(..., description="Application ID"),
    number: str = Query(..., description="VBPL number (e.g., '65/2013/NĐ-CP')")
):
    """
    Kiểm tra trạng thái hiệu lực của VBPL dựa trên app_id và số hiệu.
    
    Trả về thông tin về ngày có hiệu lực và ngày hết hiệu lực của văn bản pháp luật.
    """
    try:
        start_time = time.time()
        
        result = await chunk_manager.get_vbpl_status(
            app_id=app_id,
            number=number
        )
        
        execution_time = time.time() - start_time
        print(f"Execution get_vbpl_status time: {execution_time}")
        
        return VBPLStatusResponse(
            effective_date=result["effective_date"],
            expiration_date=result["expiration_date"],
            found=result["found"],
            number=result["number"]
        )
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
