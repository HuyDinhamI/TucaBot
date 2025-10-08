"""
Factory cho Elasticsearch client.
"""

import logging
from typing import Dict, Any, Optional

from src.db.es_client import ResilientElasticsearchClient
from src.settings import settings

logger = logging.getLogger("elasticsearch_log")

# Singleton instance
_es_client_instance = None

def get_elasticsearch_client() -> ResilientElasticsearchClient:
    """
    Trả về singleton instance của ResilientElasticsearchClient.
    
    Returns:
        ResilientElasticsearchClient: Instance duy nhất của client
    """
    global _es_client_instance
    
    if _es_client_instance is None:
        es_config = settings.SEARCH_CONF.get("vector_storage", {})
        
        # Tạo client với các tham số từ cấu hình
        url = es_config.get("url")
        connection_params = es_config.get("connection_params", {})
        
        _es_client_instance = ResilientElasticsearchClient(
            url=url,
            timeout=connection_params.get("timeout", 30),
            retry_on_timeout=connection_params.get("retry_on_timeout", True),
            max_retries=connection_params.get("max_retries", 3),
            sniff_on_start=connection_params.get("sniff_on_start", True),
            sniff_on_connection_fail=connection_params.get("sniff_on_connection_fail", True),
        )
        
        logger.info(f"Đã khởi tạo Elasticsearch client với URL: {url}")
        
    return _es_client_instance
