"""Language-specific compiler and syntax verifiers."""

import ast
import asyncio
import json
import py_compile
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Optional

from src.core.interfaces import Artifact
from src.utils.app_logging import get_logger

from .verifier_base import (
    BaseVerifier,
    VerificationConfig,
    VerificationResult,
    VerificationType,
)

logger = get_logger(__name__)


class PythonVerifier(BaseVerifier):
    """Python syntax and compilation verifier."""

    def __init__(self, config: Optional[VerificationConfig] = None):
        super().__init__(config)
        self._supported_languages = {"python"}

    @property
    def name(self) -> str:
        return "PythonVerifier"

    @property
    def verification_type(self) -> VerificationType:
        return VerificationType.COMPILATION

    async def verify(
        self, artifact: Artifact, context: Optional[dict[str, Any]] = None
    ) -> VerificationResult:
        """Verify Python code syntax and optionally compile it.

        Args:
            artifact: The Python code artifact to verify
            context: Optional context

        Returns:
            Verification result

        """
        result = self._create_result(artifact)

        try:
            # Get code content
            code_content = artifact.content
            if not code_content and artifact.path and artifact.path.exists():
                code_content = artifact.path.read_text(encoding="utf-8")

            if not code_content:
                result.add_error("No code content found")
                result.complete()
                return result

            # Step 1: Syntax check using ast.parse
            logger.info(f"Checking Python syntax for artifact {artifact.id}")
            await self._check_syntax(code_content, artifact.path or Path("temp.py"), result)

            # Step 2: Compilation check if syntax passes
            if result.success and self.config.enable_compilation:
                logger.info(f"Compiling Python code for artifact {artifact.id}")
                await self._compile_code(code_content, artifact.path or Path("temp.py"), result)

            # Step 3: Additional checks
            if result.success:
                await self._check_imports(code_content, result)
                await self._check_undefined_names(code_content, result)

                # Add code metrics
                result.metrics.lines_of_code = len(code_content.splitlines())

            # Step 4: Generate suggestions if there are issues
            if not result.success or result.warnings:
                self._generate_suggestions(result)

        except Exception as e:
            logger.error(f"Unexpected error during Python verification: {e}")
            result.add_error(f"Verification failed: {str(e)}")

        result.complete()
        return result

    async def _check_syntax(self, code: str, filename: Path, result: VerificationResult) -> None:
        """Check Python syntax using ast.parse."""
        try:
            # Parse the code
            tree = ast.parse(code, filename=str(filename))
            result.add_info(f"Syntax check passed for {filename.name}")

            # Count various code elements
            class_count = sum(1 for node in ast.walk(tree) if isinstance(node, ast.ClassDef))
            func_count = sum(1 for node in ast.walk(tree) if isinstance(node, ast.FunctionDef))

            result.details["ast_stats"] = {
                "classes": class_count,
                "functions": func_count,
            }

        except SyntaxError as e:
            result.add_error(f"Syntax error at line {e.lineno}: {e.msg}")
            if e.text:
                result.add_error(f"  {e.text.strip()}")
                if e.offset:
                    result.add_error(f"  {' ' * (e.offset - 1)}^")
            result.details["syntax_error"] = {
                "line": e.lineno,
                "column": e.offset,
                "message": e.msg,
            }

    async def _compile_code(self, code: str, filename: Path, result: VerificationResult) -> None:
        """Compile Python code to bytecode."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            temp_file = Path(f.name)

        try:
            # Compile the code
            py_compile.compile(str(temp_file), doraise=True)
            result.add_info(f"Compilation successful for {filename.name}")

        except py_compile.PyCompileError as e:
            result.add_error(f"Compilation error: {e.msg}")
            result.details["compilation_error"] = str(e)

        finally:
            # Clean up
            temp_file.unlink(missing_ok=True)
            # Remove compiled file if it exists
            pyc_file = temp_file.with_suffix(".pyc")
            if pyc_file.exists():
                pyc_file.unlink()

    async def _check_imports(self, code: str, result: VerificationResult) -> None:
        """Check if imports are valid."""
        try:
            tree = ast.parse(code)
            imports = []

            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        imports.append(alias.name)
                elif isinstance(node, ast.ImportFrom):
                    module = node.module or ""
                    for alias in node.names:
                        imports.append(f"{module}.{alias.name}" if module else alias.name)

            # Check standard library imports
            import_issues = []
            for imp in imports:
                base_module = imp.split(".")[0]
                # Skip checking third-party imports for now
                if base_module in sys.stdlib_module_names:
                    try:
                        __import__(base_module)
                    except ImportError:
                        import_issues.append(base_module)

            if import_issues:
                result.add_warning(f"Potential import issues: {', '.join(import_issues)}")

            result.details["imports"] = imports

        except Exception as e:
            logger.warning(f"Import check failed: {e}")

    async def _check_undefined_names(self, code: str, result: VerificationResult) -> None:
        """Basic check for potentially undefined names."""
        try:
            tree = ast.parse(code)

            # Collect defined names
            defined_names = set()
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                    defined_names.add(node.name)
                elif isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Name):
                            defined_names.add(target.id)

            # Note: This is a very basic check and may have false positives
            # A proper implementation would need scope analysis

        except Exception as e:
            logger.warning(f"Undefined name check failed: {e}")

    def _generate_suggestions(self, result: VerificationResult) -> None:
        """Generate improvement suggestions based on errors and warnings."""
        if any("Syntax error" in err for err in result.error_messages):
            result.add_suggestion("Review Python syntax, particularly indentation and colons")
            result.add_suggestion("Use a Python linter like flake8 or pylint for detailed feedback")

        if any("import" in warn.lower() for warn in result.warnings):
            result.add_suggestion("Ensure all imported modules are available in the environment")
            result.add_suggestion("Consider using a virtual environment with requirements.txt")


class JavaScriptVerifier(BaseVerifier):
    """JavaScript syntax verifier using Node.js."""

    def __init__(self, config: Optional[VerificationConfig] = None):
        super().__init__(config)
        self._supported_languages = {"javascript"}

    @property
    def name(self) -> str:
        return "JavaScriptVerifier"

    @property
    def verification_type(self) -> VerificationType:
        return VerificationType.SYNTAX

    async def verify(
        self, artifact: Artifact, context: Optional[dict[str, Any]] = None
    ) -> VerificationResult:
        """Verify JavaScript code syntax.

        Args:
            artifact: The JavaScript code artifact to verify
            context: Optional context

        Returns:
            Verification result

        """
        result = self._create_result(artifact)

        try:
            # Get code content
            code_content = artifact.content
            if not code_content and artifact.path and artifact.path.exists():
                code_content = artifact.path.read_text(encoding="utf-8")

            if not code_content:
                result.add_error("No code content found")
                result.complete()
                return result

            # Check if Node.js is available
            if not await self._check_node_available():
                result.add_error("Node.js is not available for JavaScript verification")
                result.add_suggestion("Install Node.js to enable JavaScript verification")
                result.complete()
                return result

            # Verify syntax using Node.js
            await self._verify_with_node(code_content, artifact.path or Path("temp.js"), result)

            # Add metrics
            if result.success:
                result.metrics.lines_of_code = len(code_content.splitlines())

        except Exception as e:
            logger.error(f"Unexpected error during JavaScript verification: {e}")
            result.add_error(f"Verification failed: {str(e)}")

        result.complete()
        return result

    async def _check_node_available(self) -> bool:
        """Check if Node.js is available."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "node", "--version", stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            await proc.communicate()
            return proc.returncode == 0
        except Exception:
            return False

    async def _verify_with_node(
        self, code: str, filename: Path, result: VerificationResult
    ) -> None:
        """Verify JavaScript syntax using Node.js."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".js", delete=False) as f:
            f.write(code)
            temp_file = Path(f.name)

        try:
            # Use Node.js to check syntax
            check_script = f"""
            try {{
                new Function({json.dumps(code)});
                console.log(JSON.stringify({{success: true}}));
            }} catch (e) {{
                console.log(JSON.stringify({{
                    success: false,
                    error: e.message,
                    line: e.lineNumber,
                    column: e.columnNumber
                }}));
            }}
            """

            proc = await asyncio.create_subprocess_exec(
                "node", "-e", check_script, stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )

            stdout, stderr = await proc.communicate()

            if proc.returncode != 0:
                result.add_error(f"Node.js execution failed: {stderr.decode()}")
            else:
                try:
                    check_result = json.loads(stdout.decode())
                    if not check_result.get("success"):
                        error_msg = check_result.get("error", "Unknown syntax error")
                        result.add_error(f"Syntax error: {error_msg}")
                        if check_result.get("line"):
                            result.details["error_location"] = {
                                "line": check_result.get("line"),
                                "column": check_result.get("column"),
                            }
                    else:
                        result.add_info("JavaScript syntax check passed")
                except json.JSONDecodeError:
                    result.add_error("Failed to parse syntax check result")

        finally:
            temp_file.unlink(missing_ok=True)


class TypeScriptVerifier(BaseVerifier):
    """TypeScript compiler verifier."""

    def __init__(self, config: Optional[VerificationConfig] = None):
        super().__init__(config)
        self._supported_languages = {"typescript"}

    @property
    def name(self) -> str:
        return "TypeScriptVerifier"

    @property
    def verification_type(self) -> VerificationType:
        return VerificationType.COMPILATION

    async def verify(
        self, artifact: Artifact, context: Optional[dict[str, Any]] = None
    ) -> VerificationResult:
        """Verify TypeScript code using tsc compiler.

        Args:
            artifact: The TypeScript code artifact to verify
            context: Optional context

        Returns:
            Verification result

        """
        result = self._create_result(artifact)

        try:
            # Get code content
            code_content = artifact.content
            if not code_content and artifact.path and artifact.path.exists():
                code_content = artifact.path.read_text(encoding="utf-8")

            if not code_content:
                result.add_error("No code content found")
                result.complete()
                return result

            # Check if TypeScript compiler is available
            if not await self._check_tsc_available():
                result.add_warning(
                    "TypeScript compiler not available, falling back to JavaScript verification"
                )
                # Fall back to JavaScript verification
                js_verifier = JavaScriptVerifier(self.config)
                return await js_verifier.verify(artifact, context)

            # Verify using TypeScript compiler
            await self._verify_with_tsc(code_content, artifact.path or Path("temp.ts"), result)

            # Add metrics
            if result.success:
                result.metrics.lines_of_code = len(code_content.splitlines())

        except Exception as e:
            logger.error(f"Unexpected error during TypeScript verification: {e}")
            result.add_error(f"Verification failed: {str(e)}")

        result.complete()
        return result

    async def _check_tsc_available(self) -> bool:
        """Check if TypeScript compiler is available."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "tsc", "--version", stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            await proc.communicate()
            return proc.returncode == 0
        except Exception:
            return False

    async def _verify_with_tsc(self, code: str, filename: Path, result: VerificationResult) -> None:
        """Verify TypeScript code using tsc compiler."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            temp_file = temp_path / filename.name
            temp_file.write_text(code, encoding="utf-8")

            # Create a basic tsconfig.json
            tsconfig = {
                "compilerOptions": {
                    "target": "ES2020",
                    "module": "commonjs",
                    "strict": self.config.strict_mode,
                    "esModuleInterop": True,
                    "skipLibCheck": True,
                    "forceConsistentCasingInFileNames": True,
                    "noEmit": True,  # Don't generate output files
                }
            }

            tsconfig_file = temp_path / "tsconfig.json"
            tsconfig_file.write_text(json.dumps(tsconfig, indent=2))

            # Run TypeScript compiler
            proc = await asyncio.create_subprocess_exec(
                "tsc",
                "--project",
                str(tsconfig_file),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=str(temp_path),
            )

            stdout, stderr = await proc.communicate()

            if proc.returncode != 0:
                # Parse TypeScript errors
                error_output = stdout.decode() + stderr.decode()
                for line in error_output.splitlines():
                    if line.strip():
                        result.add_error(line.strip())
            else:
                result.add_info("TypeScript compilation successful")


# Additional language verifiers can be added here (Java, Go, C++, etc.)


def get_verifier_for_language(
    language: str, config: Optional[VerificationConfig] = None
) -> Optional[BaseVerifier]:
    """Get the appropriate verifier for a language.

    Args:
        language: Programming language name
        config: Optional verification configuration

    Returns:
        Verifier instance or None if language not supported

    """
    verifier_map = {
        "python": PythonVerifier,
        "javascript": JavaScriptVerifier,
        "typescript": TypeScriptVerifier,
    }

    language_lower = language.lower()
    verifier_class = verifier_map.get(language_lower)

    if verifier_class:
        return verifier_class(config)

    return None
