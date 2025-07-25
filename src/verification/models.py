"""
Database models for the verification system.

This module defines SQLAlchemy models for storing verification results,
maintaining history, and tracking performance metrics.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    Integer,
    JSON,
    String,
    Text,
)
from sqlalchemy.ext.declarative import declarative_base

# Use the same Base as the prompt evolution system for consistency
from src.learning.prompt_evolution import Base


class VerificationStage(str, Enum):
    """Stages of verification process."""
    
    COMPILER = "compiler"
    SYNTAX = "syntax"
    TYPE_CHECK = "type_check"
    LINT = "lint"
    TEST = "test"
    INTEGRATION = "integration"


class VerificationStatus(str, Enum):
    """Status of verification execution."""
    
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"
    ERROR = "error"


class LanguageType(str, Enum):
    """Supported programming languages."""
    
    PYTHON = "python"
    JAVASCRIPT = "javascript"
    TYPESCRIPT = "typescript"
    GO = "go"
    RUST = "rust"
    JAVA = "java"


class VerificationResult(Base):
    """Database model for storing verification results."""
    
    __tablename__ = "verification_results"
    
    id = Column(Integer, primary_key=True)
    verification_id = Column(String(255), unique=True, index=True)
    artifact_id = Column(String(255), index=True)
    stage = Column(String(50), index=True)  # VerificationStage
    language = Column(String(50), index=True)  # LanguageType
    status = Column(String(50), index=True)  # VerificationStatus
    
    # Execution details
    started_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    execution_time = Column(Float, default=0.0)
    
    # Results and errors
    success = Column(Boolean, default=False)
    output = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)
    error_details = Column(JSON, nullable=True)
    warnings = Column(JSON, nullable=True)
    
    # Metrics and metadata
    metrics = Column(JSON, nullable=True)  # Coverage, performance, etc.
    file_path = Column(String(500), nullable=True)
    line_count = Column(Integer, nullable=True)
    
    # Configuration used
    verifier_config = Column(JSON, nullable=True)
    environment_info = Column(JSON, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)


class VerificationSession(Base):
    """Database model for tracking complete verification sessions."""
    
    __tablename__ = "verification_sessions"
    
    id = Column(Integer, primary_key=True)
    session_id = Column(String(255), unique=True, index=True)
    task_id = Column(String(255), index=True, nullable=True)
    agent_id = Column(String(255), index=True, nullable=True)
    
    # Session metadata
    total_stages = Column(Integer, default=0)
    completed_stages = Column(Integer, default=0)
    failed_stages = Column(Integer, default=0)
    skipped_stages = Column(Integer, default=0)
    
    # Overall status
    overall_status = Column(String(50), index=True)  # VerificationStatus
    overall_success = Column(Boolean, default=False)
    
    # Timing
    started_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    total_execution_time = Column(Float, default=0.0)
    
    # Results summary
    summary = Column(JSON, nullable=True)
    artifacts_verified = Column(JSON, nullable=True)  # List of artifact IDs
    
    created_at = Column(DateTime, default=datetime.utcnow)


class VerificationTemplate(Base):
    """Database model for verification template configurations."""
    
    __tablename__ = "verification_templates"
    
    id = Column(Integer, primary_key=True)
    template_id = Column(String(255), unique=True, index=True)
    name = Column(String(255), index=True)
    description = Column(Text, nullable=True)
    language = Column(String(50), index=True)  # LanguageType
    
    # Template configuration
    stages = Column(JSON)  # List of VerificationStage
    stage_configs = Column(JSON)  # Configuration for each stage
    requirements = Column(JSON, nullable=True)  # Dependencies, tools required
    
    # Performance and usage
    usage_count = Column(Integer, default=0)
    success_rate = Column(Float, default=0.0)
    avg_execution_time = Column(Float, default=0.0)
    
    # Metadata
    is_active = Column(Boolean, default=True)
    version = Column(Integer, default=1)
    parent_template_id = Column(String(255), nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class VerificationMetrics(Base):
    """Database model for aggregated verification metrics."""
    
    __tablename__ = "verification_metrics"
    
    id = Column(Integer, primary_key=True)
    metric_id = Column(String(255), unique=True, index=True)
    
    # Time period for metrics
    period_start = Column(DateTime, index=True)
    period_end = Column(DateTime, index=True)
    period_type = Column(String(50))  # hourly, daily, weekly, monthly
    
    # Aggregated metrics
    total_verifications = Column(Integer, default=0)
    successful_verifications = Column(Integer, default=0)
    failed_verifications = Column(Integer, default=0)
    avg_execution_time = Column(Float, default=0.0)
    
    # By language
    language_breakdown = Column(JSON, nullable=True)
    # By stage
    stage_breakdown = Column(JSON, nullable=True)
    # By status
    status_breakdown = Column(JSON, nullable=True)
    
    # Performance trends
    success_rate_trend = Column(JSON, nullable=True)
    execution_time_trend = Column(JSON, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)