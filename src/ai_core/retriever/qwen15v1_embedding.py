from enum import Enum
from typing import Any, Dict, List, Optional, Text

from langchain_core.embeddings import Embeddings

import numpy as np
import logging
import time
import requests
import unicodedata

from src.settings import settings

logger = logging.getLogger("Embedding")

class Domain(Enum):
    ACCOUNTING: str = "accounting"
    GENERAL: str = "general"

class Qwen15V1Embedding(Embeddings):
    def __init__(self) -> None:
        embedding_conf = settings.SEARCH_CONF["embedding"]["qwen"]
        self.url = embedding_conf["url"]
        self.accounting_prompt = embedding_conf["accounting_prompt"]
        self.general_prompt = embedding_conf["general_prompt"]
        self.api_key = embedding_conf["api-key"]
        self.batch_size = embedding_conf["batch_size"]
        self.dim_size = embedding_conf["dim_size"]
        self.model_name = embedding_conf["model_name"]
        logger.info(f"LLMEncoder: {self.url}")

    def get_detailed_instruct(self, queries: List[Text], domain: Domain) -> List[Text]:
        if domain == Domain.ACCOUNTING:
            return [f"Instruct: {self.accounting_prompt}\nQuery: {query}" for query in queries]
        else:
            return [f"Instruct: {self.general_prompt}\nQuery: {query}" for query in queries]
    
    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        if isinstance(texts, str):
            texts = [texts]

        texts = [self.preprocess_text(text) for text in texts]

        t1 =  time.time()
        embeddings = []
        for i in range(0, len(texts), self.batch_size):
            try:
                responses = requests.post(
                    self.url,
                    headers = {
                        "Content-Type": "application/json",
                        "x-api-key": self.api_key,
                    },
                    json = {
                        "texts": texts[i:i+self.batch_size],
                    },
                    timeout = 10
                )
                responses.raise_for_status()
                result = responses.json()
                # API returns {"embeddings": [[...], [...]]}
                batch_embeddings = result.get("embeddings", [])
                embeddings.extend(batch_embeddings)
                logger.debug(f"Successfully embedded {len(texts[i:i+self.batch_size])} texts, got {len(batch_embeddings)} vectors")
            except requests.exceptions.RequestException as e:
                logger.error(f"Embedding service error: {e}")
                if hasattr(e, 'response') and hasattr(e.response, 'text'):
                    logger.error(f"Response: {e.response.text}")
                raise Exception(f"Failed to get embeddings: {str(e)}")
        
        logger.debug(f"Embedding with LLMEncoder: {time.time() - t1}")
        return embeddings
    
    def embed_query(self, text: Text) -> List[float]:
        """Call out to HuggingFaceHub's embedding endpoint for embedding query text.

        Args:
            text: The text to embed.

        Returns:
            Embeddings for the text.
        """
        text = self.get_detailed_instruct([text], Domain.GENERAL)
        response = self.embed_documents(text)[0]
        return response
    
    @staticmethod
    def preprocess_text(text: str) -> str:
        if isinstance(text, str):
            text = unicodedata.normalize("NFKC", text.lower())
        return text
