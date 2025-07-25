#!/usr/bin/env python3
"""Generate Test Count Badge - Auto-generates test count badge for README
Integrates seamlessly with existing CI workflow and quality gates.
"""

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, Tuple

def count_tests_by_type(project_root: Path) -> Dict[str, int]:
    """Count different types of tests in the project."""
    counts = {
        'unit': 0,
        'integration': 0,
        'performance': 0,
        'validation': 0,
        'ui': 0,
        'total': 0
    }
    
    # Search patterns for test functions
    test_patterns = [
        r'def test_[a-zA-Z_][a-zA-Z0-9_]*\s*\(',
        r'async def test_[a-zA-Z_][a-zA-Z0-9_]*\s*\(',
        r'@pytest\.mark\.\w+\s*\ndef test_',
    ]
    
    # Count tests by directory
    test_dirs = {
        'unit': project_root / 'tests' / 'unit',
        'integration': project_root / 'tests' / 'integration', 
        'performance': project_root / 'tests' / 'performance',
        'validation': project_root / 'tests' / 'validation',
        'ui': project_root / 'tests' / 'ui',
        'root': project_root / 'tests'
    }
    
    for category, test_dir in test_dirs.items():
        if not test_dir.exists():
            continue
            
        # Find all Python test files
        if category == 'root':
            # Only count files directly in tests/ not in subdirectories
            test_files = [f for f in test_dir.glob('test_*.py') if f.is_file()]
            test_files.extend([f for f in test_dir.glob('*_test.py') if f.is_file()])
        else:
            test_files = list(test_dir.rglob('test_*.py'))
            test_files.extend(list(test_dir.rglob('*_test.py')))
        
        category_count = 0
        for test_file in test_files:
            try:
                content = test_file.read_text(encoding='utf-8')
                for pattern in test_patterns:
                    matches = re.findall(pattern, content, re.MULTILINE)
                    category_count += len(matches)
            except (UnicodeDecodeError, FileNotFoundError):
                continue
        
        if category == 'root':
            counts['other'] = category_count
        else:
            counts[category] = category_count
        counts['total'] += category_count
    
    return counts

def count_rust_tests(project_root: Path) -> int:
    """Count Rust tests in the zero-engine workspace."""
    rust_dir = project_root / 'zero-engine'
    if not rust_dir.exists():
        return 0
    
    try:
        # Use cargo test --no-run to just count tests without running
        result = subprocess.run(
            ['cargo', 'test', '--no-run', '--message-format=json'],
            cwd=rust_dir,
            capture_output=True,
            text=True,
            timeout=60
        )
        
        # Parse JSON output to count tests
        test_count = 0
        for line in result.stdout.split('\n'):
            if line.strip():
                try:
                    data = json.loads(line)
                    if data.get('reason') == 'compiler-artifact' and 'test' in data.get('target', {}).get('kind', []):
                        # This is a test binary - count #[test] functions in source
                        for src_file in data.get('filenames', []):
                            if src_file.endswith('.rs'):
                                try:
                                    with open(src_file, 'r') as f:
                                        content = f.read()
                                        test_count += len(re.findall(r'#\[test\]', content))
                                except (FileNotFoundError, UnicodeDecodeError):
                                    continue
                except json.JSONDecodeError:
                    continue
        
        return test_count
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError):
        return 0

def generate_badge_url(test_count: int, rust_count: int = 0) -> str:
    """Generate shields.io badge URL for test count."""
    total_tests = test_count + rust_count
    
    # Determine color based on test count
    if total_tests >= 300:
        color = 'brightgreen'
    elif total_tests >= 200:
        color = 'green'
    elif total_tests >= 100:
        color = 'yellow'
    elif total_tests >= 50:
        color = 'orange'
    else:
        color = 'red'
    
    # Format the count with suffix
    if total_tests >= 1000:
        count_str = f"{total_tests//1000}k+"
    else:
        count_str = str(total_tests)
    
    if rust_count > 0:
        label = f"tests-{count_str}%20(Python%20{test_count}%2B%20Rust%20{rust_count})"
    else:
        label = f"tests-{count_str}"
    
    return f"https://img.shields.io/badge/{label}-{color}?style=flat-square"

