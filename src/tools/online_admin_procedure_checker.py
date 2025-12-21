import logging
import re
from typing import Optional
from pydantic import Field
from langchain_core.tools import tool
from difflib import SequenceMatcher

logger = logging.getLogger("uvicornerror")

# Path to the knowledge base file
KNOWLEDGE_BASE_PATH = "/home/misa/Code/capstone_prj/work/MAVAPBot/thu_tuc_hanh_chinh.md"

def normalize_text(text: str) -> str:
    """Chuẩn hóa text để so sánh."""
    # Remove extra whitespaces
    text = re.sub(r'\s+', ' ', text.strip())
    # Convert to lowercase
    text = text.lower()
    return text

def similarity_ratio(str1: str, str2: str) -> float:
    """Tính độ tương đồng giữa 2 chuỗi."""
    str1_norm = normalize_text(str1)
    str2_norm = normalize_text(str2)
    return SequenceMatcher(None, str1_norm, str2_norm).ratio()

def parse_procedure_info(content: str, procedure_name: str, address: str) -> str:
    """
    Parse thông tin thủ tục từ file tri thức.
    
    Returns:
        - "offline_only":  Chỉ trực tiếp
        - "both": Cả trực tuyến và trực tiếp (địa chỉ hỗ trợ)
        - "both_but_address_not_supported": Có cả 2 hình thức nhưng địa chỉ không hỗ trợ
        - "unknown": Không tìm thấy thông tin
    """
    try:
        # Split content into procedure blocks (mỗi thủ tục bắt đầu với số thứ tự)
        procedure_pattern = r'\d+\.\s+Thủ tục\s+\*\*(.*? )\*\*\s+(.*?)(?=\n\d+\.\s+Thủ tục|\Z)'
        procedures = re.findall(procedure_pattern, content, re.DOTALL)
        
        best_match = None
        best_score = 0.0
        THRESHOLD = 0.6  # Ngưỡng tương đồng 60%
        
        # Tìm thủ tục khớp nhất
        for proc_name, proc_content in procedures: 
            score = similarity_ratio(procedure_name, proc_name)
            if score > best_score and score >= THRESHOLD:
                best_score = score
                best_match = (proc_name, proc_content)
        
        if not best_match:
            logger.warning(f"Không tìm thấy thủ tục khớp với:  '{procedure_name}'")
            return "unknown"
        
        proc_name, proc_content = best_match
        logger.info(f"Tìm thấy thủ tục khớp: '{proc_name}' (score: {best_score:.2f})")
        
        # Kiểm tra hình thức thực hiện
        # Case 1: Chỉ trực tiếp
        if "chỉ có thể thực hiện bằng hình thức trực tiếp" in proc_content:
            return "offline_only"
        
        # Case 2: Cả hai hình thức
        if "có thể thực hiện bằng cả 2 hình thức trực tuyến và trực tiếp" in proc_content:
            # Parse danh sách địa chỉ hỗ trợ
            # Pattern: "- Phường/Xã .., Tỉnh/Thành phố ..."
            address_pattern = r'-\s+(Phường|Xã)\s+(.*? ),\s+(Tỉnh|Thành phố)\s+(.*?)(?:\n|$)'
            supported_addresses = re.findall(address_pattern, proc_content)
            
            if not supported_addresses:
                logger.warning(f"Không parse được danh sách địa chỉ hỗ trợ cho thủ tục '{proc_name}'")
                return "both_but_address_not_supported"
            
            # Chuẩn hóa địa chỉ người dùng
            address_norm = normalize_text(address)
            
            # Kiểm tra địa chỉ có trong danh sách không
            for ward_type, ward_name, province_type, province_name in supported_addresses:
                supported_addr = f"{ward_type} {ward_name}, {province_type} {province_name}"
                supported_addr_norm = normalize_text(supported_addr)
                
                # Check if user address contains the supported address components
                # Kiểm tra cả phường/xã và tỉnh/thành phố
                ward_full = normalize_text(f"{ward_type} {ward_name}")
                province_full = normalize_text(f"{province_type} {province_name}")
                
                if ward_full in address_norm and province_full in address_norm: 
                    logger.info(f"Địa chỉ '{address}' được hỗ trợ cả 2 hình thức")
                    return "both"
            
            logger.info(f"Địa chỉ '{address}' không nằm trong danh sách hỗ trợ trực tuyến")
            return "both_but_address_not_supported"
        
        # Không tìm thấy thông tin về hình thức
        loggerwarning(f"Không tìm thấy thông tin hình thức thực hiện cho thủ tục '{proc_name}'")
        return "unknown"
        
    except Exception as e:
        logger.error(f"Lỗi khi parse thông tin thủ tục: {str(e)}")
        return "unknown"

@tool
async def check_online_admin_procedure(
    procedure_name: str = Field(
        description="Tên thủ tục hành chính cần kiểm tra"
    ),
    address: str = Field(
        description="Địa chỉ hành chính đã được chuẩn hóa (phường/xã, quận/huyện, tỉnh/thành phố)"
    )
) -> str:
    """
    Kiểm tra hình thức thực hiện thủ tục hành chính (trực tuyến/trực tiếp/cả hai).
    Tri thức được lấy từ file thu_tuc_hanh_chinh.md
    
    Returns:
        Thông tin về hình thức thực hiện thủ tục
    """
    try:
        # Đọc file tri thức
        with open(KNOWLEDGE_BASE_PATH, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Parse và phân tích
        result = parse_procedure_info(content, procedure_name, address)
        print("*"*100)
        print(result)
        print("*"*100)
        # Format kết quả trả về
        if result == "offline_only":
            return f"📋 **Thủ tục '{procedure_name}'** chỉ có thể thực hiện bằng **hình thức trực tiếp** tại cơ quan hành chính."
        
        elif result == "both": 
            return f"🌐 **Thủ tục '{procedure_name}'** có thể thực hiện bằng **cả 2 hình thức trực tuyến và trực tiếp** tại địa chỉ **{address}**."
        
        elif result == "both_but_address_not_supported":
            return f"📋 **Thủ tục '{procedure_name}'** có hình thức trực tuyến, nhưng địa chỉ **{address}** chưa được hỗ trợ Bạn cần thực hiện theo **hình thức trực tiếp**."
        
        else:  # unknown
            return f"❓ Không tìm thấy thông tin về hình thức thực hiện cho thủ tục '{procedure_name}' Hệ thống sẽ tìm kiếm thông tin chung."
        
    except FileNotFoundError:
        logger.error(f"Không tìm thấy file tri thức: {KNOWLEDGE_BASE_PATH}")
        return "❌ Không thể truy cập file tri thức Vui lòng kiểm tra lại hệ thống."
    
    except Exception as e:
        logger.error(f"Lỗi khi kiểm tra hình thức thủ tục: {str(e)}")
        return f"❌ Đã xảy ra lỗi khi kiểm tra hình thức thủ tục:  {str(e)}"
