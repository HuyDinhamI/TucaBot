
from langchain_elasticsearch import DenseVectorStrategy, BM25Strategy
from langchain_core.runnables import ConfigurableField
from src.db.elasticsearch import AVAElasticsearchStore
from src.ai_core.retriever.custom_retriever import CustomEnsembleRetriever
from src.ai_core.retriever.qwen15v1_embedding import Qwen15V1Embedding
from src.settings import settings

qwen_embedding = Qwen15V1Embedding()

es_config = settings.SEARCH_CONF["vector_storage"]
connection_params = {}

dense_vector_store = AVAElasticsearchStore(
    es_url=es_config["url"],
    es_user=es_config.get("user", None),
    es_password=es_config.get("password", None),
    index_name=es_config["index_name"],
    embedding=qwen_embedding,
    strategy=DenseVectorStrategy(),
    **connection_params,
)
bm25_vector_store = AVAElasticsearchStore(
    es_url=es_config["url"],
    index_name=es_config["index_name"],
    strategy=BM25Strategy(),
    **connection_params,
)
chunk_dense_retriever = dense_vector_store.as_retriever(
    search_type="similarity_score_threshold",
    search_kwargs={"score_threshold": 0.45, "k": 10}
    ).configurable_fields(
        search_kwargs=ConfigurableField(
            id="search_kwargs_chunk_dense",
            name="Search Kwargs",
            description="The search kwargs to use",
        )
    )
chunk_bm25_retriever = bm25_vector_store.as_retriever().configurable_fields(
    search_kwargs=ConfigurableField(
        id="search_kwargs_chunk_bm25",
        name="Search Kwargs",
        description="The search kwargs to use",
    )
)

retriever = CustomEnsembleRetriever(retrievers=[chunk_dense_retriever, chunk_bm25_retriever], weights=[0.7, 0.3])
