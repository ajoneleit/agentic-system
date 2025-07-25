#!/bin/bash
# CI Pipeline Validation Script

set -e  # Exit on any error

echo "🔍 CI PIPELINE VALIDATION SCRIPT"
echo "=================================="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    local status=$1
    local message=$2
    case $status in
        "SUCCESS") echo -e "${GREEN}✅ $message${NC}" ;;
        "FAILURE") echo -e "${RED}❌ $message${NC}" ;;
        "WARNING") echo -e "${YELLOW}⚠️ $message${NC}" ;;
        "INFO") echo -e "${BLUE}ℹ️ $message${NC}" ;;
    esac
}

# Check if we're in a git repository
if ! git rev-parse --is-inside-work-tree > /dev/null 2>&1; then
    print_status "FAILURE" "Not in a git repository"
    exit 1
fi

print_status "SUCCESS" "In git repository"

# Get repository information
REPO_URL=$(git remote get-url origin 2>/dev/null || echo "no-remote")
CURRENT_BRANCH=$(git branch --show-current)
COMMIT_HASH=$(git rev-parse --short HEAD)

print_status "INFO" "Repository: $REPO_URL"
print_status "INFO" "Current branch: $CURRENT_BRANCH"
print_status "INFO" "Current commit: $COMMIT_HASH"

# Check for CI configuration files
echo ""
echo "🔧 Checking CI Configuration..."
CI_CONFIGS=(
    ".github/workflows/ci.yml"
    ".github/workflows/documentation.yml"
    ".github/workflows/main.yml"
    ".github/workflows/test.yml"
)

FOUND_CONFIGS=()
for config in "${CI_CONFIGS[@]}"; do
    if [ -f "$config" ]; then
        FOUND_CONFIGS+=("$config")
        print_status "SUCCESS" "Found CI config: $config"
    fi
done

