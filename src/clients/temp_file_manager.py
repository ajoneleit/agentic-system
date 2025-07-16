"""Temporary file management for Claude CLI operations.

This module provides secure temporary file creation and cleanup for
large prompts and other CLI operations.
"""

import atexit
import os
import signal
import tempfile
from pathlib import Path
from typing import Dict, Optional, Set
from contextlib import contextmanager
from uuid import uuid4

from structlog import get_logger

from src.core.result import Result
from src.core.exceptions import FileOperationError

logger = get_logger(__name__)


class TempFileManager:
    """Manages temporary file lifecycle for Claude CLI operations."""
    
    def __init__(self, cleanup_on_exit: bool = True):
        """Initialize the temporary file manager.
        
        Args:
            cleanup_on_exit: Whether to register cleanup on process exit
        """
        self._temp_files: Set[Path] = set()
        self._file_handles: Dict[Path, int] = {}
        self._cleanup_on_exit = cleanup_on_exit
        
        if cleanup_on_exit:
            self._register_cleanup_handlers()
    
    def _register_cleanup_handlers(self) -> None:
        """Register cleanup handlers for process exit."""
        atexit.register(self._cleanup_all_files)
        
        # Register signal handlers for graceful shutdown
        try:
            signal.signal(signal.SIGTERM, self._signal_handler)
            signal.signal(signal.SIGINT, self._signal_handler)
        except ValueError:
            # Signal handlers can only be registered in main thread
            logger.debug("Could not register signal handlers (not in main thread)")
    
    def _signal_handler(self, signum: int, frame) -> None:
        """Handle process signals by cleaning up temp files.
        
        Args:
            signum: Signal number
            frame: Current stack frame
        """
        logger.info(f"Received signal {signum}, cleaning up temporary files")
        self._cleanup_all_files()
    
    def create_temp_file(
        self,
        content: str,
        suffix: str = '.md',
        prefix: str = 'claude_prompt_',
        encoding: str = 'utf-8'
    ) -> Result[Path]:
        """Create a temporary file with content.
        
        Args:
            content: Content to write to the file
            suffix: File suffix/extension
            prefix: File prefix
            encoding: Text encoding
            
        Returns:
            Result containing path to temporary file or error
        """
        try:
            # Create secure temporary file
            fd, temp_path = tempfile.mkstemp(
                suffix=suffix,
                prefix=prefix,
                text=True
            )
            
            temp_file_path = Path(temp_path)
            
            # Store file descriptor and path
            self._file_handles[temp_file_path] = fd
            self._temp_files.add(temp_file_path)
            
            # Write content to file
            try:
                with os.fdopen(fd, 'w', encoding=encoding) as f:
                    f.write(content)
                    f.flush()
                    os.fsync(f.fileno())
                
                # Remove from handles dict since file is now closed
                del self._file_handles[temp_file_path]
                
                logger.debug(
                    "Temporary file created",
                    path=str(temp_file_path),
                    size=len(content)
                )
                
                return Result.success(temp_file_path)
                
            except Exception as e:
                # Ensure file descriptor is closed on error
                try:
                    os.close(fd)
                except:
                    pass
                raise e
                
        except Exception as e:
            logger.error("Failed to create temporary file", error=str(e))
            return Result.failure(FileOperationError(f"Failed to create temporary file: {str(e)}"))
    
    @contextmanager
    def temp_file_context(
        self,
        content: str,
        suffix: str = '.md',
        prefix: str = 'claude_prompt_',
        encoding: str = 'utf-8'
    ):
        """Context manager for temporary file creation and cleanup.
        
        Args:
            content: Content to write to the file
            suffix: File suffix/extension
            prefix: File prefix
            encoding: Text encoding
            
        Yields:
            Path to temporary file
            
        Raises:
            FileOperationError: If file creation fails
        """
        result = self.create_temp_file(content, suffix, prefix, encoding)
        if result.is_failure():
            raise FileOperationError(str(result.error))
        
        temp_path = result.value
        try:
            yield temp_path
        finally:
            self.cleanup_file(temp_path)
    
    def cleanup_file(self, file_path: Path) -> Result[None]:
        """Clean up a specific temporary file.
        
        Args:
            file_path: Path to the file to clean up
            
        Returns:
            Result indicating success or failure
        """
        try:
            # Close file descriptor if still open
            if file_path in self._file_handles:
                try:
                    os.close(self._file_handles[file_path])
                    del self._file_handles[file_path]
                except:
                    pass
            
            # Remove file if it exists
            if file_path.exists():
                file_path.unlink()
                logger.debug("Temporary file cleaned up", path=str(file_path))
            
            # Remove from tracking
            self._temp_files.discard(file_path)
            
            return Result.success(None)
            
        except Exception as e:
            logger.warning("Failed to clean up temporary file", path=str(file_path), error=str(e))
            return Result.failure(FileOperationError(f"Failed to clean up file: {str(e)}"))
    
    def cleanup_all(self) -> None:
        """Clean up all temporary files."""
        self._cleanup_all_files()
    
    def _cleanup_all_files(self) -> None:
        """Internal method to clean up all temporary files."""
        files_to_cleanup = list(self._temp_files)
        
        for file_path in files_to_cleanup:
            try:
                self.cleanup_file(file_path)
            except Exception as e:
                logger.warning("Failed to cleanup file during bulk cleanup", path=str(file_path), error=str(e))
        
        # Close any remaining file descriptors
        for file_path, fd in list(self._file_handles.items()):
            try:
                os.close(fd)
                del self._file_handles[file_path]
            except:
                pass
        
        if files_to_cleanup:
            logger.info("Cleaned up temporary files", count=len(files_to_cleanup))
    
    def get_temp_file_count(self) -> int:
        """Get the number of active temporary files.
        
        Returns:
            Number of temporary files being tracked
        """
        return len(self._temp_files)
    
    def get_temp_files(self) -> Set[Path]:
        """Get set of all temporary files.
        
        Returns:
            Set of temporary file paths
        """
        return self._temp_files.copy()
    
    def is_temp_file(self, file_path: Path) -> bool:
        """Check if a file is managed by this temp file manager.
        
        Args:
            file_path: Path to check
            
        Returns:
            True if file is managed by this manager
        """
        return file_path in self._temp_files


