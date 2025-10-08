import re
import logging
from typing import Union, Optional
from pydantic import Field
from langchain_core.tools import tool

from src.ai_core.services import search_service, chunk_service
from src.ai_core.models.chunks import SearchResult
from src.config import SearchConfig

logger = logging.getLogger("uvicorn.error")

@tool
async def search(
    background_search_queries: list[str] = Field(
        default_factory=list,
        description="Danh sách các truy vấn tìm kiếm nền tảng."
    ),
    in_depth_search_queries: Optional[list[str]] = Field(
        default_factory=list,
        description="Danh sách cách truy vấn tìm kiếm chuyên sâu."
    )
) -> list[dict]:
    """Truy xuất thông tin từ cơ sở tri thức sử dụng các truy vấn tìm kiếm."""
    search_queries = (background_search_queries or []) + (in_depth_search_queries or [])
    chunks: list[dict] = await asearch(
        search_queries,
        max_chars=SearchConfig.max_chars
    )

    local_index = 0
    for i in range(len(chunks)):
        if isinstance(chunks[i], dict):
            chunks[i] = {
                "local_index": local_index,
                **{k: v for k, v in chunks[i].items() if k != "ids"}
            }
            local_index += 1
    return chunks

async def asearch(
    queries: Union[str, list[str]],
    max_chars: int = SearchConfig.max_chars,
    top_docs: int = SearchConfig.top_docs,
    score_threshold: float = SearchConfig.score_threshold,
    ignore_chunk_ids: Optional[set[str]] = set(),
) -> list[dict]:
    """Search with per-query budget allocation - no overflow processing."""
    agent_id = SearchConfig.agent_id
    if agent_id is None:
        return []
    
    if isinstance(queries, str):
        queries = [queries]

    # Process each query independently with strict budget
    results: list[dict] = []

    max_chars = max_chars // len(queries)
    total_chars_used = 0
    total_chunks = 0
    for query in queries:
        try:
            documents: list[dict] = []
            chars_used: int = 0

            search_results: list[dict] = await _search_with_retry(
                agent_id=agent_id,
                query=query,
                top_docs=top_docs,
                score_threshold=score_threshold
            )
            logger.info(f"Found {len(search_results)} chunks")
            for result in search_results:
                if result.get("document_metadata", {}).get("category") == "VBPL":
                    result: dict = await _expand_search_result(result, agent_id)

                content_length = len(str(result))
                if (
                    chars_used + content_length <= max_chars and 
                    not any(cid in ignore_chunk_ids for cid in result.get("ids", []))
                ):
                    documents.append({k: v for k, v in result.items() if k != "ids"})
                    ignore_chunk_ids.update(set(result.get("ids")))
                    chars_used += content_length
            
            results.extend(documents)
            total_chars_used += chars_used
            total_chunks += len(documents)
            
        except Exception as e:
            logger.error(f"Search failed for query '{query}': {str(e)}")
            continue
            
    logger.info(f"Search complete. Total queries: {len(queries)}. "
                f"Total chars: {total_chars_used}")
    
    return results

async def _expand_search_result(
    result: dict,
    agent_id: str
) -> dict:
    title = result.get("title")
    if not (
        isinstance(title, str) and
        re.search(r"(điều [0-9]+)", title, flags=re.IGNORECASE)
    ):
        return result

    # Filter chunks by title and document number
    filters = [
        {"terms": {"metadata.app_ids": [agent_id]}},
        {"match": {"metadata.enabled": True}},
        {"match": {"metadata.document_metadata.category": "VBPL"}},
        {"match_phrase": {"metadata.title": title}}
    ]
    document_number = result.get("document_metadata", {}).get("number")
    if document_number:
        filters.append({"match": {"metadata.document_metadata.number": document_number}})

    chunks, _ = await chunk_service.get_chunks(
        limit=20,
        filters=filters
    )

    # Sort chunks by chunk index
    chunks: list[dict] = sorted(chunks, key=lambda x: x.get("chunk_index", 0))

    # Merge chunks
    ids: list[str] = []
    contents: list[str] = []
    modify_chunk_ids: list[str] = []
    modify_types: list[str] = []
    for chunk in chunks:
        if modified_by := chunk.get("document_metadata", {}).get("modified_by"):
            for item in modified_by:
                chunk_id = item.get("chunk_id")
                if chunk_id is not None and chunk_id not in modify_chunk_ids:
                    modify_chunk_ids.append(chunk_id)

                modify_type = item.get("modification_type")
                if modify_type is not None and modify_type not in modify_types:
                    modify_types.append(modify_type)

        ids.append(chunk.get("id"))
        contents.append(_clean_text(chunk.get("content", "")))

    merged_chunk = dict(
        ids=ids,
        title=title,
        content="\n".join(contents),
        document_metadata=dict(
            number=result.get("document_metadata", {}).get("number"),
            effective_date=result.get("document_metadata", {}).get("effective_date"),
            expiration_date="N/A (In effect)" if not modify_chunk_ids else "Một số nội dung đã/sẽ hết hạn do bị " + ", ".join(modify_types) + " bởi " + ("một" if len(modify_chunk_ids) == 1 else "một số") + " nội dung khác. Chi tiết ở phần modified_by bên dưới."
        )
    )

    # Add modifications if available
    if modify_chunk_ids:
        modify_chunks, _ = await chunk_service.get_chunks(
            limit=len(modify_chunk_ids),
            filters=[
                {"terms": {"metadata.app_ids": [agent_id]}},
                {"match": {"metadata.enabled": True}},
                {"terms": {"metadata.id": modify_chunk_ids}}
            ]
        )

        modify_contents: dict[str, dict] = {}
        for chunk in modify_chunks:
            document_metadata = chunk.get("document_metadata") or {}
            document_number = document_metadata.get("number") or "nan"
            if document_number not in modify_contents:
                modify_contents[document_number] = dict(
                    title=chunk.get("title", ""),
                    contents=[],
                    metadata=dict(
                        document_number=document_number,
                        effective_date=f'Ngày {document_metadata.get("effective_date")}',
                        expiration_date=f'Ngày {document_metadata.get("expiration_date")}' if document_metadata.get("expiration_date") else "N/A (In effect)"

                    )
                )
            content = chunk.get("content")
            if (
                isinstance(content, str) and
                content.startswith("Bãi bỏ ") and
                len(content_parts:=content.split("\n")) == 2
            ):
                # Dedup content
                content = content_parts[0]

            modify_contents[document_number]["contents"].append(content)

        merged_chunk["modified_by"] = list(modify_contents.values())
    
    return merged_chunk

