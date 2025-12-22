import requests
from typing import List, Optional, Union
from src.ai_core.models.chunks import SearchResult
from src.ai_core.retriever import retriever
from src.ai_core.services.rerank_service import rerank_service
from src.config import AgentConfig
from src.settings import settings

class HybridSearch:
    def __init__(self):
        self.retriever = retriever
        
    async def search(
        self,
        app_id: str,
        query: str,
        top_k: int = 3,
        score_threshold : float = None,
        filters: list[dict] = None
    ) -> List[SearchResult]:
        _filter = [
            {"terms": {"metadata.app_ids": [app_id]}},
            {"match": {"metadata.enabled": True}}
        ]
        if filters:
            _filter.extend(filters)

        if score_threshold is None:
            score_threshold = settings.SEARCH_CONF["vector_storage"]["score_threshold"]
        if top_k is None:
            top_k = settings.SEARCH_CONF["vector_storage"]["top_k"]
            
        config = {
            "configurable": {
                "search_kwargs_chunk_dense": {
                    "k": 20,
                    "score_threshold": score_threshold,
                    "filter": _filter
                },
                "search_kwargs_chunk_bm25": {
                    "k": 50,
                    "filter": _filter
                }
            }
        }
        chunks = await self.retriever.ainvoke(query, config = config)
        result_docs = []
        for chunk in chunks[:top_k]:
            try: 
                new_chunk = SearchResult(
                    id=chunk.metadata.get("id", ""),
                    title=chunk.metadata.get("title", ""),
                    content=chunk.metadata.get("content", ""),
                    score=chunk.metadata.get("score", ""),
                    app_ids=chunk.metadata.get("app_ids", []),
                    chunk_index=chunk.metadata.get("chunk_index", 0),
                    url=chunk.metadata.get("url", ""),
                    document_metadata=chunk.metadata.get("document_metadata", ""),
                )
                result_docs.append(new_chunk)
            except Exception as e:
                print(f"Error mapping chunk data: {e}, data: {chunk}")
                continue
        print("===================================")
        print(len(result_docs))
        # Áp dụng rerank nếu được bật
        reranked_docs = await rerank_service.arerank(query, result_docs)
        print("===================================")
        print(len(reranked_docs))
        return reranked_docs

    async def get_chunk_by_id(
        self,
        app_id: str,
        chunk_id: str,
    ) -> Optional[SearchResult]:
        """Tìm kiếm chunk theo ID cụ thể."""
        if not chunk_id or not chunk_id.strip():
            return None
            
        _filter = [
            {"terms": {"metadata.app_ids": ["88886666-9999-4666-aaaa-88889999ffff"]}},
            # {"match": {"metadata.enabled": True}},

        ]

        try:
            # Sử dụng Elasticsearch query trực tiếp để tìm theo ID
            from src.ai_core.retriever import dense_vector_store
            
            query = {
                "query": {
                    "bool": {
                        "must": _filter
                    }
                },
                "size": 1
            }
            
            result = dense_vector_store.client.search(
                index=dense_vector_store.index_name,
                body=query
            )
            
            if result["hits"]["hits"]:
                hit = result["hits"]["hits"][0]
                metadata = hit["_source"].get("metadata", {})
                
                return SearchResult(
                    id=metadata.get("id", ""),
                    title=metadata.get("title", ""),
                    content=metadata.get("content", ""),
                    score=1.0,  # Set score to 1.0 for exact ID match
                    app_ids=metadata.get("app_ids", []),
                    chunk_index=metadata.get("chunk_index", 0),
                    url=metadata.get("url", ""),
                    document_metadata=metadata.get("document_metadata", ""),
                )
            
            return None
            
        except Exception as e:
            print(f"Error searching chunk by ID {chunk_id}: {e}")
            return None


# # Tạo instance global để sử dụng
# search_service = HybridSearch()

if __name__ == "__main__":
    import asyncio

    async def main():
        search_service = HybridSearch()
        results = await search_service.search(app_id="88886666-9999-4666-aaaa-88889999ffff", query="đăng ký khai sinh")
        for result in results:
            print(result)

    asyncio.run(main())
