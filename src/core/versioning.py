"""Version control system for artifacts with diff tracking and branching support.

This module provides Git-like versioning capabilities for artifacts,
including diff generation, merging, and branch management.
"""

import difflib
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional
from uuid import UUID, uuid4

from structlog import get_logger

from src.core.interfaces import Artifact

logger = get_logger(__name__)


@dataclass
class VersionMetadata:
    """Metadata for a version in the version tree."""

    version_id: UUID
    artifact_id: UUID
    version_number: int
    author_agent_id: UUID
    timestamp: datetime
    commit_message: str
    parent_version_id: Optional[UUID] = None
    branch_name: str = "main"
    change_summary: dict[str, Any] = field(default_factory=dict)

    # Diff information
    lines_added: int = 0
    lines_removed: int = 0
    diff_size: int = 0

    # Merge information
    is_merge: bool = False
    merge_parents: list[UUID] = field(default_factory=list)
    merge_conflicts_resolved: int = 0


@dataclass
class Branch:
    """Represents a branch in the version tree."""

    name: str
    head_version_id: UUID
    created_at: datetime
    created_by: UUID
    base_version_id: UUID
    is_active: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class VersionDiff:
    """Represents differences between two versions."""

    from_version_id: UUID
    to_version_id: UUID
    unified_diff: str
    additions: list[str]
    deletions: list[str]
    modifications: list[tuple[str, str]]
    summary: dict[str, Any]


