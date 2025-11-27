import logging
from typing import Optional
from pydantic import Field
from langchain_core.tools import tool

from src.ai_core.services import search_service
from src.config import SearchConfig

logger = logging.getLogger("uvicorn.error")

@tool
async def lookup_administrative_division(
    query: str = Field(
        description="Tên địa chính cần tra cứu (phường/xã, quận/huyện, tỉnh/thành phố)"
    )
) -> str:
    """Tool tra cứu thông tin địa chính sau sáp nhập theo các nghị định của Chính phủ Việt Nam."""
    
    try:
        agent_id = SearchConfig.agent_id
        if agent_id is None:
            return "Không thể kết nối đến hệ thống tìm kiếm."
        
        # Tìm kiếm với filter chỉ lấy dữ liệu địa chính
        results = await search_service.search(
            app_id="1234abcd-5678-90ef-abcd-1234567890ef",
            query=query,
            top_k=10,
            score_threshold=0.5,
            filters=[
                {"terms": {"metadata.app_ids": ["1234abcd-5678-90ef-abcd-1234567890ef"]}}
            ]
        )
        
        if not results:
            return f"Không tìm thấy thông tin địa chính cho: '{query}'. Có thể địa chính này chưa có thay đổi hoặc không có trong cơ sở dữ liệu."
        
        # Format kết quả
        response = f"🏛️ **Kết quả tra cứu địa chính cho '{query}':**\n\n"
        
        for i, result in enumerate(results[:3], 1):
            metadata = result.document_metadata if hasattr(result, 'document_metadata') else {}
            
            # Lấy thông tin địa chính cũ và mới
            old_info = metadata.get('old_ward_name', {})
            new_info = metadata.get('new_ward_name', {})
            
            if old_info and new_info:
                response += f"**{i}. {metadata.get('old_ward_name', 'N/A')}**\n"
                response += f"**Trước sáp nhập:**\n"
                response += f"   • Phường/Xã: {metadata.get('old_ward_name', 'N/A')} (Mã: {metadata.get('old_ward_code', 'N/A')})\n"
                response += f"   • Quận/Huyện: {metadata.get('old_district_name', 'N/A')} (Mã: {metadata.get('old_district_code', 'N/A')})\n"
                response += f"   • Tỉnh/TP: {metadata.get('old_province_name', 'N/A')} (Mã: {metadata.get('old_province_code', 'N/A')})\n\n"
                
                response += f"**Sau sáp nhập:**\n"
                response += f"   • Phường/Xã: {metadata.get('new_ward_name', 'N/A')} (Mã: {metadata.get('new_ward_code', 'N/A')})\n"
                response += f"   • Tỉnh/TP: {metadata.get('new_province_name', 'N/A')} (Mã: {metadata.get('new_province_code', 'N/A')})\n\n"
                
                response += "\n" + "─" * 50 + "\n\n"
            else:
                # Fallback nếu cấu trúc dữ liệu khác
                response += f"**{i}. {result.title if hasattr(result, 'title') else 'Kết quả'}**\n"
                response += f"{result.content if hasattr(result, 'content') else 'Không có nội dung chi tiết'}\n\n"
        
        response += "💡 **Lưu ý:** Thông tin trên dựa trên các nghị định sáp nhập hành chính của Chính phủ. Để biết thêm chi tiết, vui lòng tham khảo các văn bản pháp lý chính thức."
        
        return response
        
    except Exception as e:
        logger.error(f"Lỗi tra cứu địa chính: {str(e)}")
        return f"Đã xảy ra lỗi khi tra cứu thông tin địa chính: {str(e)}"

# if __name__ == "__main__":
#     import asyncio
    
#     async def test_tool():
#         query = "trước tôi sống ở Thọ Xuân Đan Phượng thì bây giờ ở đâu?"
#         result = await lookup_administrative_division.ainvoke({"query": query})
#         print(result)
    
#     asyncio.run(test_tool())