def update_readme_badge(project_root: Path, badge_url: str, test_counts: Dict[str, int]) -> bool:
    """Update README.md with the test count badge."""
    readme_path = project_root / 'README.md'
    
    if not readme_path.exists():
        print(f"⚠️ README.md not found at {readme_path}")
        return False
    
    try:
        content = readme_path.read_text(encoding='utf-8')
        
        # Badge markdown
        badge_markdown = f"![Tests]({badge_url})"
        
        # Look for existing test badge and replace it
        test_badge_pattern = r'\!\[Tests\]\(https://img\.shields\.io/badge/tests-[^)]+\)'
        
        if re.search(test_badge_pattern, content):
            # Replace existing badge
            new_content = re.sub(test_badge_pattern, badge_markdown, content)
            print("🔄 Updated existing test count badge")
        else:
            # Add badge after first line (title) or at beginning
            lines = content.split('\n')
            if len(lines) > 0 and lines[0].startswith('# '):
                # Insert after title
                lines.insert(1, '')
                lines.insert(2, badge_markdown)
                lines.insert(3, '')
            else:
                # Insert at beginning
                lines.insert(0, badge_markdown)
                lines.insert(1, '')
            new_content = '\n'.join(lines)
            print("➕ Added new test count badge")
        
        readme_path.write_text(new_content, encoding='utf-8')
        
        # Show breakdown
        print(f"📊 Test Breakdown:")
        for category, count in test_counts.items():
            if count > 0 and category != 'total':
                print(f"   • {category.title()}: {count}")
        
        return True
        
    except (UnicodeDecodeError, FileNotFoundError, PermissionError) as e:
        print(f"❌ Error updating README.md: {e}")
        return False

def save_test_metrics(project_root: Path, test_counts: Dict[str, int], rust_count: int) -> None:
    """Save test metrics to reports directory for tracking."""
    reports_dir = project_root / 'reports'
    reports_dir.mkdir(exist_ok=True)
    
    metrics = {
        'timestamp': subprocess.check_output(['date', '-u', '+%Y-%m-%dT%H:%M:%SZ']).decode().strip(),
        'python_tests': test_counts,
        'rust_tests': rust_count,
        'total_tests': test_counts['total'] + rust_count,
        'badge_url': generate_badge_url(test_counts['total'], rust_count)
    }
    
    metrics_file = reports_dir / 'test_metrics.json'
    with open(metrics_file, 'w') as f:
        json.dump(metrics, f, indent=2)
    
    print(f"💾 Test metrics saved to {metrics_file}")

def main():
    """Main entry point."""
    project_root = Path.cwd()
    
    print("🧪 GENERATING TEST COUNT BADGE")
    print("=" * 50)
    
    # Count Python tests
    print("🐍 Counting Python tests...")
    test_counts = count_tests_by_type(project_root)
    
    # Count Rust tests
    print("🦀 Counting Rust tests...")
    rust_count = count_rust_tests(project_root)
    
    total_tests = test_counts['total'] + rust_count
    
    print(f"📈 Found {test_counts['total']} Python tests + {rust_count} Rust tests = {total_tests} total tests")
    
    # Generate badge
    badge_url = generate_badge_url(test_counts['total'], rust_count)
    print(f"🏷️ Badge URL: {badge_url}")
    
    # Update README if requested
    if '--update-readme' in sys.argv:
        success = update_readme_badge(project_root, badge_url, test_counts)
        if not success:
            sys.exit(1)
    
    # Save metrics
    save_test_metrics(project_root, test_counts, rust_count)
    
    print()
    print("✅ Test count badge generation complete!")

if __name__ == '__main__':
    main()