async def _search_with_retry(
    agent_id: str,
    query: str,
    top_docs: int = SearchConfig.top_docs,
    score_threshold: float = SearchConfig.score_threshold,
    max_retries: int = SearchConfig.max_retries
) -> list[dict]:
    """Execute search with retry mechanism."""
    for attempt in range(max_retries + 1):
        try:
            # 1. Search ban đầu
            results: list[SearchResult] = await search_service.search(
                app_id=agent_id,
                query=query,
                top_k=top_docs,
                score_threshold=score_threshold
            )
            chunks = [_create_chunk_from_result(result) for result in results]

            # 2. Đếm legal chunks hiện tại
            legal_count = 0
            for chunk in chunks:
                if chunk.get("document_metadata", {}).get("category") == "VBPL":
                    legal_count += 1

            # 3. Tính số legal chunks cần thiết (ít nhất 50%)
            required_legal = int(top_docs * 0.5)
            
            # 4. Nếu thiếu legal chunks, thay thế non-legal chunks có score thấp nhất
            if legal_count < required_legal:
                missing_count = required_legal - legal_count
                
                additional_results: list[SearchResult] = await search_service.search(
                    app_id=agent_id,
                    query=query,
                    top_k=missing_count,
                    score_threshold=score_threshold,
                    filters=[{"match": {"metadata.document_metadata.category": "VBPL"}}]
                )
                
                if additional_results:
                    # Find non-legal chunks from the end (lowest scores) to remove
                    chunks_to_remove = []
                    for i in range(len(chunks) - 1, -1, -1):
                        chunk = chunks[i]
                        if chunk.get("document_metadata", {}).get("category") != "VBPL":
                            chunks_to_remove.append(i)
                            if len(chunks_to_remove) >= missing_count:
                                break
                    
                    # Remove non-legal chunks (from end to preserve order)
                    for idx in sorted(chunks_to_remove, reverse=True):
                        chunks.pop(idx)
                    
                    # Add new legal chunks to the end
                    for result in additional_results:
                        chunks.append(_create_chunk_from_result(result))

            return chunks
        except Exception as e:
            if attempt < max_retries:
                logger.warning(f"Search attempt {attempt + 1} failed: {str(e)}")
                continue
            raise

def _create_chunk_from_result(
    result: SearchResult
) -> dict:
    """Create Chunk object(s) from SearchResult. 
    If chunk has modifications, replace with chunks from modification chunk_ids."""
    metadata = result.document_metadata if isinstance(result.document_metadata, dict) else {}
    
    # Create base chunk
    document_metadata = dict(
        number=metadata.get("number"),
        category=metadata.get("category"),
        effective_date=f'Ngày {metadata.get("effective_date")}',
        expiration_date=f'Ngày {metadata.get("expiration_date")}' if metadata.get("expiration_date") else "N/A (In effect)"
    )
    if (
        (modified_by := metadata.get("modified_by")) and
        modified_by and
        modified_by[0].get("document_name")
    ):
        document_metadata["modified_by"] = metadata.get("modified_by")

    return dict(
        ids=[result.id],
        title=result.title,
        content=_clean_text(result.content),
        document_metadata=document_metadata
    )

def _clean_text(text: str) -> str:
    if isinstance(text, str):
        text = re.sub(r"\xa0+", " ", text).strip()
        text = re.sub(r"kế\s+toán\s+thiên\s+ưng", "", text, flags=re.IGNORECASE)
        text = re.sub(r"https?://[^\s]*ketoanthienung[^\s]*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s+", " ", text).strip()
        return text
    return text
