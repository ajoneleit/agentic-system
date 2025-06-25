"""Demonstration of the Artifact Management System.

This example shows how to use the artifact manager to store, retrieve,
version, and manage code artifacts.
"""

import asyncio
import sys
from datetime import datetime
from pathlib import Path
from uuid import uuid4

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from src.core.artifact_manager import ArtifactManager
from src.core.dependency_tracker import DependencyTracker
from src.core.interfaces import Artifact, ArtifactType
from src.core.versioning import VersionControl
from src.utils.file_manager import FileManager


async def demonstrate_artifact_storage():
    """Demonstrate basic artifact storage and retrieval."""
    print("\n=== Artifact Storage Demo ===")
    
    # Initialize artifact manager
    storage_path = Path("./projects/demo_artifacts")
    manager = ArtifactManager(
        storage_path=storage_path,
        max_memory_cache_size=50,
        enable_compression=True
    )
    await manager.initialize()
    
    # Create a sample artifact
    artifact = Artifact(
        id=uuid4(),
        name="calculator.py",
        type=ArtifactType.SOURCE_CODE,
        content="""def add(a: int, b: int) -> int:
    \"\"\"Add two numbers.\"\"\"
    return a + b

def subtract(a: int, b: int) -> int:
    \"\"\"Subtract b from a.\"\"\"
    return a - b

def multiply(a: int, b: int) -> int:
    \"\"\"Multiply two numbers.\"\"\"
    return a * b

def divide(a: float, b: float) -> float:
    \"\"\"Divide a by b.\"\"\"
    if b == 0:
        raise ValueError("Cannot divide by zero")
    return a / b
""",
        language="python",
        path=Path("src/calculator.py"),
        version=1,
        created_at=datetime.utcnow(),
        modified_at=datetime.utcnow(),
        task_id=uuid4(),
        agent_id=uuid4(),
        tags={"math", "calculator", "basic"}
    )
    
    # Store the artifact
    stored = await manager.store_artifact(artifact)
    print(f"Stored artifact: {stored.name} (v{stored.version})")
    print(f"  ID: {stored.id}")
    print(f"  Size: {stored.size_bytes} bytes")
    print(f"  Checksum: {stored.checksum[:16]}...")
    
    # Retrieve the artifact
    retrieved = await manager.get_artifact(artifact.id)
    print(f"\nRetrieved artifact: {retrieved.name}")
    print(f"  Content matches: {retrieved.content == artifact.content}")
    
    # Update the artifact (creates new version)
    updated_content = artifact.content + """
def power(a: float, b: float) -> float:
    \"\"\"Raise a to the power of b.\"\"\"
    return a ** b
"""
    
    updated = await manager.update_artifact(
        artifact.id,
        updated_content,
        reason="Added power function"
    )
    print(f"\nUpdated artifact: {updated.name} (v{updated.version})")
    
    # Get all versions
    versions = await manager.get_artifact_versions(artifact.id)
    print(f"\nAvailable versions: {[v.version for v in versions]}")
    
    # Search for artifacts
    results = await manager.search_artifacts(
        tags={"calculator"},
        language="python"
    )
    print(f"\nSearch results: {len(results)} artifacts found")
    
    # Get metrics
    metrics = await manager.get_metrics()
    print(f"\nMetrics:")
    print(f"  Total artifacts: {metrics['total_artifacts']}")
    print(f"  Cache hit rate: {metrics['cache_hit_rate']:.2%}")
    
    return manager, artifact


async def demonstrate_versioning():
    """Demonstrate version control features."""
    print("\n\n=== Version Control Demo ===")
    
    # Initialize version control
    vc = VersionControl()
    
    # Create initial version
    artifact1 = Artifact(
        id=uuid4(),
        name="feature.js",
        type=ArtifactType.SOURCE_CODE,
        content="""function greet(name) {
    return `Hello, ${name}!`;
}

module.exports = { greet };
""",
        language="javascript",
        version=1,
        created_at=datetime.utcnow(),
        modified_at=datetime.utcnow(),
        task_id=uuid4(),
        agent_id=uuid4()
    )
    
    # Create version
    v1 = await vc.create_version(
        artifact1,
        author_agent_id=uuid4(),
        commit_message="Initial implementation of greet function"
    )
    print(f"Created version: {v1.version_id}")
    print(f"  Branch: {v1.branch_name}")
    print(f"  Message: {v1.commit_message}")
    
    # Create a feature branch
    feature_branch = await vc.create_branch(
        "feature/add-farewell",
        base_version_id=artifact1.id,
        created_by=uuid4()
    )
    print(f"\nCreated branch: {feature_branch.name}")
    
    # Create new version on feature branch
    artifact2 = artifact1.increment_version()
    artifact2.content = """function greet(name) {
    return `Hello, ${name}!`;
}

function farewell(name) {
    return `Goodbye, ${name}!`;
}

module.exports = { greet, farewell };
"""
    
    v2 = await vc.create_version(
        artifact2,
        author_agent_id=uuid4(),
        commit_message="Add farewell function",
        branch_name="feature/add-farewell"
    )
    print(f"\nCreated version on feature branch:")
    print(f"  Lines added: {v2.lines_added}")
    print(f"  Lines removed: {v2.lines_removed}")
    
    # Generate diff
    diff = await vc.generate_diff(artifact1, artifact2)
    print(f"\nDiff summary:")
    print(f"  Additions: {len(diff.additions)} lines")
    print(f"  Deletions: {len(diff.deletions)} lines")
    
    # Get version history
    history = await vc.get_version_history(artifact2.id)
    print(f"\nVersion history: {len(history)} versions")
    
    # List branches
    branches = await vc.get_branches()
    print(f"\nActive branches: {[b.name for b in branches]}")


