from typing import Dict, Optional, Any, List, Text, Iterable, Literal, Tuple
import logging
import uuid
from elasticsearch import (
    AsyncElasticsearch,
    Elasticsearch,
    ConnectionTimeout, 
    ConnectionError,
)
from langchain_elasticsearch import ElasticsearchStore, DenseVectorStrategy, BM25Strategy

from elasticsearch import Elasticsearch
from elasticsearch.helpers import BulkIndexError, bulk
from elasticsearch.helpers.vectorstore import (
    RetrievalStrategy,
)
from langchain_core.embeddings import Embeddings

from langchain_elasticsearch._utilities import (
    DistanceStrategy,
)
from src.db.es_factory import get_elasticsearch_client
from src.ai_core.retriever.custom_retriever import CustomVectorStoreRetriever
from src.ai_core.models.chunks import DocumentChunk

logger = logging.getLogger("elasticsearch_log")


class AVAElasticsearchStore(ElasticsearchStore):
    def __init__(
        self,
        index_name: str,
        *,
        embedding: Optional[Embeddings] = None,
        es_connection: Optional[Elasticsearch] = None,
        es_url: Optional[str] = None,
        es_cloud_id: Optional[str] = None,
        es_user: Optional[str] = None,
        es_api_key: Optional[str] = None,
        es_password: Optional[str] = None,
        vector_query_field: str = "vector",
        query_field: str = "text",
        distance_strategy: Optional[
            Literal[
                DistanceStrategy.COSINE,
                DistanceStrategy.DOT_PRODUCT,
                DistanceStrategy.EUCLIDEAN_DISTANCE,
                DistanceStrategy.MAX_INNER_PRODUCT,
            ]
        ] = None,
        strategy: RetrievalStrategy = DenseVectorStrategy(),
        es_params: Optional[Dict[str, Any]] = None,
    ):
        # Sử dụng ResilientElasticsearchClient thay vì kết nối trực tiếp
        if not es_connection:
            try:
                # Lấy client có khả năng tự phục hồi từ factory
                es_connection = get_elasticsearch_client().client
                logger.info(f"Sử dụng ResilientElasticsearchClient cho index {index_name}")
            except Exception as e:
                # Nếu có lỗi khi lấy client từ factory, log lỗi và sử dụng cách kết nối cũ
                logger.error(f"Không thể sử dụng ResilientElasticsearchClient: {str(e)}. Sử dụng kết nối trực tiếp.")
                
        self.params = {
            "index_name": index_name,
            "embedding": embedding,
            "es_connection": es_connection,
            "es_url": es_url,
            "es_cloud_id": es_cloud_id,
            "es_user": es_user,
            "es_api_key": es_api_key,
            "es_password": es_password,
            "vector_query_field": vector_query_field,
            "query_field": query_field,
            "distance_strategy": distance_strategy,
            "strategy": strategy,
            "es_params": es_params,
        }
        super().__init__(**self.params)
        
        self.index_name = index_name
        self._store.metadata_mappings = {
            "id": {"type": "keyword"},
            "document_id": {"type": "keyword"},
            "app_ids": {"type": "keyword"},
            "misa_id": {"type": "keyword"},
            "tenant_id": {"type": "keyword"},
        }

    def get_index_info(self) -> Dict[Text, Any]:
        info = {"index_name": self.index_name}
        if self.client.indices.exists(index=self.index_name):
            info["status"] = "exists"
            info.update(self.client.indices.get(index=self.index_name))
        else:
            info["status"] = "not found"
        return info

    async def get_chunks(
        self, document_ids, chunk_ids, offset, limit, filters=None
    ) -> Tuple[List[DocumentChunk], int]:
        query = {"query": {"bool": {"must": []}}, "from": offset, "size": limit}

        if document_ids:
            query["query"]["bool"]["must"].append(
                {"terms": {"metadata.document_id": document_ids}}
            )
        if chunk_ids:
            query["query"]["bool"]["must"].append({"terms": {"_id": chunk_ids}})
        
        # Thêm bộ lọc filters
        if filters:
            valid_query_types = [
                "match", "match_phrase", "term", "terms", "range", "exists", 
                "wildcard", "prefix", "fuzzy", "bool", "nested",
            ]
            for filter_item in filters:
                if isinstance(filter_item, dict) and filter_item:
                    # Validate filter structure - phải có ít nhất 1 key hợp lệ
                    if any(key in filter_item for key in valid_query_types):
                        query["query"]["bool"]["must"].append(filter_item)
                    else:
                        print(f"Invalid filter structure: {filter_item}")

        try:
            query["_source"] = ["metadata"]
            res = self.client.search(index=self.index_name, body=query)
            total = res["hits"]["total"]["value"]
            chunks = []
            for hit in res["hits"]["hits"]:
                source = hit["_source"]
                try:
                    chunks.append(source.get("metadata", {}))
                except Exception as e:
                    print(f"Error mapping chunk data: {e}, data: {source}")
                    continue
            return chunks, total
        except Exception as e:
            print(f"Error querying Elasticsearch: {e}")
            return [], 0
        
    def add_texts(
        self,
        texts: Iterable[str],
        metadatas: Optional[List[Dict[Any, Any]]] = None,
        ids: Optional[List[str]] = None,
        refresh_indices: bool = True,
        create_index_if_not_exists: bool = True,
        bulk_kwargs: Optional[Dict] = None,
        **kwargs: Any,
    ) -> List[str]:
        """Add documents to the Elasticsearch index.

        :param texts: List of text documents.
        :param metadata: Optional list of document metadata. Must be of same length as
            texts.
        :param vectors: Optional list of embedding vectors. Must be of same length as
            texts.
        :param ids: Optional list of ID strings. Must be of same length as texts.
        :param refresh_indices: Whether to refresh the index after deleting documents.
            Defaults to True.
        :param create_index_if_not_exists: Whether to create the index if it does not
            exist. Defaults to True.
        :param bulk_kwargs: Arguments to pass to the bulk function when indexing
            (for example chunk_size).

        :return: List of IDs of the created documents, either echoing the provided one
            or returning newly created ones.
        """
        bulk_kwargs = bulk_kwargs or {}
        ids = ids or [str(uuid.uuid4()) for _ in texts]
        requests = []

        if create_index_if_not_exists:
            self._store._create_index_if_not_exists()

        if self._store.embedding_service:
            vectors = self._store.embedding_service.embed_documents(texts)

        for i, text in enumerate(texts):
            metadata = metadatas[i] if metadatas else {}

            request: Dict[str, Any] = {
                "_op_type": "index",
                "_index": self._store.index,
                self._store.text_field: text,
                "metadata": metadata,
                "_id": ids[i],
            }

            if vectors:
                request[self._store.vector_field] = vectors[i]

            requests.append(request)

        if len(requests) > 0:
            try:
                _ , errors = bulk(
                    self.client,
                    requests,
                    stats_only=False,
                    refresh=refresh_indices,
                    **bulk_kwargs,
                )
                if errors:
                    err_ids = [e["index"]["_id"] for e in errors]
                    logger.error(f"Errors adding texts: {errors}")
                    return err_ids
                return []
            except BulkIndexError as e:
                logger.error(f"Error adding texts: {e}")
                firstError = e.errors[0].get("index", {}).get("error", {})
                logger.error(f"First error reason: {firstError.get('reason')}")
                raise e

        else:
            logger.debug("No texts to add to index")
            return []
    
    async def update_metadata(self, chunks: List[dict])-> List[str]:
        """
        Update chunks in bulk
        """
        actions = []
        for chunk in chunks:
            metadata = chunk.get("metadata", {})
            updated_chunk = {}
            for key, value in metadata.items():
                if value is not None:
                    updated_chunk[key] = value
            actions.append(
                {
                    "_op_type": "update",
                    "_index": self.index_name,
                    "_id": chunk["id"],
                    "doc": {
                        "metadata": updated_chunk
                    },
                }
            )
            
        try:
            _ , errors = bulk(
                self.client,
                actions,
                stats_only=False,
                refresh=True,
            )
            if errors:
                err_ids = [e["update"]["_id"] for e in errors]
                logger.error(f"Errors adding texts: {errors}")
                return err_ids
            return []
        except BulkIndexError as e:
            logger.error(f"Error adding texts: {e}")
            raise e

    def delete(  # type: ignore[no-untyped-def]
        self,
        ids: Optional[List[str]] = None,
        refresh_indices: Optional[bool] = True,
        **kwargs: Any,
    ) -> List[str]:
        """Delete documents from the Elasticsearch index.

        :param ids: List of IDs of documents to delete.
        :param refresh_indices: Whether to refresh the index after deleting documents.
            Defaults to True.

        :return: True if deletion was successful.
        """
        if ids is None:
            raise ValueError("please specify some IDs")

        try:
            body = [
                {"_op_type": "delete", "_index": self._store.index, "_id": _id}
                for _id in ids
            ]
            _ , errors = bulk(
                self.client,
                body,
                refresh=refresh_indices,
                ignore_status=404
            )
            if errors:
                err_ids = [e["delete"]["_id"] for e in errors]
                logger.error(f"Errors deleting texts: {errors}")
                return err_ids
            return []

        except BulkIndexError as e:
            logger.error(f"Error deleting texts: {e}")
            firstError = e.errors[0].get("index", {}).get("error", {})
            logger.error(f"First error reason: {firstError.get('reason')}")
            raise e
    
    def as_retriever(self, **kwargs: Any) -> CustomVectorStoreRetriever:
        tags = kwargs.pop("tags", None) or [] + self._get_retriever_tags()
        return CustomVectorStoreRetriever(vectorstore=self, tags=tags, **kwargs)
