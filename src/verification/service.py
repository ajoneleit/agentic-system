"""
Verification service implementation.

This module provides a high-level service for managing verification operations,
integrating with the database, and providing a clean API for the verification system.
"""

import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Union
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from src.verification.interfaces import (
    VerificationContext,
    VerificationResult,
    VerificationSummary,
    VerificationServiceInterface
)
from src.verification.models import (
    LanguageType,
    VerificationStage,
    VerificationStatus,
    VerificationResult as DBVerificationResult,
    VerificationSession as DBVerificationSession,
    VerificationMetrics
)
from src.verification.pipeline import VerificationPipeline

logger = logging.getLogger(__name__)


class VerificationService(VerificationServiceInterface):
    """High-level verification service with database integration."""
    
    def __init__(self, db_session: AsyncSession, config: Dict[str, Any] = None):
        """Initialize the verification service.
        
        Args:
            db_session: Database session for persistence
            config: Configuration dictionary for the service
        """
        self.db_session = db_session
        self.config = config or {}
        self.logger = logging.getLogger(self.__class__.__name__)
        
        # Service configuration
        self.auto_persist = self.config.get("auto_persist", True)
        self.max_concurrent_verifications = self.config.get("max_concurrent_verifications", 5)
        self.session_timeout = self.config.get("session_timeout", 3600)  # 1 hour
        
        # Initialize pipeline
        pipeline_config = self.config.get("pipeline", {})
        self.pipeline = VerificationPipeline(pipeline_config)
        
        # Track active sessions
        self._active_sessions: Dict[str, DBVerificationSession] = {}
        self._semaphore = asyncio.Semaphore(self.max_concurrent_verifications)
    
    async def verify_file(
        self, 
        file_path: Union[str, Path], 
        language: Optional[LanguageType] = None,
        project_root: Optional[Union[str, Path]] = None,
        session_id: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None
    ) -> VerificationSummary:
        """
        Verify a single file.
        
        Args:
            file_path: Path to the file to verify
            language: Language type (auto-detected if not provided)
            project_root: Project root directory
            session_id: Optional session ID for grouping verifications
            config: Optional configuration overrides
            
        Returns:
            VerificationSummary with results
        """
        file_path = Path(file_path)
        project_root = Path(project_root) if project_root else file_path.parent
        
        # Auto-detect language if not provided
        if language is None:
            language = self._detect_language(file_path)
        
        # Create context
        context = VerificationContext(
            file_path=file_path,
            language=language,
            project_root=project_root,
            config=config or {}
        )
        
        # Use semaphore to limit concurrent verifications
        async with self._semaphore:
            return await self._verify_with_session(context, session_id)
    
    async def verify_directory(
        self,
        directory_path: Union[str, Path],
        include_patterns: Optional[List[str]] = None,
        exclude_patterns: Optional[List[str]] = None,
        session_id: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None
    ) -> List[VerificationSummary]:
        """
        Verify all files in a directory.
        
        Args:
            directory_path: Path to directory to verify
            include_patterns: Glob patterns for files to include
            exclude_patterns: Glob patterns for files to exclude
            session_id: Optional session ID for grouping verifications
            config: Optional configuration overrides
            
        Returns:
            List of verification summaries
        """
        directory_path = Path(directory_path)
        include_patterns = include_patterns or ["**/*.py", "**/*.js", "**/*.ts"]
        exclude_patterns = exclude_patterns or ["**/node_modules/**", "**/__pycache__/**", "**/venv/**"]
        
        # Discover files
        files_to_verify = self._discover_files(directory_path, include_patterns, exclude_patterns)
        
        if not files_to_verify:
            self.logger.warning(f"No files found to verify in {directory_path}")
            return []
        
        self.logger.info(f"Found {len(files_to_verify)} files to verify in {directory_path}")
        
        # Create contexts
        contexts = []
        for file_path in files_to_verify:
            language = self._detect_language(file_path)
            context = VerificationContext(
                file_path=file_path,
                language=language,
                project_root=directory_path,
                config=config or {}
            )
            contexts.append(context)
        
        # Verify all contexts
        summaries = []
        for context in contexts:
            async with self._semaphore:
                summary = await self._verify_with_session(context, session_id)
                summaries.append(summary)
        
        return summaries
    
    async def create_session(
        self,
        name: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Create a new verification session.
        
        Args:
            name: Optional session name
            metadata: Optional metadata for the session
            
        Returns:
            Session ID
        """
        session_id = str(uuid4())
        
        db_session = DBVerificationSession(
            session_id=session_id,
            name=name or f"Session {session_id[:8]}",
            metadata=metadata or {},
            started_at=datetime.utcnow(),
            status=VerificationStatus.PENDING
        )
        
        if self.auto_persist:
            self.db_session.add(db_session)
            await self.db_session.commit()
        
        self._active_sessions[session_id] = db_session
        self.logger.info(f"Created verification session: {session_id}")
        
        return session_id
    
    async def get_session(self, session_id: str) -> Optional[DBVerificationSession]:
        """
        Get a verification session by ID.
        
        Args:
            session_id: Session ID
            
        Returns:
            Session object or None if not found
        """
        # Check active sessions first
        if session_id in self._active_sessions:
            return self._active_sessions[session_id]
        
        # Query database
        if self.auto_persist:
            result = await self.db_session.execute(
                select(DBVerificationSession)
                .where(DBVerificationSession.session_id == session_id)
                .options(selectinload(DBVerificationSession.results))
            )
            return result.scalar_one_or_none()
        
        return None
    
    async def close_session(self, session_id: str) -> bool:
        """
        Close a verification session.
        
        Args:
            session_id: Session ID
            
        Returns:
            True if session was closed, False if not found
        """
        session = await self.get_session(session_id)
        if not session:
            return False
        
        session.completed_at = datetime.utcnow()
        session.status = VerificationStatus.SUCCESS  # This could be calculated from results
        
        if self.auto_persist:
            await self.db_session.commit()
        
        # Remove from active sessions
        self._active_sessions.pop(session_id, None)
        
        self.logger.info(f"Closed verification session: {session_id}")
        return True
    
    async def get_results(
        self,
        session_id: Optional[str] = None,
        language: Optional[LanguageType] = None,
        status: Optional[VerificationStatus] = None,
        limit: int = 100
    ) -> List[DBVerificationResult]:
        """
        Get verification results with optional filters.
        
        Args:
            session_id: Filter by session ID
            language: Filter by language
            status: Filter by status
            limit: Maximum number of results
            
        Returns:
            List of verification results
        """
        if not self.auto_persist:
            self.logger.warning("Database persistence disabled, cannot retrieve historical results")
            return []
        
        query = select(DBVerificationResult).limit(limit)
        
        if session_id:
            query = query.where(DBVerificationResult.session_id == session_id)
        
        if language:
            query = query.where(DBVerificationResult.language == language)
        
        if status:
            query = query.where(DBVerificationResult.status == status)
        
        query = query.order_by(DBVerificationResult.started_at.desc())
        
        result = await self.db_session.execute(query)
        return result.scalars().all()
    
    async def get_statistics(
        self,
        session_id: Optional[str] = None,
        time_range_hours: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Get verification statistics.
        
        Args:
            session_id: Filter by session ID
            time_range_hours: Filter by time range in hours
            
        Returns:
            Dictionary with statistics
        """
        if not self.auto_persist:
            return {"error": "Database persistence disabled"}
        
        # This would implement complex aggregation queries
        # For now, return basic statistics
        query = select(DBVerificationResult)
        
        if session_id:
            query = query.where(DBVerificationResult.session_id == session_id)
        
        if time_range_hours:
            cutoff_time = datetime.utcnow() - datetime.timedelta(hours=time_range_hours)
            query = query.where(DBVerificationResult.started_at >= cutoff_time)
        
        result = await self.db_session.execute(query)
        results = result.scalars().all()
        
        if not results:
            return {"total": 0}
        
        total = len(results)
        successful = len([r for r in results if r.status == VerificationStatus.SUCCESS])
        failed = len([r for r in results if r.status == VerificationStatus.FAILED])
        errors = len([r for r in results if r.status == VerificationStatus.ERROR])
        
        # Language breakdown
        language_stats = {}
        for result in results:
            lang = result.language.value
            if lang not in language_stats:
                language_stats[lang] = {"total": 0, "successful": 0, "failed": 0}
            language_stats[lang]["total"] += 1
            if result.status == VerificationStatus.SUCCESS:
                language_stats[lang]["successful"] += 1
            elif result.status == VerificationStatus.FAILED:
                language_stats[lang]["failed"] += 1
        
        return {
            "total": total,
            "successful": successful,
            "failed": failed,
            "errors": errors,
            "success_rate": successful / total if total > 0 else 0.0,
            "languages": language_stats,
            "average_execution_time": sum(r.execution_time or 0 for r in results) / total if total > 0 else 0.0
        }
    
    async def is_available(self) -> bool:
        """Check if the verification service is available."""
        return await self.pipeline.is_available()
    
    def get_supported_languages(self) -> Set[LanguageType]:
        """Get supported languages."""
        return self.pipeline.get_supported_languages()
    
    async def _verify_with_session(
        self, 
        context: VerificationContext, 
        session_id: Optional[str]
    ) -> VerificationSummary:
        """Verify a context with optional session tracking."""
        try:
            # Run verification pipeline
            summary = await self.pipeline.verify(context)
            
            # Persist results if auto-persist is enabled
            if self.auto_persist and summary.results:
                await self._persist_results(summary, session_id)
            
            return summary
            
        except Exception as e:
            self.logger.error(f"Verification failed for {context.file_path}: {str(e)}")
            
            # Create error summary
            error_result = VerificationResult(
                success=False,
                status=VerificationStatus.ERROR,
                stage=VerificationStage.PIPELINE,
                language=context.language,
                started_at=datetime.utcnow(),
                completed_at=datetime.utcnow(),
                error_message=f"Service error: {str(e)}",
                error_details={"exception": str(e)}
            )
            
            return VerificationSummary(
                overall_success=False,
                total_stages=0,
                completed_stages=0,
                results=[error_result],
                started_at=datetime.utcnow(),
                completed_at=datetime.utcnow(),
                language=context.language,
                context=context
            )
    
    async def _persist_results(
        self, 
        summary: VerificationSummary, 
        session_id: Optional[str]
    ):
        """Persist verification results to database."""
        try:
            for result in summary.results:
                # Create DB result record
                db_result = DBVerificationResult(
                    result_id=str(uuid4()),
                    session_id=session_id,
                    file_path=str(summary.context.file_path) if summary.context else "",
                    language=result.language,
                    stage=result.stage,
                    status=result.status,
                    started_at=result.started_at,
                    completed_at=result.completed_at,
                    execution_time=result.execution_time,
                    success=result.success,
                    output=result.output,
                    error_message=result.error_message,
                    error_details=result.error_details,
                    warnings=result.warnings,
                    line_count=result.line_count,
                    file_size=result.file_size,
                    config=result.config
                )
                
                self.db_session.add(db_result)
                
                # Create metrics record if available
                if result.metrics:
                    db_metrics = VerificationMetrics(
                        result_id=db_result.result_id,
                        metrics_data=result.metrics,
                        collected_at=datetime.utcnow()
                    )
                    self.db_session.add(db_metrics)
            
            await self.db_session.commit()
            self.logger.debug(f"Persisted {len(summary.results)} verification results")
            
        except Exception as e:
            self.logger.error(f"Failed to persist verification results: {str(e)}")
            await self.db_session.rollback()
    
    def _detect_language(self, file_path: Path) -> LanguageType:
        """Detect language from file extension."""
        suffix = file_path.suffix.lower()
        
        if suffix == ".py":
            return LanguageType.PYTHON
        elif suffix == ".js":
            return LanguageType.JAVASCRIPT
        elif suffix in [".ts", ".tsx"]:
            return LanguageType.TYPESCRIPT
        else:
            # Default to Python for unknown extensions
            return LanguageType.PYTHON
    
    def _discover_files(
        self, 
        directory: Path, 
        include_patterns: List[str], 
        exclude_patterns: List[str]
    ) -> List[Path]:
        """Discover files matching include patterns and not matching exclude patterns."""
        found_files = []
        
        try:
            for pattern in include_patterns:
                for file_path in directory.rglob(pattern):
                    if file_path.is_file():
                        # Check if file should be excluded
                        should_exclude = False
                        for exclude_pattern in exclude_patterns:
                            if file_path.match(exclude_pattern):
                                should_exclude = True
                                break
                        
                        if not should_exclude:
                            found_files.append(file_path)
            
            # Remove duplicates and sort
            found_files = sorted(list(set(found_files)))
            
        except Exception as e:
            self.logger.error(f"Error discovering files: {str(e)}")
        
        return found_files