# Global temp file manager instance
_global_temp_manager: Optional[TempFileManager] = None


def get_temp_manager() -> TempFileManager:
    """Get the global temporary file manager instance.
    
    Returns:
        Global TempFileManager instance
    """
    global _global_temp_manager
    if _global_temp_manager is None:
        _global_temp_manager = TempFileManager()
    return _global_temp_manager


def create_temp_file(
    content: str,
    suffix: str = '.md',
    prefix: str = 'claude_prompt_',
    encoding: str = 'utf-8'
) -> Result[Path]:
    """Create a temporary file using the global manager.
    
    Args:
        content: Content to write to the file
        suffix: File suffix/extension
        prefix: File prefix
        encoding: Text encoding
        
    Returns:
        Result containing path to temporary file or error
    """
    return get_temp_manager().create_temp_file(content, suffix, prefix, encoding)


def cleanup_temp_file(file_path: Path) -> Result[None]:
    """Clean up a temporary file using the global manager.
    
    Args:
        file_path: Path to the file to clean up
        
    Returns:
        Result indicating success or failure
    """
    return get_temp_manager().cleanup_file(file_path)


def cleanup_all_temp_files() -> None:
    """Clean up all temporary files using the global manager."""
    get_temp_manager().cleanup_all()


# Context manager for temporary files
@contextmanager
def temp_file(
    content: str,
    suffix: str = '.md',
    prefix: str = 'claude_prompt_',
    encoding: str = 'utf-8'
):
    """Context manager for temporary file creation and cleanup.
    
    Args:
        content: Content to write to the file
        suffix: File suffix/extension
        prefix: File prefix
        encoding: Text encoding
        
    Yields:
        Path to temporary file
        
    Raises:
        FileOperationError: If file creation fails
    """
    with get_temp_manager().temp_file_context(content, suffix, prefix, encoding) as temp_path:
        yield temp_path