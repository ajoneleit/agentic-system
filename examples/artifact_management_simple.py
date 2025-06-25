"""Simple demonstration of the Artifact Management System.

This is a streamlined demo that shows the basic features quickly.
"""

import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from src.core.artifact_manager import ArtifactManager
from src.core.interfaces import Artifact, ArtifactType


async def main():
    """Run a simple artifact management demonstration."""
    print("=== Simple Artifact Management Demo ===\n")
    
    # Initialize artifact manager
    storage_path = Path("./demo_artifacts")
    manager = ArtifactManager(
        storage_path=storage_path,
        max_memory_cache_size=10,
        enable_compression=True
    )
    await manager.initialize()
    print("✓ Artifact manager initialized")
    
    # Create a sample artifact
    artifact = Artifact(
        id=uuid4(),
        name="hello.py",
        type=ArtifactType.SOURCE_CODE,
        content='def hello():\n    return "Hello, World!"',
        language="python",
        path=Path("src/hello.py"),
        version=1,
        created_at=datetime.now(timezone.utc),
        modified_at=datetime.now(timezone.utc),
        task_id=uuid4(),
        agent_id=uuid4(),
        tags={"demo", "hello"}
    )
    
    # Store the artifact
    stored = await manager.store_artifact(artifact)
    print(f"✓ Stored artifact: {stored.name} (ID: {stored.id})")
    print(f"  - Size: {stored.size_bytes} bytes")
    print(f"  - Checksum: {stored.checksum[:16]}...")
    
    # Retrieve the artifact
    retrieved = await manager.get_artifact(artifact.id)
    print(f"\n✓ Retrieved artifact: {retrieved.name}")
    print(f"  - Content matches: {retrieved.content == artifact.content}")
    
    # Update the artifact
    updated = await manager.update_artifact(
        artifact.id,
        'def hello():\n    return "Hello, World!"\n\ndef goodbye():\n    return "Goodbye!"',
        reason="Added goodbye function"
    )
    print(f"\n✓ Updated artifact to version {updated.version}")
    
    # Get all versions
    versions = await manager.get_artifact_versions(artifact.id)
    print(f"\n✓ Available versions: {[v.version for v in versions]}")
    
    # Get metrics
    metrics = await manager.get_metrics()
    print(f"\n✓ Metrics:")
    print(f"  - Total artifacts: {metrics['total_artifacts']}")
    print(f"  - Cache hit rate: {metrics['cache_hit_rate']:.0%}")
    
    # Clean up
    import shutil
    if storage_path.exists():
        shutil.rmtree(storage_path)
    print("\n✓ Demo completed and cleaned up!")


if __name__ == "__main__":
    asyncio.run(main())