"""Safe file system operations for artifact management.

This module provides thread-safe, atomic file operations with proper
error handling and cross-platform compatibility.
"""

import asyncio
import hashlib
import os
import shutil
import tempfile
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional, Union

import aiofiles
import aiofiles.os
from structlog import get_logger

logger = get_logger(__name__)


class FileManagerError(Exception):
    """Base exception for file manager errors."""
    pass


class PathTraversalError(FileManagerError):
    """Raised when a path traversal attempt is detected."""
    pass


class FileSizeError(FileManagerError):
    """Raised when file size exceeds limits."""
    pass


class FileTypeError(FileManagerError):
    """Raised when file type is not allowed."""
    pass


class FileManager:
    """Manages file system operations for artifacts.
    
    Provides safe, atomic file operations with validation and
    cross-platform compatibility.
    """
    
    # Default file type whitelist
    DEFAULT_ALLOWED_EXTENSIONS = {
        # Source code
        '.py', '.js', '.ts', '.java', '.go', '.rs', '.cpp', '.c', '.h', '.hpp',
        '.rb', '.php', '.swift', '.kt', '.scala', '.r', '.m', '.mm',
        
        # Web
        '.html', '.css', '.scss', '.sass', '.less', '.vue', '.jsx', '.tsx',
        
        # Data/Config
        '.json', '.yaml', '.yml', '.xml', '.toml', '.ini', '.env', '.properties',
        
        # Documentation
        '.md', '.rst', '.txt', '.adoc',
        
        # Build/Project
        '.gradle', '.maven', '.sbt', '.cmake', '.make', '.dockerfile',
        
        # Shell
        '.sh', '.bash', '.zsh', '.fish', '.ps1', '.bat', '.cmd',
        
        # Other
        '.sql', '.graphql', '.proto', '.thrift'
    }
    
    def __init__(
        self,
        base_path: Path,
        max_file_size: int = 10 * 1024 * 1024,  # 10MB default
        allowed_extensions: Optional[set] = None,
        enable_backup: bool = True
    ):
        """Initialize file manager.
        
        Args:
            base_path: Base directory for all file operations
            max_file_size: Maximum allowed file size in bytes
            allowed_extensions: Set of allowed file extensions
            enable_backup: Whether to create backups before modifications
        """
        self.base_path = Path(base_path).resolve()
        self.max_file_size = max_file_size
        self.allowed_extensions = allowed_extensions or self.DEFAULT_ALLOWED_EXTENSIONS
        self.enable_backup = enable_backup
        
        # Create base directory if it doesn't exist
        self.base_path.mkdir(parents=True, exist_ok=True)
        
        # Lock for atomic operations
        self._locks: Dict[Path, asyncio.Lock] = {}
        self._global_lock = asyncio.Lock()
        
        logger.info(
            "FileManager initialized",
            base_path=str(self.base_path),
            max_file_size=max_file_size
        )
    
    async def read_file(
        self,
        relative_path: Union[str, Path],
        encoding: str = 'utf-8'
    ) -> str:
        """Safely read a file.
        
        Args:
            relative_path: Path relative to base_path
            encoding: File encoding
            
        Returns:
            File content
            
        Raises:
            FileNotFoundError: If file doesn't exist
            PathTraversalError: If path attempts traversal
            FileManagerError: For other errors
        """
        file_path = self._resolve_safe_path(relative_path)
        
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {relative_path}")
        
        if not file_path.is_file():
            raise FileManagerError(f"Not a file: {relative_path}")
        
        try:
            async with aiofiles.open(file_path, 'r', encoding=encoding) as f:
                content = await f.read()
            
            logger.debug(
                "File read successfully",
                path=str(relative_path),
                size=len(content)
            )
            
            return content
            
        except Exception as e:
            logger.error(
                "Failed to read file",
                path=str(relative_path),
                error=str(e)
            )
            raise FileManagerError(f"Failed to read file: {e}")
    
    async def write_file(
        self,
        relative_path: Union[str, Path],
        content: str,
        encoding: str = 'utf-8',
        create_dirs: bool = True
    ) -> Path:
        """Safely write content to a file atomically.
        
        Args:
            relative_path: Path relative to base_path
            content: Content to write
            encoding: File encoding
            create_dirs: Whether to create parent directories
            
        Returns:
            Absolute path to written file
            
        Raises:
            PathTraversalError: If path attempts traversal
            FileSizeError: If content exceeds size limit
            FileTypeError: If file type not allowed
        """
        file_path = self._resolve_safe_path(relative_path)
        
        # Validate file type
        if not self._is_allowed_file_type(file_path):
            raise FileTypeError(f"File type not allowed: {file_path.suffix}")
        
        # Check size
        content_bytes = content.encode(encoding)
        if len(content_bytes) > self.max_file_size:
            raise FileSizeError(
                f"File size {len(content_bytes)} exceeds limit {self.max_file_size}"
            )
        
        # Get file-specific lock
        async with self._get_file_lock(file_path):
            # Create parent directories if needed
            if create_dirs:
                file_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Create backup if file exists and backup enabled
            if self.enable_backup and file_path.exists():
                await self._create_backup(file_path)
            
            # Write atomically using temporary file
            temp_fd, temp_path = tempfile.mkstemp(
                dir=file_path.parent,
                prefix=f".{file_path.name}.",
                suffix=".tmp"
            )
            temp_path = Path(temp_path)
            
            try:
                # Write to temporary file
                async with aiofiles.open(temp_path, 'w', encoding=encoding) as f:
                    await f.write(content)
                
                # Set permissions to match original if it exists
                if file_path.exists():
                    shutil.copystat(file_path, temp_path)
                
                # Atomic rename
                temp_path.replace(file_path)
                
                logger.info(
                    "File written successfully",
                    path=str(relative_path),
                    size=len(content_bytes)
                )
                
                return file_path
                
            except Exception as e:
                # Clean up temporary file on error
                if temp_path.exists():
                    temp_path.unlink()
                
                logger.error(
                    "Failed to write file",
                    path=str(relative_path),
                    error=str(e)
                )
                raise FileManagerError(f"Failed to write file: {e}")
            finally:
                # Close the file descriptor
                os.close(temp_fd)
    
    async def delete_file(
        self,
        relative_path: Union[str, Path],
        backup_before_delete: bool = True
    ) -> None:
        """Safely delete a file.
        
        Args:
            relative_path: Path relative to base_path
            backup_before_delete: Whether to backup before deletion
            
        Raises:
            FileNotFoundError: If file doesn't exist
            PathTraversalError: If path attempts traversal
        """
        file_path = self._resolve_safe_path(relative_path)
        
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {relative_path}")
        
        if not file_path.is_file():
            raise FileManagerError(f"Not a file: {relative_path}")
        
        async with self._get_file_lock(file_path):
            # Create backup if requested
            if backup_before_delete and self.enable_backup:
                await self._create_backup(file_path)
            
            try:
                file_path.unlink()
                
                logger.info(
                    "File deleted",
                    path=str(relative_path)
                )
                
            except Exception as e:
                logger.error(
                    "Failed to delete file",
                    path=str(relative_path),
                    error=str(e)
                )
                raise FileManagerError(f"Failed to delete file: {e}")
    
    async def copy_file(
        self,
        source_path: Union[str, Path],
        dest_path: Union[str, Path],
        overwrite: bool = False
    ) -> Path:
        """Copy a file safely.
        
        Args:
            source_path: Source path relative to base_path
            dest_path: Destination path relative to base_path
            overwrite: Whether to overwrite existing file
            
        Returns:
            Absolute path to destination file
            
        Raises:
            FileNotFoundError: If source doesn't exist
            FileExistsError: If destination exists and overwrite=False
        """
        source = self._resolve_safe_path(source_path)
        dest = self._resolve_safe_path(dest_path)
        
        if not source.exists():
            raise FileNotFoundError(f"Source file not found: {source_path}")
        
        if dest.exists() and not overwrite:
            raise FileExistsError(f"Destination already exists: {dest_path}")
        
        # Validate destination file type
        if not self._is_allowed_file_type(dest):
            raise FileTypeError(f"File type not allowed: {dest.suffix}")
        
        async with self._get_file_lock(source), self._get_file_lock(dest):
            # Create parent directories
            dest.parent.mkdir(parents=True, exist_ok=True)
            
            # Create backup of destination if it exists
            if dest.exists() and self.enable_backup:
                await self._create_backup(dest)
            
            try:
                # For async copy, read and write in chunks
                async with aiofiles.open(source, 'rb') as src:
                    async with aiofiles.open(dest, 'wb') as dst:
                        while chunk := await src.read(8192):
                            await dst.write(chunk)
                
                # Copy metadata
                shutil.copystat(source, dest)
                
                logger.info(
                    "File copied",
                    source=str(source_path),
                    dest=str(dest_path)
                )
                
                return dest
                
            except Exception as e:
                logger.error(
                    "Failed to copy file",
                    source=str(source_path),
                    dest=str(dest_path),
                    error=str(e)
                )
                raise FileManagerError(f"Failed to copy file: {e}")
    
    async def move_file(
        self,
        source_path: Union[str, Path],
        dest_path: Union[str, Path],
        overwrite: bool = False
    ) -> Path:
        """Move a file safely.
        
        Args:
            source_path: Source path relative to base_path
            dest_path: Destination path relative to base_path
            overwrite: Whether to overwrite existing file
            
        Returns:
            Absolute path to destination file
        """
        source = self._resolve_safe_path(source_path)
        dest = self._resolve_safe_path(dest_path)
        
        if not source.exists():
            raise FileNotFoundError(f"Source file not found: {source_path}")
        
        if dest.exists() and not overwrite:
            raise FileExistsError(f"Destination already exists: {dest_path}")
        
        # Validate destination file type
        if not self._is_allowed_file_type(dest):
            raise FileTypeError(f"File type not allowed: {dest.suffix}")
        
        async with self._get_file_lock(source), self._get_file_lock(dest):
            # Create parent directories
            dest.parent.mkdir(parents=True, exist_ok=True)
            
            # Create backup of destination if it exists
            if dest.exists() and self.enable_backup:
                await self._create_backup(dest)
            
            try:
                # Use rename for atomic operation if on same filesystem
                source.rename(dest)
                
                logger.info(
                    "File moved",
                    source=str(source_path),
                    dest=str(dest_path)
                )
                
                return dest
                
            except OSError:
                # Fall back to copy and delete if rename fails (cross-filesystem)
                await self.copy_file(source_path, dest_path, overwrite)
                await self.delete_file(source_path, backup_before_delete=False)
                return dest
    
    async def list_files(
        self,
        relative_path: Union[str, Path] = ".",
        pattern: Optional[str] = None,
        recursive: bool = False
    ) -> List[Path]:
        """List files in a directory.
        
        Args:
            relative_path: Directory path relative to base_path
            pattern: Glob pattern to match files
            recursive: Whether to search recursively
            
        Returns:
            List of file paths relative to base_path
        """
        dir_path = self._resolve_safe_path(relative_path)
        
        if not dir_path.exists():
            return []
        
        if not dir_path.is_dir():
            raise FileManagerError(f"Not a directory: {relative_path}")
        
        files = []
        
        try:
            if pattern:
                if recursive:
                    glob_pattern = f"**/{pattern}"
                else:
                    glob_pattern = pattern
                
                for file_path in dir_path.glob(glob_pattern):
                    if file_path.is_file():
                        files.append(file_path.relative_to(self.base_path))
            else:
                if recursive:
                    for file_path in dir_path.rglob("*"):
                        if file_path.is_file():
                            files.append(file_path.relative_to(self.base_path))
                else:
                    for file_path in dir_path.iterdir():
                        if file_path.is_file():
                            files.append(file_path.relative_to(self.base_path))
            
            return sorted(files)
            
        except Exception as e:
            logger.error(
                "Failed to list files",
                path=str(relative_path),
                error=str(e)
            )
            raise FileManagerError(f"Failed to list files: {e}")
    
    async def get_file_info(
        self,
        relative_path: Union[str, Path]
    ) -> Dict[str, Any]:
        """Get information about a file.
        
        Args:
            relative_path: Path relative to base_path
            
        Returns:
            Dictionary with file information
        """
        file_path = self._resolve_safe_path(relative_path)
        
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {relative_path}")
        
        stat = file_path.stat()
        
        # Calculate checksum
        checksum = await self._calculate_checksum(file_path)
        
        return {
            "path": str(relative_path),
            "absolute_path": str(file_path),
            "size": stat.st_size,
            "created": datetime.fromtimestamp(stat.st_ctime),
            "modified": datetime.fromtimestamp(stat.st_mtime),
            "is_file": file_path.is_file(),
            "is_dir": file_path.is_dir(),
            "suffix": file_path.suffix,
            "checksum": checksum,
            "permissions": oct(stat.st_mode)[-3:]
        }
    
    async def create_directory(
        self,
        relative_path: Union[str, Path],
        parents: bool = True,
        exist_ok: bool = True
    ) -> Path:
        """Create a directory.
        
        Args:
            relative_path: Path relative to base_path
            parents: Create parent directories if needed
            exist_ok: Don't raise error if directory exists
            
        Returns:
            Absolute path to created directory
        """
        dir_path = self._resolve_safe_path(relative_path)
        
        try:
            dir_path.mkdir(parents=parents, exist_ok=exist_ok)
            
            logger.info(
                "Directory created",
                path=str(relative_path)
            )
            
            return dir_path
            
        except Exception as e:
            logger.error(
                "Failed to create directory",
                path=str(relative_path),
                error=str(e)
            )
            raise FileManagerError(f"Failed to create directory: {e}")
    
    async def cleanup_old_files(
        self,
        days: int,
        relative_path: Union[str, Path] = ".",
        pattern: Optional[str] = None,
        dry_run: bool = False
    ) -> List[Path]:
        """Clean up files older than specified days.
        
        Args:
            days: Files older than this many days will be deleted
            relative_path: Directory to clean
            pattern: File pattern to match
            dry_run: If True, only return files that would be deleted
            
        Returns:
            List of deleted file paths
        """
        cutoff_time = datetime.now().timestamp() - (days * 24 * 60 * 60)
        deleted_files = []
        
        files = await self.list_files(relative_path, pattern, recursive=True)
        
        for file_path in files:
            abs_path = self.base_path / file_path
            
            try:
                stat = abs_path.stat()
                if stat.st_mtime < cutoff_time:
                    if not dry_run:
                        await self.delete_file(file_path)
                    deleted_files.append(file_path)
            except Exception as e:
                logger.warning(
                    "Failed to process file for cleanup",
                    path=str(file_path),
                    error=str(e)
                )
        
        logger.info(
            "Cleanup completed",
            files_deleted=len(deleted_files),
            dry_run=dry_run
        )
        
        return deleted_files
    
    def _resolve_safe_path(self, relative_path: Union[str, Path]) -> Path:
        """Resolve a path safely, preventing traversal attacks.
        
        Args:
            relative_path: Path relative to base_path
            
        Returns:
            Resolved absolute path
            
        Raises:
            PathTraversalError: If path would escape base_path
        """
        # Convert to Path and resolve
        path = Path(relative_path)
        
        # Remove any leading slashes or drive letters
        if path.is_absolute():
            raise PathTraversalError(f"Absolute paths not allowed: {path}")
        
        # Resolve the full path
        full_path = (self.base_path / path).resolve()
        
        # Ensure it's within base_path
        try:
            full_path.relative_to(self.base_path)
        except ValueError:
            raise PathTraversalError(f"Path traversal detected: {relative_path}")
        
        return full_path
    
    def _is_allowed_file_type(self, file_path: Path) -> bool:
        """Check if file type is allowed.
        
        Args:
            file_path: File path to check
            
        Returns:
            True if file type is allowed
        """
        return file_path.suffix.lower() in self.allowed_extensions
    
    @asynccontextmanager
    async def _get_file_lock(self, file_path: Path) -> AsyncIterator[asyncio.Lock]:
        """Get a lock for a specific file path.
        
        Args:
            file_path: File path to lock
            
        Yields:
            File-specific lock
        """
        async with self._global_lock:
            if file_path not in self._locks:
                self._locks[file_path] = asyncio.Lock()
            lock = self._locks[file_path]
        
        async with lock:
            yield lock
    
    async def _create_backup(self, file_path: Path) -> Path:
        """Create a backup of a file.
        
        Args:
            file_path: File to backup
            
        Returns:
            Path to backup file
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = file_path.parent / f".{file_path.name}.{timestamp}.bak"
        
        # Copy file to backup location
        shutil.copy2(file_path, backup_path)
        
        logger.debug(
            "Backup created",
            original=str(file_path),
            backup=str(backup_path)
        )
        
        return backup_path
    
    async def _calculate_checksum(self, file_path: Path) -> str:
        """Calculate SHA-256 checksum of a file.
        
        Args:
            file_path: File to checksum
            
        Returns:
            Hexadecimal checksum string
        """
        sha256_hash = hashlib.sha256()
        
        async with aiofiles.open(file_path, 'rb') as f:
            while chunk := await f.read(8192):
                sha256_hash.update(chunk)
        
        return sha256_hash.hexdigest()