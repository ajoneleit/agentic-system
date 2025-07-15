"""
Workspace indexing system for efficient file discovery and metadata caching.

This module provides a high-performance workspace indexing solution that:
- Builds a complete file index with a single directory walk
- Supports efficient file lookups by extension, path, or pattern
- Provides thread-safe operations with asyncio support
- Caches file metadata to avoid repeated filesystem calls
- Handles large workspaces efficiently (target: 1000 files in <500ms)
"""

import asyncio
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Callable, Any
from collections import defaultdict
import threading
import logging
import mimetypes
import stat

logger = logging.getLogger(__name__)


@dataclass
class FileInfo:
    """Information about a file in the workspace."""
    relative_path: str
    absolute_path: Path
    size: int
    modified_time: float
    extension: str
    is_binary: bool
    is_symlink: bool = False
    is_hidden: bool = False
    
    @property
    def name(self) -> str:
        """Get the file name without path."""
        return self.absolute_path.name
    
    @property
    def stem(self) -> str:
        """Get the file name without extension."""
        return self.absolute_path.stem
    
    def __hash__(self):
        return hash(self.relative_path)


class WorkspaceIndex:
    """
    High-performance workspace file indexing system.
    
    Provides efficient file discovery and metadata caching with thread-safe operations.
    Designed to handle large workspaces with thousands of files efficiently.
    """
    
    # Common binary file extensions to detect
    BINARY_EXTENSIONS = {
        '.pyc', '.pyo', '.so', '.dll', '.dylib', '.exe', '.bin',
        '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.ico', '.webp',
        '.mp3', '.mp4', '.avi', '.mov', '.wav', '.flac',
        '.zip', '.tar', '.gz', '.bz2', '.rar', '.7z',
        '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
        '.db', '.sqlite', '.sqlite3'
    }
    
    # Default ignore patterns
    DEFAULT_IGNORE_PATTERNS = {
        '__pycache__', '.git', '.svn', '.hg', '.bzr',
        'node_modules', 'venv', 'env', '.env', '.venv',
        '*.pyc', '*.pyo', '.DS_Store', 'Thumbs.db',
        '.pytest_cache', '.mypy_cache', '.coverage',
        'dist', 'build', '*.egg-info'
    }
    
    def __init__(
        self,
        root_path: Path,
        ignore_patterns: Optional[Set[str]] = None,
        follow_symlinks: bool = False,
        include_hidden: bool = False,
        max_file_size: Optional[int] = None  # in bytes
    ):
        """
        Initialize the workspace index.
        
        Args:
            root_path: Root directory to index
            ignore_patterns: Set of patterns to ignore (glob-style)
            follow_symlinks: Whether to follow symbolic links
            include_hidden: Whether to include hidden files/directories
            max_file_size: Maximum file size to index (in bytes)
        """
        self._root = Path(root_path).resolve()
        self._index: Dict[str, FileInfo] = {}
        self._extension_map: Dict[str, Set[str]] = defaultdict(set)
        self._directory_map: Dict[str, Set[str]] = defaultdict(set)
        self._lock = threading.RLock()  # Reentrant lock for thread safety
        self._async_lock = asyncio.Lock()
        self._last_index_time: Optional[float] = None
        self._index_duration: Optional[float] = None
        
        # Configuration
        self.ignore_patterns = ignore_patterns or self.DEFAULT_IGNORE_PATTERNS.copy()
        self.follow_symlinks = follow_symlinks
        self.include_hidden = include_hidden
        self.max_file_size = max_file_size
        
        # Statistics
        self._stats = {
            'total_files': 0,
            'total_size': 0,
            'binary_files': 0,
            'text_files': 0,
            'symlinks': 0,
            'skipped_files': 0
        }
    
    def _should_ignore(self, path: Path) -> bool:
        """Check if a path should be ignored based on patterns."""
        name = path.name
        
        # Check hidden files
        if not self.include_hidden and name.startswith('.'):
            return True
        
        # Check ignore patterns
        for pattern in self.ignore_patterns:
            if '*' in pattern:
                # Simple glob pattern matching
                import fnmatch
                if fnmatch.fnmatch(name, pattern):
                    return True
            elif name == pattern or pattern in str(path):
                return True
        
        return False
    
    def _is_binary(self, file_path: Path, extension: str) -> bool:
        """Detect if a file is binary."""
        # Check by extension first (fast)
        if extension.lower() in self.BINARY_EXTENSIONS:
            return True
        
        # Use mimetypes as a secondary check
        mime_type, _ = mimetypes.guess_type(str(file_path))
        if mime_type:
            return not mime_type.startswith('text/')
        
        # For unknown types, sample the file content
        try:
            with open(file_path, 'rb') as f:
                chunk = f.read(512)
                return b'\0' in chunk
        except:
            return True  # Assume binary if we can't read
    
    def _process_file(self, file_path: Path) -> Optional[FileInfo]:
        """Process a single file and create FileInfo."""
        try:
            stat_info = file_path.stat(follow_symlinks=self.follow_symlinks)
            
            # Skip if file is too large
            if self.max_file_size and stat_info.st_size > self.max_file_size:
                self._stats['skipped_files'] += 1
                return None
            
            # Calculate relative path
            try:
                relative_path = file_path.relative_to(self._root)
            except ValueError:
                # Handle case where file is outside root (e.g., symlink)
                relative_path = file_path
            
            extension = file_path.suffix
            is_symlink = file_path.is_symlink()
            is_binary = self._is_binary(file_path, extension)
            
            file_info = FileInfo(
                relative_path=str(relative_path),
                absolute_path=file_path,
                size=stat_info.st_size,
                modified_time=stat_info.st_mtime,
                extension=extension,
                is_binary=is_binary,
                is_symlink=is_symlink,
                is_hidden=file_path.name.startswith('.')
            )
            
            # Update statistics
            self._stats['total_files'] += 1
            self._stats['total_size'] += stat_info.st_size
            if is_binary:
                self._stats['binary_files'] += 1
            else:
                self._stats['text_files'] += 1
            if is_symlink:
                self._stats['symlinks'] += 1
            
            return file_info
            
        except (OSError, IOError) as e:
            logger.debug(f"Could not process file {file_path}: {e}")
            self._stats['skipped_files'] += 1
            return None
    
    def build_index(self) -> None:
        """Build the complete file index synchronously."""
        start_time = time.time()
        
        with self._lock:
            # Clear existing index
            self._index.clear()
            self._extension_map.clear()
            self._directory_map.clear()
            self._stats = {
                'total_files': 0,
                'total_size': 0,
                'binary_files': 0,
                'text_files': 0,
                'symlinks': 0,
                'skipped_files': 0
            }
            
            # Walk directory tree
            for root, dirs, files in os.walk(self._root, followlinks=self.follow_symlinks):
                root_path = Path(root)
                
                # Filter directories
                dirs[:] = [d for d in dirs if not self._should_ignore(root_path / d)]
                
                # Process files in this directory
                for file_name in files:
                    file_path = root_path / file_name
                    
                    if self._should_ignore(file_path):
                        continue
                    
                    file_info = self._process_file(file_path)
                    if file_info:
                        # Add to main index
                        self._index[file_info.relative_path] = file_info
                        
                        # Add to extension map
                        if file_info.extension:
                            self._extension_map[file_info.extension].add(file_info.relative_path)
                        
                        # Add to directory map
                        dir_path = str(Path(file_info.relative_path).parent)
                        self._directory_map[dir_path].add(file_info.relative_path)
            
            self._last_index_time = time.time()
            self._index_duration = self._last_index_time - start_time
            
            logger.info(
                f"Indexed {self._stats['total_files']} files in {self._index_duration:.2f}s "
                f"({self._stats['total_files'] / self._index_duration:.0f} files/sec)"
            )
    
    async def build_index_async(self) -> None:
        """Build the file index asynchronously."""
        async with self._async_lock:
            # Run the synchronous build_index in a thread pool
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self.build_index)
    
    def get_file(self, relative_path: str) -> Optional[FileInfo]:
        """Get file info by relative path."""
        with self._lock:
            return self._index.get(relative_path)
    
    def get_files_by_extension(self, ext: str) -> List[FileInfo]:
        """Get all files with a specific extension."""
        if not ext.startswith('.'):
            ext = f'.{ext}'
        
        with self._lock:
            relative_paths = self._extension_map.get(ext, set())
            return [self._index[path] for path in relative_paths if path in self._index]
    
    def get_files_in_directory(self, directory: str) -> List[FileInfo]:
        """Get all files in a specific directory (non-recursive)."""
        with self._lock:
            relative_paths = self._directory_map.get(directory, set())
            return [self._index[path] for path in relative_paths if path in self._index]
    
    def find_files(
        self,
        pattern: Optional[str] = None,
        extension: Optional[str] = None,
        is_binary: Optional[bool] = None,
        min_size: Optional[int] = None,
        max_size: Optional[int] = None,
        modified_after: Optional[float] = None,
        filter_func: Optional[Callable[[FileInfo], bool]] = None
    ) -> List[FileInfo]:
        """
        Find files matching specific criteria.
        
        Args:
            pattern: Glob pattern to match file names
            extension: File extension to filter by
            is_binary: Filter by binary/text files
            min_size: Minimum file size in bytes
            max_size: Maximum file size in bytes
            modified_after: Unix timestamp - only files modified after this time
            filter_func: Custom filter function
        
        Returns:
            List of matching FileInfo objects
        """
        import fnmatch
        
        with self._lock:
            results = []
            
            for file_info in self._index.values():
                # Apply filters
                if pattern and not fnmatch.fnmatch(file_info.name, pattern):
                    continue
                
                if extension:
                    if not extension.startswith('.'):
                        extension = f'.{extension}'
                    if file_info.extension != extension:
                        continue
                
                if is_binary is not None and file_info.is_binary != is_binary:
                    continue
                
                if min_size is not None and file_info.size < min_size:
                    continue
                
                if max_size is not None and file_info.size > max_size:
                    continue
                
                if modified_after is not None and file_info.modified_time < modified_after:
                    continue
                
                if filter_func and not filter_func(file_info):
                    continue
                
                results.append(file_info)
            
            return results
    
    def get_all_files(self) -> List[FileInfo]:
        """Get all indexed files."""
        with self._lock:
            return list(self._index.values())
    
    def get_text_files(self) -> List[FileInfo]:
        """Get all text (non-binary) files."""
        return self.find_files(is_binary=False)
    
    def get_binary_files(self) -> List[FileInfo]:
        """Get all binary files."""
        return self.find_files(is_binary=True)
    
    def refresh(self) -> None:
        """Refresh the entire index."""
        self.build_index()
    
    async def refresh_async(self) -> None:
        """Refresh the index asynchronously."""
        await self.build_index_async()
    
    def update_file(self, file_path: Path) -> Optional[FileInfo]:
        """Update a single file in the index."""
        if not file_path.exists():
            # Remove from index if file no longer exists
            relative_path = str(file_path.relative_to(self._root))
            with self._lock:
                if relative_path in self._index:
                    old_info = self._index[relative_path]
                    del self._index[relative_path]
                    
                    # Remove from maps
                    if old_info.extension:
                        self._extension_map[old_info.extension].discard(relative_path)
                    
                    dir_path = str(Path(relative_path).parent)
                    self._directory_map[dir_path].discard(relative_path)
                    
                    # Update stats
                    self._stats['total_files'] -= 1
                    self._stats['total_size'] -= old_info.size
            return None
        
        # Process and update file
        file_info = self._process_file(file_path)
        if file_info:
            with self._lock:
                # Remove old entry if exists
                if file_info.relative_path in self._index:
                    old_info = self._index[file_info.relative_path]
                    self._stats['total_size'] -= old_info.size
                    self._stats['total_files'] -= 1
                
                # Add new entry
                self._index[file_info.relative_path] = file_info
                
                # Update maps
                if file_info.extension:
                    self._extension_map[file_info.extension].add(file_info.relative_path)
                
                dir_path = str(Path(file_info.relative_path).parent)
                self._directory_map[dir_path].add(file_info.relative_path)
        
        return file_info
    
    @property
    def stats(self) -> Dict[str, Any]:
        """Get index statistics."""
        with self._lock:
            return {
                **self._stats,
                'last_index_time': self._last_index_time,
                'index_duration': self._index_duration,
                'unique_extensions': len(self._extension_map),
                'directories': len(self._directory_map)
            }
    
    @property
    def root_path(self) -> Path:
        """Get the root path of the indexed workspace."""
        return self._root
    
    def __len__(self) -> int:
        """Get the number of indexed files."""
        with self._lock:
            return len(self._index)
    
    def __contains__(self, relative_path: str) -> bool:
        """Check if a file is in the index."""
        with self._lock:
            return relative_path in self._index
    
    def __repr__(self) -> str:
        """String representation of the index."""
        return (
            f"WorkspaceIndex(root={self._root}, "
            f"files={len(self)}, "
            f"size={self._stats['total_size'] / (1024**2):.1f}MB)"
        )


def index_workspace(
    root_path: Path,
    ignore_patterns: Optional[Set[str]] = None,
    follow_symlinks: bool = False,
    include_hidden: bool = False,
    max_file_size: Optional[int] = None
) -> WorkspaceIndex:
    """
    Convenience function to create and build a workspace index.
    
    Args:
        root_path: Root directory to index
        ignore_patterns: Set of patterns to ignore
        follow_symlinks: Whether to follow symbolic links
        include_hidden: Whether to include hidden files
        max_file_size: Maximum file size to index (in bytes)
    
    Returns:
        Built WorkspaceIndex instance
    """
    index = WorkspaceIndex(
        root_path=root_path,
        ignore_patterns=ignore_patterns,
        follow_symlinks=follow_symlinks,
        include_hidden=include_hidden,
        max_file_size=max_file_size
    )
    index.build_index()
    return index