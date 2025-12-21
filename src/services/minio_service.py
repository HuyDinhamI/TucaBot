import os
import tempfile
import logging
from typing import Optional
from minio import Minio
from minio.error import S3Error
from src.config import MinioConfig

logger = logging.getLogger("uvicorn.error")

class MinioService:
    """Service để kết nối và thao tác với Minio storage"""
    
    def __init__(self):
        self.client = Minio(
            endpoint=MinioConfig.endpoint,
            access_key=MinioConfig.access_key,
            secret_key=MinioConfig.secret_key,
            secure=MinioConfig.secure
        )
        self.default_bucket = MinioConfig.bucket_name
        
    async def download_file(self, file_path: str, bucket_name: str = "default") -> Optional[str]:
        """
        Download file từ Minio và lưu vào thư mục tạm thời
        
        Args:
            file_path: Đường dẫn file trong Minio (ví dụ: dataset/test_ndhuy/khai_sinh.docx)
            bucket_name: Tên bucket trong Minio
            
        Returns:
            Đường dẫn file tạm thời trên local filesystem hoặc None nếu thất bại
        """
        try:
            # Kiểm tra xem bucket có tồn tại không
            if not self.client.bucket_exists(bucket_name):
                logger.error(f"Bucket '{bucket_name}' does not exist")
                return None
                
            # Tạo thư mục tạm thời
            temp_dir = tempfile.mkdtemp()
            
            # Lấy tên file từ file_path
            file_name = os.path.basename(file_path)
            local_file_path = os.path.join(temp_dir, file_name)
            
            # Download file từ Minio
            logger.info(f"Downloading file from Minio: {file_path}")
            self.client.fget_object(bucket_name, file_path, local_file_path)
            
            logger.info(f"File downloaded successfully to: {local_file_path}")
            return local_file_path
            
        except S3Error as e:
            logger.error(f"S3 Error downloading file {file_path}: {e}")
            return None
        except Exception as e:
            logger.error(f"Error downloading file {file_path}: {e}")
            return None
    
    async def upload_file(self, local_file_path: str, remote_file_path: str, bucket_name: str = "default") -> bool:
        """
        Upload file lên Minio
        
        Args:
            local_file_path: Đường dẫn file trên local filesystem
            remote_file_path: Đường dẫn file muốn lưu trên Minio
            bucket_name: Tên bucket trong Minio
            
        Returns:
            True nếu upload thành công, False nếu thất bại
        """
        try:
            # Kiểm tra xem bucket có tồn tại không, nếu không thì tạo
            if not self.client.bucket_exists(bucket_name):
                self.client.make_bucket(bucket_name)
                logger.info(f"Created bucket: {bucket_name}")
            
            # Upload file
            logger.info(f"Uploading file to Minio: {local_file_path} -> {remote_file_path}")
            self.client.fput_object(bucket_name, remote_file_path, local_file_path)
            
            logger.info(f"File uploaded successfully: {remote_file_path}")
            return True
            
        except S3Error as e:
            logger.error(f"S3 Error uploading file {local_file_path}: {e}")
            return False
        except Exception as e:
            logger.error(f"Error uploading file {local_file_path}: {e}")
            return False
    
    async def get_file_url(self, file_path: str, bucket_name: str = "default", expires_hours: int = 24) -> Optional[str]:
        """
        Tạo URL tạm thời để download file từ Minio
        
        Args:
            file_path: Đường dẫn file trong Minio
            bucket_name: Tên bucket trong Minio  
            expires_hours: Số giờ URL có hiệu lực
            
        Returns:
            URL download tạm thời hoặc None nếu thất bại
        """
        try:
            from datetime import timedelta
            
            logger.info(f"Attempting to generate presigned URL for bucket: {bucket_name}, file: {file_path}")
            
            # Kiểm tra xem bucket có tồn tại không
            if not self.client.bucket_exists(bucket_name):
                logger.error(f"Bucket '{bucket_name}' does not exist")
                return None
            
            # Kiểm tra xem file có tồn tại không
            try:
                self.client.stat_object(bucket_name, file_path)
                logger.info(f"File exists in bucket '{bucket_name}': {file_path}")
            except S3Error as stat_error:
                logger.error(f"File not found in bucket '{bucket_name}': {file_path}.Error: {stat_error}")
                return None
            
            # Tạo presigned URL
            url = self.client.presigned_get_object(
                bucket_name, 
                file_path, 
                expires=timedelta(hours=expires_hours)
            )
            
            logger.info(f"Successfully generated presigned URL for {bucket_name}/{file_path}")
            return url
            
        except S3Error as e:
            logger.error(f"S3 Error generating URL for {bucket_name}/{file_path}: {e}")
            return None
        except Exception as e:
            logger.error(f"Error generating URL for {bucket_name}/{file_path}: {e}")
            return None

# Singleton instance
minio_service = MinioService()
