import logging
from typing import Optional
from pydantic import Field
from langchain_core.tools import tool

from src.ai_core.services import search_service
from src.ai_core.models.chunks import SearchResult
from src.services.minio_service import minio_service
from src.config import ToolsConfig

logger = logging.getLogger("uvicorn.error")

@tool
async def get_template_document(
    document_type: str = Field(
        description="Loại mẫu đơn cần lấy, ví dụ: 'khai sinh', 'ly hôn', 'đăng ký cư trú'"
    )
) -> dict:
    """
    Tìm và trả về link download file mẫu đơn gốc (chưa điền thông tin) cho người dùng.
    Người dùng có thể tự điền tay vào file này.
    """
    
    try:
        logger.info(f"Getting template document for type: {document_type}")
        
        # Tìm kiếm mẫu đơn trong database
        results: list[SearchResult] = await search_service.search(
            app_id=ToolsConfig.document_template_app_id,
            query=f"mẫu đơn {document_type}",
            top_k=3,
            score_threshold=0.3,
            filters=[
                {
                    "bool": {
                        "should": [
                            {"match_phrase": {"metadata.title": f"mẫu đơn {document_type}"}},
                            {"match_phrase": {"metadata.title": document_type}},
                            {"wildcard": {"metadata.document_metadata.file_name": "*.docx"}},
                            {"wildcard": {"metadata.document_metadata.file_name": "*.doc"}}
                        ],
                        "minimum_should_match": 1
                    }
                }
            ]
        )
        
        if not results:
            return {
                "success": False,
                "message": f"Không tìm thấy mẫu đơn {document_type}",
                "suggestion": "Vui lòng thử với tên khác hoặc liên hệ hỗ trợ"
            }
        
        # Lấy kết quả tốt nhất
        best_result = results[0]
        
        # Lấy file_path gốc (không phải placeholder)
        if hasattr(best_result, 'document_metadata') and best_result.document_metadata:
            metadata = best_result.document_metadata
            if isinstance(metadata, dict):
                file_path = metadata.get("file_path", "")
                file_name = metadata.get("file_name", "")
                
                if not file_path:
                    return {
                        "success": False,
                        "message": "Không tìm thấy đường dẫn file mẫu đơn"
                    }
                
                # Auto-detect bucket
                bucket_name = "mavap-document"
                actual_file_path = file_path
                if "/" in file_path:
                    potential_bucket = file_path.split("/")[0]
                    common_buckets = ["mavap-document"]
                    if potential_bucket in common_buckets:
                        bucket_name = potential_bucket
                        actual_file_path = "/".join(file_path.split("/")[1:])
                
                # Tạo URL download
                download_url = await minio_service.get_file_url(
                    actual_file_path,
                    bucket_name,
                    expires_hours=24
                )
                
                if download_url:
                    return {
                        "success": True,
                        "message": f"Mẫu đơn {document_type} đã sẵn sàng để tải về",
                        "document_title": best_result.title,
                        "file_name": file_name,
                        "download_url": download_url,
                        "expires_in": "24 giờ",
                        "type": "template_original",
                        "instructions": [
                            "Đây là file mẫu gốc, bạn cần tự điền thông tin",
                            "Mở file bằng Microsoft Word",
                            "Điền thông tin vào các trường trống",
                            "Link download có hiệu lực trong 24 giờ"
                        ]
                    }
                else:
                    return {
                        "success": False,
                        "message": "Không thể tạo link download"
                    }
        
        return {
            "success": False,
            "message": "File mẫu đơn không có thông tin metadata phù hợp"
        }
        
    except Exception as e:
        logger.error(f"Error in get_template_document: {e}")
        return {
            "success": False,
            "message": f"Đã có lỗi xảy ra: {str(e)}"
        }