if [ ${#FOUND_CONFIGS[@]} -eq 0 ]; then
    print_status "FAILURE" "No CI configuration files found"
    echo "Expected files: ${CI_CONFIGS[*]}"
    exit 1
fi

# Check GitHub CLI availability
echo ""
echo "🔧 Checking GitHub CLI..."
if command -v gh &> /dev/null; then
    GH_VERSION=$(gh --version | head -n1)
    print_status "SUCCESS" "GitHub CLI available: $GH_VERSION"
    
    # Check if authenticated
    if gh auth status &> /dev/null; then
        print_status "SUCCESS" "GitHub CLI authenticated"
        GH_AUTHENTICATED=true
    else
        print_status "WARNING" "GitHub CLI not authenticated"
        print_status "INFO" "Run 'gh auth login' to authenticate"
        GH_AUTHENTICATED=false
    fi
else
    print_status "WARNING" "GitHub CLI not available"
    print_status "INFO" "Install GitHub CLI from: https://cli.github.com/"
    GH_AUTHENTICATED=false
fi

# Validate CI configuration syntax
echo ""
echo "🔧 Validating CI Configuration Syntax..."
for config in "${FOUND_CONFIGS[@]}"; do
    if command -v yamllint &> /dev/null; then
        if yamllint "$config" &> /dev/null; then
            print_status "SUCCESS" "$config syntax valid"
        else
            print_status "WARNING" "$config has syntax warnings"
        fi
    else
        # Basic YAML syntax check
        if python3 -c "import yaml; yaml.safe_load(open('$config'))" &> /dev/null; then
            print_status "SUCCESS" "$config syntax valid (basic check)"
        else
            print_status "FAILURE" "$config has syntax errors"
        fi
    fi
done

# Check for required CI components
echo ""
echo "🔧 Checking CI Components..."

# Check for test commands
for config in "${FOUND_CONFIGS[@]}"; do
    if grep -q "pytest\|test" "$config"; then
        print_status "SUCCESS" "$config includes test execution"
    fi
    
    if grep -q "lint\|black\|ruff" "$config"; then
        print_status "SUCCESS" "$config includes code linting"
    fi
    
    if grep -q "coverage" "$config"; then
        print_status "SUCCESS" "$config includes coverage checking"
    fi
    
    if grep -q "quality.*gate\|doc.*valid" "$config"; then
        print_status "SUCCESS" "$config includes quality gates"
    fi
done

# Test CI workflow locally (if possible)
echo ""
echo "🔧 Local CI Validation..."

# Check if we can run basic commands that CI would run
if [ -f "requirements.txt" ]; then
    print_status "INFO" "Found requirements.txt"
    
    # Test pip install (dry run)
    if pip install --dry-run -q -r requirements.txt &> /dev/null; then
        print_status "SUCCESS" "Requirements.txt is installable"
    else
        print_status "WARNING" "Issues with requirements.txt dependencies"
    fi
fi

# Test if health check exists and runs
if [ -f "scripts/health_check.py" ]; then
    print_status "INFO" "Testing health check script..."
    if timeout 30 python scripts/health_check.py &> /dev/null; then
        print_status "SUCCESS" "Health check script runs successfully"
    else
        print_status "WARNING" "Health check script has issues or times out"
    fi
fi

# Test documentation validation
if [ -f "docs/validation/quality_gates.py" ]; then
    print_status "INFO" "Testing quality gates..."
    if timeout 60 python docs/validation/quality_gates.py --pre-commit &> /dev/null; then
        print_status "SUCCESS" "Quality gates validation runs successfully"
    else
        print_status "WARNING" "Quality gates validation fails or times out"
    fi
fi

# GitHub Actions workflow validation
if [ "$GH_AUTHENTICATED" = true ]; then
    echo ""
    echo "🔧 GitHub Actions Workflow Status..."
    
    # Check recent workflow runs
    if gh run list --limit 5 --json status,conclusion,createdAt,name > /tmp/gh_runs.json 2>/dev/null; then
        print_status "SUCCESS" "Retrieved recent workflow runs"
        
        # Parse and display recent runs
        python3 << 'EOF'
import json
import sys
try:
    with open('/tmp/gh_runs.json', 'r') as f:
        runs = json.load(f)
    
    if not runs:
        print("⚠️ No recent workflow runs found")
    else:
        print("📊 Recent workflow runs:")
        for i, run in enumerate(runs[:3], 1):
            status = run.get('status', 'unknown')
            conclusion = run.get('conclusion', 'pending')
            name = run.get('name', 'unnamed')
            created = run.get('createdAt', 'unknown')
            
            if conclusion == 'success':
                emoji = '✅'
            elif conclusion == 'failure':
                emoji = '❌'
            elif status == 'in_progress':
                emoji = '🔄'
            else:
                emoji = '⚠️'
            
            print(f"  {emoji} {name}: {conclusion} ({created[:10]})")
except Exception as e:
    print(f"⚠️ Could not parse workflow runs: {e}")
EOF
    else
        print_status "WARNING" "Could not retrieve workflow runs"
    fi
    
    # Offer to watch current run if available
    echo ""
    print_status "INFO" "To watch live CI run: gh run watch"
    print_status "INFO" "To trigger new run: gh workflow run ci.yml"
    
else
    echo ""
    print_status "INFO" "Manual CI Validation Steps:"
    echo "  1. Push changes to trigger CI"
    echo "  2. Visit GitHub repository → Actions tab"
    echo "  3. Verify all workflows show green ✅ status"
    echo "  4. Check that CI runs complete in reasonable time"
fi

# Fresh clone test recommendation
echo ""
echo "🔧 Fresh Clone Test Instructions..."
print_status "INFO" "To perform comprehensive CI validation:"

cat << 'EOF'

1. FRESH CLONE TEST:
   ```bash
   TEMP_DIR=$(mktemp -d)
   git clone <your-repo-url> "$TEMP_DIR/fresh_clone"
   cd "$TEMP_DIR/fresh_clone"
   # Wait for CI to trigger and complete
   gh run watch  # (if GitHub CLI available)
   ```

2. LOCAL VALIDATION TEST:
   ```bash
   # Install dependencies
   pip install -r requirements.txt
   
   # Run validation suite
   python scripts/validate_system.py
   
   # Run quality gates
   python docs/validation/quality_gates.py --pre-commit
   ```

3. CI ARTIFACTS CHECK:
   - Go to GitHub repository → Actions → Latest run
   - Check "Artifacts" section contains:
     ✅ coverage.xml
     ✅ pylint.json
     ✅ quality reports
EOF

# Summary
echo ""
echo "📋 CI VALIDATION SUMMARY"
echo "========================"

if [ ${#FOUND_CONFIGS[@]} -gt 0 ]; then
    print_status "SUCCESS" "CI configuration files present: ${#FOUND_CONFIGS[@]}"
else
    print_status "FAILURE" "No CI configuration found"
fi

if [ "$GH_AUTHENTICATED" = true ]; then
    print_status "SUCCESS" "GitHub CLI ready for CI monitoring"
else
    print_status "WARNING" "GitHub CLI not ready - manual verification required"
fi

print_status "INFO" "For complete validation, run: python scripts/validate_system.py"

echo ""
print_status "INFO" "CI Pipeline validation complete"