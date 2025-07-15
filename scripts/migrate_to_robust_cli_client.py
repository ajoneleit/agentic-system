#!/usr/bin/env python3
"""Migration script to update imports to use the robust Claude CLI client.

This script updates all Python files to use the new robust implementation
of the Claude CLI client that fixes the "argument too long" error.
"""

import os
import re
from pathlib import Path
import shutil
from datetime import datetime


def backup_file(file_path: Path) -> Path:
    """Create a backup of the file before modification."""
    backup_path = file_path.with_suffix(f"{file_path.suffix}.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
    shutil.copy2(file_path, backup_path)
    return backup_path


def update_imports_in_file(file_path: Path, dry_run: bool = False) -> bool:
    """Update imports in a single file.
    
    Returns True if changes were made, False otherwise.
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        original_content = content
        
        # Pattern to match various import styles
        patterns = [
            # from src.clients.claude_cli_client import ClaudeCLIClient
            (r'from\s+src\.clients\.claude_cli_client\s+import\s+ClaudeCLIClient',
             'from src.clients.claude_cli_client_robust import ClaudeCLIClient'),
            
            # from src.clients.claude_cli_client import *
            (r'from\s+src\.clients\.claude_cli_client\s+import\s+\*',
             'from src.clients.claude_cli_client_robust import *'),
            
            # import src.clients.claude_cli_client
            (r'import\s+src\.clients\.claude_cli_client\b',
             'import src.clients.claude_cli_client_robust as claude_cli_client'),
            
            # from .claude_cli_client import ClaudeCLIClient (relative import)
            (r'from\s+\.claude_cli_client\s+import\s+ClaudeCLIClient',
             'from .claude_cli_client_robust import ClaudeCLIClient'),
        ]
        
        for pattern, replacement in patterns:
            content = re.sub(pattern, replacement, content)
        
        if content != original_content:
            if not dry_run:
                # Create backup
                backup_path = backup_file(file_path)
                print(f"  Backed up to: {backup_path}")
                
                # Write updated content
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(content)
            
            return True
        
        return False
        
    except Exception as e:
        print(f"  Error processing {file_path}: {e}")
        return False


def find_python_files(root_dir: Path) -> list[Path]:
    """Find all Python files in the project."""
    python_files = []
    
    # Directories to skip
    skip_dirs = {
        '.git', '__pycache__', '.pytest_cache', 'htmlcov', 
        'venv', '.venv', 'node_modules', '.tox', 'dist', 'build'
    }
    
    for path in root_dir.rglob('*.py'):
        # Skip if in ignored directory
        if any(skip_dir in path.parts for skip_dir in skip_dirs):
            continue
        
        # Skip backup files
        if '.backup_' in str(path):
            continue
        
        # Skip the robust client itself and its tests
        if path.name in ['claude_cli_client_robust.py', 'test_claude_cli_client_robust.py']:
            continue
        
        python_files.append(path)
    
    return python_files


def main():
    """Main migration function."""
    print("Claude CLI Client Migration Script")
    print("==================================")
    print()
    
    # Get project root (parent of scripts directory)
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    
    print(f"Project root: {project_root}")
    print()
    
    # Find all Python files
    print("Scanning for Python files...")
    python_files = find_python_files(project_root)
    print(f"Found {len(python_files)} Python files")
    print()
    
    # Check for files that need updating
    files_to_update = []
    print("Checking files for claude_cli_client imports...")
    
    for file_path in python_files:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        if 'claude_cli_client' in content and 'claude_cli_client_robust' not in content:
            files_to_update.append(file_path)
    
    if not files_to_update:
        print("No files need updating!")
        return
    
    print(f"\nFound {len(files_to_update)} files that need updating:")
    for file_path in files_to_update:
        print(f"  - {file_path.relative_to(project_root)}")
    
    print()
    
    # Ask for confirmation
    response = input("Do you want to proceed with the migration? (yes/no): ").strip().lower()
    if response not in ['yes', 'y']:
        print("Migration cancelled.")
        return
    
    print("\nPerforming migration...")
    updated_count = 0
    
    for file_path in files_to_update:
        print(f"\nUpdating: {file_path.relative_to(project_root)}")
        if update_imports_in_file(file_path):
            updated_count += 1
            print("  ✓ Updated successfully")
        else:
            print("  ✗ No changes made")
    
    print(f"\nMigration complete! Updated {updated_count} files.")
    
    if updated_count > 0:
        print("\nNext steps:")
        print("1. Review the changes")
        print("2. Run tests to ensure everything works: pytest tests/")
        print("3. If issues arise, backups were created for each modified file")
        print("\nTo use the new client in new code, import it as:")
        print("  from src.clients.claude_cli_client_robust import ClaudeCLIClient")


if __name__ == "__main__":
    main()