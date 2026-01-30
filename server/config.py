"""
配置管理 - 使用Pydantic验证环境变量
确保所有必需的配置都存在且有效
"""
from pydantic_settings import BaseSettings
from pydantic import validator, Field
from functools import lru_cache
from typing import Literal


class Settings(BaseSettings):
    """应用配置 - 自动从环境变量加载并验证"""
    
    # PostgreSQL配置
    POSTGRES_HOST: str = Field(default="localhost", description="PostgreSQL主机")
    POSTGRES_PORT: int = Field(default=5432, ge=1, le=65535)
    POSTGRES_USER: str = Field(description="PostgreSQL用户名")
    POSTGRES_PASSWORD: str = Field(description="PostgreSQL密码")
    POSTGRES_DB: str = Field(description="PostgreSQL数据库名")
    
    # Redis配置
    REDIS_HOST: str = Field(default="localhost")
    REDIS_PORT: int = Field(default=6379, ge=1, le=65535)
    REDIS_PASSWORD: str = Field(default="")
    REDIS_DB: int = Field(default=0, ge=0, le=15)
    
    # Binance API
    BINANCE_API_KEY: str = Field(description="Binance API密钥")
    BINANCE_SECRET_KEY: str = Field(description="Binance私钥")
    
    # 交易模式
    TRADING_MODE: Literal["paper", "live"] = Field(
        default="paper",
        description="交易模式: paper=模拟盘, live=实盘"
    )
    
    # 加密密钥
    ENCRYPTION_KEY: str = Field(
        default="inarbit_secret_key_2026_v1_do_not_share",
        description="数据加密密钥"
    )
    
    # 日志级别
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO"
    )
    
    # API配置
    API_HOST: str = Field(default="0.0.0.0")
    API_PORT: int = Field(default=8000, ge=1, le=65535)
    
    @validator('BINANCE_API_KEY', 'BINANCE_SECRET_KEY')
    def validate_api_keys(cls, v):
        """验证API密钥不为空"""
        if not v or len(v) < 10:
            raise ValueError("API密钥无效，长度过短")
        return v
    
    @validator('ENCRYPTION_KEY')
    def validate_encryption_key(cls, v):
        """验证加密密钥强度"""
        if len(v) < 16:
            raise ValueError("加密密钥长度必须至少16个字符")
        return v
    
    @property
    def postgres_url(self) -> str:
        """PostgreSQL连接URL"""
        return (
            f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )
    
    @property
    def redis_url(self) -> str:
        """Redis连接URL"""
        password_part = f":{self.REDIS_PASSWORD}@" if self.REDIS_PASSWORD else ""
        return f"redis://{password_part}{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    """
    获取配置单例
    使用lru_cache确保Settings只被实例化一次
    """
    return Settings()


# 便捷访问
settings = get_settings()