async def demonstrate_dependencies():
    """Demonstrate dependency tracking."""
    print("\n\n=== Dependency Tracking Demo ===")
    
    # Initialize dependency tracker
    tracker = DependencyTracker()
    
    # Create artifacts with dependencies
    main_artifact = Artifact(
        id=uuid4(),
        name="main.py",
        type=ArtifactType.SOURCE_CODE,
        content="""import calculator
import utils
from config import Settings

def main():
    result = calculator.add(5, 3)
    utils.log_result(result)
    
if __name__ == "__main__":
    main()
""",
        language="python",
        version=1,
        created_at=datetime.utcnow(),
        modified_at=datetime.utcnow(),
        task_id=uuid4(),
        agent_id=uuid4()
    )
    
    calc_artifact = Artifact(
        id=uuid4(),
        name="calculator.py",
        type=ArtifactType.SOURCE_CODE,
        content="""def add(a, b):
    return a + b
""",
        language="python",
        version=1,
        created_at=datetime.utcnow(),
        modified_at=datetime.utcnow(),
        task_id=uuid4(),
        agent_id=uuid4()
    )
    
    # Create known artifacts mapping
    known_artifacts = {
        "calculator": calc_artifact.id,
        "utils": uuid4(),  # Placeholder
        "config": uuid4()   # Placeholder
    }
    
    # Analyze dependencies
    dependencies = await tracker.analyze_artifact(main_artifact, known_artifacts)
    print(f"Found {len(dependencies)} dependencies in {main_artifact.name}")
    
    # Add manual dependency
    await tracker.add_dependency(
        main_artifact.id,
        calc_artifact.id,
        dependency_type="import",
        metadata={"critical": True}
    )
    
    # Get dependencies
    deps = await tracker.get_dependencies(main_artifact.id)
    print(f"\nDirect dependencies: {len(deps)}")
    
    # Get dependents
    dependents = await tracker.get_dependents(calc_artifact.id)
    print(f"Artifacts depending on calculator.py: {len(dependents)}")
    
    # Impact analysis
    impact = await tracker.get_impact_analysis(calc_artifact.id)
    print(f"\nImpact of changing calculator.py:")
    print(f"  Direct impact: {impact['direct_impact']} artifacts")
    print(f"  Risk level: {impact['risk_level']}")
    
    # Get build order
    build_order = await tracker.get_build_order()
    print(f"\nBuild order: {len(build_order)} artifacts")


async def demonstrate_file_operations():
    """Demonstrate safe file operations."""
    print("\n\n=== File Operations Demo ===")
    
    # Initialize file manager
    base_path = Path("./demo_workspace")
    file_manager = FileManager(
        base_path=base_path,
        max_file_size=5 * 1024 * 1024,  # 5MB
        enable_backup=True
    )
    
    # Write a file
    content = """# Demo Project

This is a demonstration of the file management system.

## Features
- Safe file operations
- Atomic writes
- Automatic backups
- Path traversal protection
"""
    
    file_path = await file_manager.write_file(
        "README.md",
        content,
        create_dirs=True
    )
    print(f"Created file: {file_path}")
    
    # Read the file
    read_content = await file_manager.read_file("README.md")
    print(f"Read {len(read_content)} characters")
    
    # Get file info
    info = await file_manager.get_file_info("README.md")
    print(f"\nFile info:")
    print(f"  Size: {info['size']} bytes")
    print(f"  Modified: {info['modified']}")
    print(f"  Checksum: {info['checksum'][:16]}...")
    
    # List files
    files = await file_manager.list_files(".", pattern="*.md")
    print(f"\nFound {len(files)} markdown files")
    
    # Copy file
    await file_manager.copy_file("README.md", "README.backup.md")
    print("Created backup copy")
    
    # Clean up old files (dry run)
    old_files = await file_manager.cleanup_old_files(
        days=30,
        dry_run=True
    )
    print(f"\nWould clean up {len(old_files)} old files")


async def main():
    """Run all demonstrations."""
    print("Artifact Management System Demonstration")
    print("=" * 50)
    
    try:
        # Run demonstrations
        manager, artifact = await demonstrate_artifact_storage()
        await demonstrate_versioning()
        await demonstrate_dependencies()
        await demonstrate_file_operations()
        
        print("\n\nDemonstration completed successfully!")
        
    except Exception as e:
        print(f"\nError during demonstration: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        # Clean up demo directories
        import shutil
        for path in ["./demo_artifacts", "./demo_workspace"]:
            if Path(path).exists():
                shutil.rmtree(path)
                print(f"Cleaned up {path}")


if __name__ == "__main__":
    asyncio.run(main())