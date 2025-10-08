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

class JinnaEmbedding(Embeddings):
    def __init__(self) -> None:
        embedding_conf = settings.SEARCH_CONF["embedding"]["jinna"]
        self.url = embedding_conf["url"]
        self.api_key = embedding_conf["api-key"]
        self.batch_size = embedding_conf["batch_size"]
        self.dim_size = embedding_conf["dim_size"]
        logger.info(f"JinnaEmbedding: {self.url}")
    
    def embed_documents(self, texts: List[str], task="retrieval.passage") -> List[List[float]]:
        if isinstance(texts, str):
            texts = [texts]

        texts = [self.preprocess_text(text) for text in texts]

        t1 =  time.time()
        embeddings = []
        for i in range(0, len(texts), self.batch_size):
            responses = requests.post(
                self.url,
                headers = {
                    "Content-Type": "application/json",
                    "api-key": self.api_key
                },
                json = {
                    "texts": texts,
                    "task": task,
                    "truncate_dim": self.dim_size,
                },
                timeout = 10
            )
            embeddings.extend(responses.json())
        
        logger.debug(f"Embedding with LLMEncoder: {time.time() - t1}")
        return embeddings
    
    def embed_query(self, text: Text) -> List[float]:
        """Call out to HuggingFaceHub's embedding endpoint for embedding query text.

        Args:
            text: The text to embed.

        Returns:
            Embeddings for the text.
        """
        response = self.embed_documents(text, task="retrieval.query")[0]
        return response
    
    @staticmethod
    def preprocess_text(text: str) -> str:
        if isinstance(text, str):
            text = unicodedata.normalize("NFKC", text.lower())
        return text