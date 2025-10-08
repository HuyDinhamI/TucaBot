"""
Elasticsearch client với khả năng tự phục hồi khi kết nối bị mất.
"""

import logging
import time
from typing import Any, Dict, Optional, Union, List, Callable
from functools import wraps

from elasticsearch import Elasticsearch, ConnectionTimeout, ConnectionError
import tenacity
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

logger = logging.getLogger("elasticsearch_log")

class ResilientElasticsearchClient:
    """
    Elasticsearch client với khả năng tự phục hồi kết nối.
    
    Client này cung cấp:
    1. Khả năng tự phục hồi khi kết nối bị mất
    2. Cơ chế thử lại tự động cho các lỗi kết nối
    3. Health check để đảm bảo kết nối còn sống trước khi sử dụng
    4. Cấu hình timeout hợp lý
    """
    
    def __init__(
        self, 
        url: Optional[str] = None,
        cloud_id: Optional[str] = None,
        api_key: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        timeout: int = 30,
        retry_on_timeout: bool = True,
        max_retries: int = 3,
        sniff_on_start: bool = True,
        sniff_on_connection_fail: bool = True,
        health_check_interval: int = 60,
        **kwargs: Any
    ):
        """
        Khởi tạo client Elasticsearch với khả năng tự phục hồi.
        
        Args:
            url: URL của Elasticsearch instance
            cloud_id: Cloud ID của Elasticsearch instance 
            api_key: API key để kết nối đến Elasticsearch
            username: Tên đăng nhập
            password: Mật khẩu
            timeout: Thời gian timeout cho mỗi request (giây)
            retry_on_timeout: Có thử lại khi timeout không
            max_retries: Số lần thử lại tối đa
            sniff_on_start: Tự động phát hiện các node khi khởi động
            sniff_on_connection_fail: Tự động phát hiện các node khi kết nối thất bại
            health_check_interval: Thời gian giữa các lần kiểm tra sức khỏe (giây)
            **kwargs: Các tham số khác cho Elasticsearch client
        """
        self.url = url
        self.cloud_id = cloud_id
        self.api_key = api_key
        self.username = username
        self.password = password
        self.timeout = timeout
        self.retry_on_timeout = retry_on_timeout
        self.max_retries = max_retries
        self.sniff_on_start = sniff_on_start
        self.sniff_on_connection_fail = sniff_on_connection_fail
        self.health_check_interval = health_check_interval
        self.extra_kwargs = kwargs
        
        self.last_health_check = 0
        self._client = None
        self.create_client()
    
    def create_client(self) -> None:
        """Tạo một Elasticsearch client mới với các tham số đã cấu hình."""
        connection_params: Dict[str, Any] = {
            "timeout": self.timeout,
            "retry_on_timeout": self.retry_on_timeout,
            "max_retries": self.max_retries,
        }
        
        # # Thêm cấu hình sniffing
        # if self.sniff_on_start:
        #     connection_params["sniff_on_start"] = True
        # if self.sniff_on_connection_fail:
        #     connection_params["sniff_on_connection_fail"] = True
            
        # Thiết lập kết nối
        if self.url:
            connection_params["hosts"] = [self.url]
        elif self.cloud_id:
            connection_params["cloud_id"] = self.cloud_id
        else:
            raise ValueError("Phải cung cấp url hoặc cloud_id.")
            
        # Thêm thông tin xác thực
        if self.api_key:
            connection_params["api_key"] = self.api_key
        elif self.username and self.password:
            connection_params["basic_auth"] = (self.username, self.password)
            
        # Thêm các tham số khác
        if self.extra_kwargs:
            connection_params.update(self.extra_kwargs)
            
        # Tạo client
        self._client = Elasticsearch(**connection_params)
        self.last_health_check = time.time()
        logger.info("Đã tạo kết nối Elasticsearch mới")
    
    def _ensure_connection(self) -> None:
        """
        Đảm bảo kết nối vẫn hoạt động, hoặc tạo lại nếu cần thiết.
        Kiểm tra sức khỏe định kỳ theo health_check_interval.
        """
        current_time = time.time()
        
        # Chỉ kiểm tra sức khỏe sau khoảng thời gian nhất định
        if current_time - self.last_health_check > self.health_check_interval:
            try:
                # Thực hiện kiểm tra đơn giản
                self._client.ping(request_timeout=5)
                self.last_health_check = current_time
                logger.debug("Health check thành công")
            except Exception as e:
                logger.warning(f"Kết nối không khả dụng, đang tạo lại: {str(e)}")
                self.create_client()
    
    @retry(
        retry=retry_if_exception_type((ConnectionTimeout, ConnectionError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True
    )
    def execute(self, method_name: str, *args: Any, **kwargs: Any) -> Any:
        """
        Thực thi một phương thức trên Elasticsearch client với khả năng tự phục hồi.
        
        Args:
            method_name: Tên phương thức cần thực thi
            *args: Các đối số vị trí cho phương thức
            **kwargs: Các đối số từ khóa cho phương thức
            
        Returns:
            Kết quả từ phương thức được gọi
        """
        self._ensure_connection()
        
        if not hasattr(self._client, method_name):
            raise AttributeError(f"Elasticsearch client không có phương thức: {method_name}")
            
        method = getattr(self._client, method_name)
        
        try:
            result = method(*args, **kwargs)
            return result
        except (ConnectionTimeout, ConnectionError) as e:
            logger.warning(f"Lỗi kết nối khi thực thi {method_name}: {str(e)}, đang thử lại...")
            self.create_client()  # Tạo lại kết nối trước khi thử lại
            raise  # Tenacity sẽ bắt và thử lại
        except Exception as e:
            logger.error(f"Lỗi không phải kết nối khi thực thi {method_name}: {str(e)}")
            raise
            
    def __getattr__(self, name: str) -> Callable:
        """
        Chuyển tiếp các phương thức không xác định đến Elasticsearch client gốc,
        bọc chúng trong execute() để có khả năng tự phục hồi.
        """
        @wraps(getattr(self._client, name, None))
        def wrapped_method(*args: Any, **kwargs: Any) -> Any:
            return self.execute(name, *args, **kwargs)
            
        return wrapped_method
        
    @property
    def client(self) -> Elasticsearch:
        """Trả về client Elasticsearch gốc."""
        self._ensure_connection()
        return self._client
