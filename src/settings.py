from pathlib import Path
from typing import Optional, Dict, List, Any
from pydantic import Field, BaseModel
from pydantic_settings import BaseSettings

from src.utils.config_loader import ConfigReaderInstance


class AppConfig(BaseModel):
    """Application configurations."""

    # all the directory level information defined at app config level
    # we do not want to pollute the env level config with these information
    # this can change on the basis of usage

    BASE_DIR: Path = Path(__file__).resolve().parent.parent

    SETTINGS_DIR: Path = BASE_DIR.joinpath("settings")
    SETTINGS_DIR.mkdir(parents=True, exist_ok=True)

    LOGS_DIR: Path = BASE_DIR.joinpath("logs")
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    MODELS_DIR: Path = BASE_DIR.joinpath("models")
    MODELS_DIR.mkdir(parents=True, exist_ok=True)

    BI_ENCODER_PATH: str = str(MODELS_DIR.joinpath("vietnamese-sbert"))

    # local cache directory to store images or text file
    CACHE_DIR: Path = BASE_DIR.joinpath("cache")
    CACHE_DIR.mkdir(parents=True, exist_ok=True)


class GlobalConfig(BaseSettings):
    """Global configurations."""

    # These variables will be loaded from the .env file. However, if
    # there is a shell environment variable having the same name,
    # that will take precedence.

    APP_CONFIG: AppConfig = AppConfig()

    API_NAME: Optional[str] = Field(None, env="API_NAME")
    API_DESCRIPTION: Optional[str] = Field(None, env="API_DESCRIPTION")
    API_VERSION: Optional[str] = Field(None, env="API_VERSION")
    API_DEBUG_MODE: Optional[bool] = Field(None, env="API_DEBUG_MODE")
    API_KEY: Optional[str] = Field(None, env="API_KEY")

    LOG_CONFIG_FILENAME: Optional[str] = Field(None, env="LOG_CONFIG_FILENAME")
    DEV_HOST: Optional[str] = Field(None, env="DEV_HOST")
    DEV_PORT: Optional[str] = Field(None, env="DEV_PORT")
    LANGSMITH_API_KEY: Optional[str] = Field(None, env="LANGSMITH_API_KEY")

    # define global variables with the Field class
    ENV_STATE: Optional[str] = Field("dev", env="ENV_STATE")

    # environment specific variables do not need the Field class
    # HOST: Optional[str] = Field(None, env="DEV_HOST")
    # PORT: Optional[int] = Field(None, env="DEV_PORT")
    HOST: Optional[str] = DEV_HOST
    PORT: Optional[str] = DEV_PORT
    LOG_LEVEL: Optional[str] = Field(None, env="LOG_LEVEL")

    LLM_CONF: Dict[str, Any] = ConfigReaderInstance.yaml.read_config_from_file(
        "settings/llm.yaml"
    )
    SEARCH_CONF: Dict[str, Any] = ConfigReaderInstance.yaml.read_config_from_file(
        "settings/search.yaml"
    )
    
    AGENT_CONF: Dict[str, Any] = ConfigReaderInstance.yaml.read_config_from_file(
        "settings/agent.yaml"
    )
    
    MINIO_CONF: Dict[str, Any] = ConfigReaderInstance.yaml.read_config_from_file(
        "settings/minio.yaml"
    )
    
    LANGFUSE_CONF: Dict[str, Any] = ConfigReaderInstance.yaml.read_config_from_file(
        "settings/langfuse.yaml"
    )
    class Config:
        """Loads the dotenv file."""

        env_file: str = ".env"
        case_sensitive: bool = True


class DevConfig(GlobalConfig):
    """Development configurations."""

    class Config:
        env_prefix: str = "DEV_"


class ProdConfig(GlobalConfig):
    """Production configurations."""

    class Config:
        env_prefix: str = "PROD_"


class FactoryConfig:
    """Returns a config instance depending on the ENV_STATE variable."""

    def __init__(self, env_state: Optional[str]):
        self.env_state = env_state

    def __call__(self):
        if self.env_state == "dev":
            return DevConfig()

        elif self.env_state == "prod":
            return ProdConfig()


settings = FactoryConfig(GlobalConfig().ENV_STATE)()
# print(settings.__repr__())
