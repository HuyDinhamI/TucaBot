from pydantic import BaseModel, Field
from typing import Dict, List, Optional
from langchain.tools import tool
import json
import requests

from src.settings import settings

@tool
def search_google(
    queries: list[str] = Field(
        description="List of search queries to find relevant information."
    ),
    max_results: Optional[int] = Field(
        default=5,
        description="The maximum number of search results to return."
    ),
    **kwargs: dict,
) -> str:
    """
    Tìm kiếm thông tin cho một danh sách các truy vấn bằng công cụ tìm kiếm Google.
    Args:
        queries (str): Danh sách các truy vấn tìm kiếm để tìm kiếm thông tin liên quan.
        max_results (int): Số lượng tối đa kết quả tìm kiếm cho mỗi truy vấn để trả về.
    Returns:
        str: The search result, each include: title, link, summary.
    """
    res: List[Dict[str, str]] = []
    for query in queries:
        params = {
            "query": query,
            'topK': max_results,
        }
        try:
            response = requests.get(
                settings.SEARCH_CONF["google_search"].get("url"),
                params=params
            )
            response.raise_for_status()
            results = response.json()
            for result in results:
                res.append(
                    {
                        # "title": result['metadata']['title'],
                        # "url": result['metadata']['sourceURL'],
                        # "description": result['metadata']['description'] if 'description' in result['metadata'] else '',
                        # "content": result['content'][:5000],
                        "link": result['link'],
                        "title": result['title'],
                        "summary": result['snippet']
                    }
                )
        except Exception as e:
            return f"Error occurred during search GG: {e}"
    return json.dumps(res, ensure_ascii=False, indent=2)