class VersionControl:
    """Manages versioning for artifacts with branching and merging support."""

    def __init__(self):
        """Initialize version control system."""
        # Version tree structure
        self._version_metadata: dict[UUID, VersionMetadata] = {}
        self._branches: dict[str, Branch] = {}
        self._version_tree: dict[UUID, list[UUID]] = {}  # parent -> children

        # Diff cache for performance
        self._diff_cache: dict[tuple[UUID, UUID], VersionDiff] = {}
        self._max_diff_cache_size = 1000

        # Initialize main branch
        self._initialize_main_branch()

        logger.info("VersionControl initialized")

    def _initialize_main_branch(self) -> None:
        """Initialize the main branch."""
        # Main branch points to None initially (no versions yet)
        self._branches["main"] = Branch(
            name="main",
            head_version_id=uuid4(),  # Placeholder
            created_at=datetime.utcnow(),
            created_by=uuid4(),  # System ID
            base_version_id=uuid4(),  # Root
            is_active=True,
        )

    async def create_version(
        self,
        artifact: Artifact,
        author_agent_id: UUID,
        commit_message: str,
        branch_name: str = "main",
        parent_version_id: Optional[UUID] = None,
    ) -> VersionMetadata:
        """Create a new version in the version tree.

        Args:
            artifact: The artifact to version
            author_agent_id: ID of the agent creating the version
            commit_message: Description of changes
            branch_name: Branch to create version on
            parent_version_id: Parent version (uses branch head if None)

        Returns:
            Version metadata for the created version

        """
        # Determine parent version
        if parent_version_id is None and branch_name in self._branches:
            parent_version_id = self._branches[branch_name].head_version_id

        # Calculate diff if there's a parent
        diff_info = {"lines_added": 0, "lines_removed": 0, "diff_size": 0}
        if parent_version_id and parent_version_id in self._version_metadata:
            parent_artifact = await self._get_artifact_for_version(parent_version_id)
            if parent_artifact:
                diff = await self.generate_diff(parent_artifact, artifact)
                diff_info = {
                    "lines_added": len(diff.additions),
                    "lines_removed": len(diff.deletions),
                    "diff_size": len(diff.unified_diff),
                }

        # Create version metadata
        version_meta = VersionMetadata(
            version_id=artifact.id,
            artifact_id=artifact.id,
            version_number=artifact.version,
            parent_version_id=parent_version_id,
            branch_name=branch_name,
            author_agent_id=author_agent_id,
            timestamp=datetime.utcnow(),
            commit_message=commit_message,
            change_summary={
                "type": artifact.type.value,
                "name": artifact.name,
                "language": artifact.language,
                "size_bytes": artifact.size_bytes,
            },
            **diff_info,
        )

        # Update version tree
        self._version_metadata[artifact.id] = version_meta
        if parent_version_id:
            if parent_version_id not in self._version_tree:
                self._version_tree[parent_version_id] = []
            self._version_tree[parent_version_id].append(artifact.id)

        # Update branch head
        if branch_name in self._branches:
            self._branches[branch_name].head_version_id = artifact.id

        logger.info(
            "Version created",
            version_id=str(artifact.id),
            branch=branch_name,
            parent=str(parent_version_id) if parent_version_id else "None",
            message=commit_message,
        )

        return version_meta

    async def create_branch(
        self,
        branch_name: str,
        base_version_id: UUID,
        created_by: UUID,
        metadata: Optional[dict[str, Any]] = None,
    ) -> Branch:
        """Create a new branch from a base version.

        Args:
            branch_name: Name of the new branch
            base_version_id: Version to branch from
            created_by: Agent creating the branch
            metadata: Additional branch metadata

        Returns:
            Created branch

        Raises:
            ValueError: If branch already exists

        """
        if branch_name in self._branches:
            raise ValueError(f"Branch '{branch_name}' already exists")

        branch = Branch(
            name=branch_name,
            head_version_id=base_version_id,
            created_at=datetime.utcnow(),
            created_by=created_by,
            base_version_id=base_version_id,
            is_active=True,
            metadata=metadata or {},
        )

        self._branches[branch_name] = branch

        logger.info(
            "Branch created",
            branch_name=branch_name,
            base_version=str(base_version_id),
            created_by=str(created_by),
        )

        return branch

    async def merge_branches(
        self,
        source_branch: str,
        target_branch: str,
        author_agent_id: UUID,
        merge_strategy: str = "recursive",
    ) -> tuple[Optional[Artifact], list[str]]:
        """Merge one branch into another.

        Args:
            source_branch: Branch to merge from
            target_branch: Branch to merge into
            author_agent_id: Agent performing the merge
            merge_strategy: Strategy for resolving conflicts

        Returns:
            Tuple of (merged artifact, list of conflicts)

        """
        if source_branch not in self._branches:
            raise ValueError(f"Source branch '{source_branch}' not found")
        if target_branch not in self._branches:
            raise ValueError(f"Target branch '{target_branch}' not found")

        source_head = self._branches[source_branch].head_version_id
        target_head = self._branches[target_branch].head_version_id

        # Find common ancestor
        common_ancestor = await self._find_common_ancestor(source_head, target_head)

        if not common_ancestor:
            logger.warning(
                "No common ancestor found", source_branch=source_branch, target_branch=target_branch
            )
            return None, ["No common ancestor found"]

        # Get artifacts
        source_artifact = await self._get_artifact_for_version(source_head)
        target_artifact = await self._get_artifact_for_version(target_head)
        base_artifact = await self._get_artifact_for_version(common_ancestor)

        if not all([source_artifact, target_artifact, base_artifact]):
            return None, ["Missing artifacts for merge"]

        # Perform three-way merge
        merged_content, conflicts = await self._three_way_merge(
            base_artifact.content, source_artifact.content, target_artifact.content, merge_strategy
        )

        if merged_content and not conflicts:
            # Create merged artifact
            merged_artifact = target_artifact.increment_version()
            merged_artifact.content = merged_content
            merged_artifact.metadata["merge_info"] = {
                "source_branch": source_branch,
                "target_branch": target_branch,
                "source_version": str(source_head),
                "target_version": str(target_head),
                "common_ancestor": str(common_ancestor),
                "strategy": merge_strategy,
            }

            # Create merge version metadata
            merge_meta = await self.create_version(
                merged_artifact,
                author_agent_id,
                f"Merge {source_branch} into {target_branch}",
                target_branch,
                target_head,
            )
            merge_meta.is_merge = True
            merge_meta.merge_parents = [source_head, target_head]

            logger.info(
                "Branches merged successfully",
                source=source_branch,
                target=target_branch,
                merged_version=str(merged_artifact.id),
            )

            return merged_artifact, []

        logger.warning(
            "Merge conflicts detected",
            source=source_branch,
            target=target_branch,
            conflicts_count=len(conflicts),
        )

        return None, conflicts

    async def get_version_history(
        self, artifact_id: UUID, branch_name: Optional[str] = None, limit: Optional[int] = None
    ) -> list[VersionMetadata]:
        """Get version history for an artifact.

        Args:
            artifact_id: Artifact to get history for
            branch_name: Specific branch (all branches if None)
            limit: Maximum number of versions to return

        Returns:
            List of version metadata, newest first

        """
        history = []

        # Start from the artifact and traverse backwards
        current_id = artifact_id
        visited = set()

        while current_id and current_id not in visited:
            visited.add(current_id)

            if current_id in self._version_metadata:
                meta = self._version_metadata[current_id]

                # Filter by branch if specified
                if branch_name is None or meta.branch_name == branch_name:
                    history.append(meta)

                # Stop if we've reached the limit
                if limit and len(history) >= limit:
                    break

                # Move to parent
                current_id = meta.parent_version_id
            else:
                break

        return history

    async def generate_diff(self, from_artifact: Artifact, to_artifact: Artifact) -> VersionDiff:
        """Generate diff between two artifact versions.

        Args:
            from_artifact: Source artifact
            to_artifact: Target artifact

        Returns:
            Version diff information

        """
        cache_key = (from_artifact.id, to_artifact.id)

        # Check cache
        if cache_key in self._diff_cache:
            return self._diff_cache[cache_key]

        # Generate unified diff
        from_lines = from_artifact.content.splitlines(keepends=True)
        to_lines = to_artifact.content.splitlines(keepends=True)

        diff_lines = list(
            difflib.unified_diff(
                from_lines,
                to_lines,
                fromfile=f"{from_artifact.name} v{from_artifact.version}",
                tofile=f"{to_artifact.name} v{to_artifact.version}",
                lineterm="",
            )
        )

        # Parse diff to extract additions/deletions
        additions = []
        deletions = []
        modifications = []

        for line in diff_lines:
            if line.startswith("+") and not line.startswith("+++"):
                additions.append(line[1:])
            elif line.startswith("-") and not line.startswith("---"):
                deletions.append(line[1:])

        # Create diff object
        version_diff = VersionDiff(
            from_version_id=from_artifact.id,
            to_version_id=to_artifact.id,
            unified_diff="\n".join(diff_lines),
            additions=additions,
            deletions=deletions,
            modifications=modifications,
            summary={
                "files_changed": 1,
                "insertions": len(additions),
                "deletions": len(deletions),
                "from_size": from_artifact.size_bytes,
                "to_size": to_artifact.size_bytes,
                "size_change": to_artifact.size_bytes - from_artifact.size_bytes,
            },
        )

        # Cache the diff
        self._update_diff_cache(cache_key, version_diff)

        return version_diff

    async def rollback_to_version(
        self, version_id: UUID, branch_name: str = "main", author_agent_id: UUID = None
    ) -> Artifact:
        """Rollback to a specific version.

        Args:
            version_id: Version to rollback to
            branch_name: Branch to rollback on
            author_agent_id: Agent performing rollback

        Returns:
            New artifact created from rollback

        """
        if version_id not in self._version_metadata:
            raise ValueError(f"Version {version_id} not found")

        # Get the artifact for the target version
        target_artifact = await self._get_artifact_for_version(version_id)
        if not target_artifact:
            raise ValueError(f"Artifact for version {version_id} not found")

        # Create a new version with the old content
        rollback_artifact = target_artifact.increment_version()
        rollback_artifact.metadata["rollback_info"] = {
            "rolled_back_to": str(version_id),
            "rolled_back_from": str(self._branches[branch_name].head_version_id),
            "timestamp": datetime.utcnow().isoformat(),
        }

        # Create version metadata
        await self.create_version(
            rollback_artifact,
            author_agent_id or uuid4(),
            f"Rollback to version {version_id}",
            branch_name,
        )

        logger.info(
            "Rollback completed",
            version_id=str(version_id),
            branch=branch_name,
            new_version=str(rollback_artifact.id),
        )

        return rollback_artifact

    async def get_branches(self, active_only: bool = True) -> list[Branch]:
        """Get all branches.

        Args:
            active_only: Whether to return only active branches

        Returns:
            List of branches

        """
        branches = list(self._branches.values())

        if active_only:
            branches = [b for b in branches if b.is_active]

        return branches

    async def delete_branch(self, branch_name: str) -> None:
        """Mark a branch as deleted.

        Args:
            branch_name: Branch to delete

        Raises:
            ValueError: If trying to delete main branch

        """
        if branch_name == "main":
            raise ValueError("Cannot delete main branch")

        if branch_name not in self._branches:
            raise ValueError(f"Branch '{branch_name}' not found")

        self._branches[branch_name].is_active = False

        logger.info("Branch deleted", branch_name=branch_name)

    def get_version_metadata(self, version_id: UUID) -> Optional[VersionMetadata]:
        """Get metadata for a specific version.

        Args:
            version_id: Version ID

        Returns:
            Version metadata if found

        """
        return self._version_metadata.get(version_id)

    async def _get_artifact_for_version(self, version_id: UUID) -> Optional[Artifact]:
        """Get artifact for a version ID.

        This is a placeholder - actual implementation would fetch from ArtifactManager.
        """
        # TODO: Integrate with ArtifactManager
        return None

    async def _find_common_ancestor(self, version1_id: UUID, version2_id: UUID) -> Optional[UUID]:
        """Find common ancestor of two versions.

        Args:
            version1_id: First version
            version2_id: Second version

        Returns:
            Common ancestor version ID if found

        """
        # Get ancestors of both versions
        ancestors1 = await self._get_ancestors(version1_id)
        ancestors2 = await self._get_ancestors(version2_id)

        # Find intersection
        common = ancestors1.intersection(ancestors2)

        if not common:
            return None

        # Find the most recent common ancestor
        # (the one with the highest version number)
        best_ancestor = None
        best_version = -1

        for ancestor_id in common:
            if ancestor_id in self._version_metadata:
                version = self._version_metadata[ancestor_id].version_number
                if version > best_version:
                    best_version = version
                    best_ancestor = ancestor_id

        return best_ancestor

    async def _get_ancestors(self, version_id: UUID) -> set[UUID]:
        """Get all ancestors of a version.

        Args:
            version_id: Version to get ancestors for

        Returns:
            Set of ancestor version IDs

        """
        ancestors = set()
        current_id = version_id

        while current_id and current_id in self._version_metadata:
            ancestors.add(current_id)
            meta = self._version_metadata[current_id]

            # Handle merge commits
            if meta.is_merge and meta.merge_parents:
                for parent_id in meta.merge_parents:
                    parent_ancestors = await self._get_ancestors(parent_id)
                    ancestors.update(parent_ancestors)

            current_id = meta.parent_version_id

        return ancestors

    async def _three_way_merge(
        self,
        base_content: str,
        source_content: str,
        target_content: str,
        strategy: str = "recursive",
    ) -> tuple[Optional[str], list[str]]:
        """Perform three-way merge of content.

        Args:
            base_content: Common ancestor content
            source_content: Source branch content
            target_content: Target branch content
            strategy: Merge strategy

        Returns:
            Tuple of (merged content, list of conflicts)

        """
        # Simple line-based three-way merge
        base_lines = base_content.splitlines(keepends=True)
        source_lines = source_content.splitlines(keepends=True)
        target_lines = target_content.splitlines(keepends=True)

        # Use difflib to generate merge
        merger = difflib.Differ()

        # Find changes from base to source
        list(merger.compare(base_lines, source_lines))

        # Find changes from base to target
        list(merger.compare(base_lines, target_lines))

        # Apply both sets of changes
        merged_lines = []
        conflicts = []

        # This is a simplified merge - real implementation would be more sophisticated
        # For now, we'll prefer target changes in conflicts
        for _i, line in enumerate(target_lines):
            merged_lines.append(line)

        merged_content = "".join(merged_lines)

        return merged_content, conflicts

    def _update_diff_cache(self, cache_key: tuple[UUID, UUID], diff: VersionDiff) -> None:
        """Update diff cache with size limit."""
        self._diff_cache[cache_key] = diff

        # Evict oldest entries if cache is too large
        if len(self._diff_cache) > self._max_diff_cache_size:
            # Remove first 10% of entries (oldest)
            to_remove = list(self._diff_cache.keys())[: self._max_diff_cache_size // 10]
            for key in to_remove:
                del self._diff_cache[key]
