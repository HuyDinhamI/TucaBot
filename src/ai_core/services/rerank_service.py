import requests
from typing import List, Dict, Any
from src.ai_core.models.chunks import SearchResult
from src.settings import settings


class RerankService:
    """Service để rerank documents sử dụng LLM API"""
    
    def __init__(self):
        self.config = settings.SEARCH_CONF.get("rerank", {})
        self.url = self.config.get("url")
        self.enabled = self.config.get("enabled", False)
        self.top_k = self.config.get("top_k", 3)
        self.timeout = self.config.get("timeout", 10)
    
    def rerank(
        self, 
        query: str, 
        documents:  List[SearchResult]
    ) -> List[SearchResult]:
        """
        Rerank documents sử dụng LLM API
        
        Args:
            query: Câu truy vấn
            documents:  Danh sách documents cần rerank
            
        Returns:
            Danh sách documents đã được rerank và lọc theo top_k
        """
        if not self.enabled:
            # Nếu rerank không được bật, trả về top_k documents gốc
            return documents[:self.top_k]
        
        if not documents:
            return []
        
        if not self.url:
            print("Warning: Rerank URL not configured, returning original documents")
            return documents[: self.top_k]
        
        try:
            # Chuẩn bị passages từ documents
            passages = [doc.content for doc in documents]
            
            # Gọi API rerank
            payload = {
                "query": query,
                "passages": passages
            }
            
            headers = {
                "accept": "application/json",
                "Content-Type": "application/json"
            }
            
            response = requests.post(
                self.url,
                json=payload,
                headers=headers,
                timeout=self.timeout
            )
            
            response.raise_for_status()
            
            # Lấy scores từ response
            result = response.json()
            scores = result.get("scores", [])
            
            if len(scores) != len(documents):
                print(f"Warning: Number of scores ({len(scores)}) doesn't match number of documents ({len(documents)})")
                return documents[:self.top_k]
            
            # Gắn scores vào documents
            for doc, score in zip(documents, scores):
                doc.score = float(score)
            
            # Sắp xếp documents theo scores giảm dần
            ranked_documents = sorted(
                documents, 
                key=lambda x:  x.score, 
                reverse=True
            )
            
            # Trả về top_k documents
            return ranked_documents[:self.top_k]
            
        except requests.exceptions.Timeout:
            print(f"Error:  Rerank API timeout after {self.timeout}s")
            return documents[:self.top_k]
        except requests.exceptions.RequestException as e:
            print(f"Error calling rerank API: {e}")
            return documents[:self.top_k]
        except Exception as e:
            print(f"Unexpected error during reranking: {e}")
            return documents[:self.top_k]
    
    async def arerank(
        self, 
        query: str, 
        documents:  List[SearchResult]
    ) -> List[SearchResult]:
        """
        Async version của rerank method
        Hiện tại sử dụng sync version, có thể upgrade sau
        """
        return self.rerank(query, documents)


# Tạo instance global
rerank_service = RerankService()
