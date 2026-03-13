"""
Configuration management for Intune Device Healer
"""

import os
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict
from dotenv import load_dotenv

load_dotenv()


class Config(BaseModel):
    """Server configuration"""

    model_config = ConfigDict(extra="allow")

    # Azure Authentication
    azure_client_id: str = Field(default_factory=lambda: os.getenv("AZURE_CLIENT_ID", ""))
    azure_tenant_id: str = Field(default_factory=lambda: os.getenv("AZURE_TENANT_ID", ""))
    azure_client_secret: str = Field(default_factory=lambda: os.getenv("AZURE_CLIENT_SECRET", ""))

    # Atomicwork Integration
    atomicwork_base_url: str = Field(
        default_factory=lambda: os.getenv("ATOMICWORK_BASE_URL", "https://atombanking.atomicwork.com")
    )
    atomicwork_api_key: str = Field(default_factory=lambda: os.getenv("ATOMICWORK_API_KEY", ""))

    # Server Configuration
    log_level: str = Field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))
    max_concurrent_operations: int = Field(
        default_factory=lambda: int(os.getenv("MAX_CONCURRENT_OPERATIONS", "10"))
    )
    operation_timeout: int = Field(
        default_factory=lambda: int(os.getenv("OPERATION_TIMEOUT", "600"))
    )

    # Safety Settings
    auto_fix_enabled: bool = Field(
        default_factory=lambda: os.getenv("AUTO_FIX_ENABLED", "true").lower() == "true"
    )
    require_approval_risky_ops: bool = Field(
        default_factory=lambda: os.getenv("REQUIRE_APPROVAL_RISKY_OPS", "true").lower() == "true"
    )
    enable_rollback: bool = Field(
        default_factory=lambda: os.getenv("ENABLE_ROLLBACK", "true").lower() == "true"
    )
    create_restore_points: bool = Field(
        default_factory=lambda: os.getenv("CREATE_RESTORE_POINTS", "true").lower() == "true"
    )

    # Monitoring
    enable_metrics: bool = Field(
        default_factory=lambda: os.getenv("ENABLE_METRICS", "true").lower() == "true"
    )
    metrics_retention_days: int = Field(
        default_factory=lambda: int(os.getenv("METRICS_RETENTION_DAYS", "30"))
    )
    health_check_interval_minutes: int = Field(
        default_factory=lambda: int(os.getenv("HEALTH_CHECK_INTERVAL_MINUTES", "60"))
    )

    # Script Execution
    script_timeout_seconds: int = Field(
        default_factory=lambda: int(os.getenv("SCRIPT_TIMEOUT_SECONDS", "300"))
    )
    max_script_output_size_kb: int = Field(
        default_factory=lambda: int(os.getenv("MAX_SCRIPT_OUTPUT_SIZE_KB", "500"))
    )
    allow_custom_scripts: bool = Field(
        default_factory=lambda: os.getenv("ALLOW_CUSTOM_SCRIPTS", "true").lower() == "true"
    )

    # Advanced
    debug_mode: bool = Field(
        default_factory=lambda: os.getenv("DEBUG_MODE", "false").lower() == "true"
    )
    dry_run_mode: bool = Field(
        default_factory=lambda: os.getenv("DRY_RUN_MODE", "false").lower() == "true"
    )

    # Graph API
    graph_api_base_url: str = "https://graph.microsoft.com/v1.0"
    graph_api_beta_url: str = "https://graph.microsoft.com/beta"

    # ── Database (PostgreSQL) ─────────────────────────────────────────────────
    database_url: str = Field(
        default_factory=lambda: os.getenv(
            "DATABASE_URL",
            "postgresql+asyncpg://healer:healer@localhost:5432/healer"
        )
    )
    db_pool_size: int = Field(default_factory=lambda: int(os.getenv("DB_POOL_SIZE", "10")))
    db_max_overflow: int = Field(default_factory=lambda: int(os.getenv("DB_MAX_OVERFLOW", "20")))
    audit_log_retention_days: int = Field(
        default_factory=lambda: int(os.getenv("AUDIT_LOG_RETENTION_DAYS", "90"))
    )

    # ── JWT Auth ─────────────────────────────────────────────────────────────
    jwt_secret_key: str = Field(
        default_factory=lambda: os.getenv("JWT_SECRET_KEY", "change-me-in-production")
    )
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = Field(
        default_factory=lambda: int(os.getenv("JWT_EXPIRE_MINUTES", "60"))
    )

    # Static API users loaded from env: HEALER_USERS="admin:pw:admin,ops:pw:operator"
    # Format: username:password:role  (role: admin | operator | viewer)
    healer_users: str = Field(
        default_factory=lambda: os.getenv("HEALER_USERS", "admin:admin:admin")
    )

    # ── Rules Config ─────────────────────────────────────────────────────────
    rules_config_path: str = Field(
        default_factory=lambda: os.getenv("RULES_CONFIG_PATH", "/config/rules.yaml")
    )

    # ── Prometheus ───────────────────────────────────────────────────────────
    metrics_enabled: bool = Field(
        default_factory=lambda: os.getenv("METRICS_ENABLED", "true").lower() == "true"
    )

    def validate(self) -> None:
        """Validate required configuration"""
        if not self.azure_client_id:
            raise ValueError("AZURE_CLIENT_ID is required")
        if not self.azure_tenant_id:
            raise ValueError("AZURE_TENANT_ID is required")
        if not self.azure_client_secret:
            raise ValueError("AZURE_CLIENT_SECRET is required")

    def get_users(self) -> list[dict]:
        """Parse HEALER_USERS env var into list of {username, password, role}."""
        users = []
        for entry in self.healer_users.split(","):
            parts = entry.strip().split(":")
            if len(parts) == 3:
                users.append({"username": parts[0], "password": parts[1], "role": parts[2]})
        return users


    # Create global settings instance
    
    @classmethod
    def load_settings(cls):
        s = cls()
        # Render provides DATABASE_URL starting with postgres://
        # asyncpg requires postgresql+asyncpg://
        if s.database_url.startswith("postgres://"):
            s.database_url = s.database_url.replace("postgres://", "postgresql+asyncpg://", 1)
        elif s.database_url.startswith("postgresql://"):
            s.database_url = s.database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return s

settings = Config.load_settings()
