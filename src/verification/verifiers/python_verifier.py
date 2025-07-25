"""
Python compiler verifier implementation.

This module provides verification capabilities for Python code including
syntax checking, type checking with mypy, and linting.
"""

import ast
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from src.verification.interfaces import VerificationContext, VerificationResult
from src.verification.models import LanguageType, VerificationStage, VerificationStatus
from src.verification.verifiers.compiler_verifier import CompilerVerifier


class PythonCompilerVerifier(CompilerVerifier):
    """Python-specific compiler verifier."""
    
    def __init__(self, config: Dict[str, Any] = None):
        """Initialize the Python compiler verifier.
        
        Args:
            config: Configuration dictionary for the verifier
        """
        super().__init__(config)
        
        # Python-specific configuration
        self.python_version = self.config.get("python_version", f"{sys.version_info.major}.{sys.version_info.minor}")
        self.enable_mypy = self.config.get("enable_mypy", True)
        self.mypy_config_file = self.config.get("mypy_config_file", None)
        self.strict_mypy = self.config.get("strict_mypy", False)
        
        # AST compilation settings
        self.compile_mode = self.config.get("compile_mode", "exec")  # exec, eval, single
        self.optimize_level = self.config.get("optimize_level", -1)  # -1, 0, 1, 2
    
    @property
    def supported_languages(self) -> Set[LanguageType]:
        """Return supported languages."""
        return {LanguageType.PYTHON}
    
    async def check_syntax(self, file_path: Path, context: VerificationContext) -> VerificationResult:
        """
        Check Python syntax using AST parsing.
        
        Args:
            file_path: Path to the Python file
            context: Verification context
            
        Returns:
            VerificationResult with syntax check results
        """
        started_at = datetime.utcnow()
        
        try:
            # Read the file content
            with open(file_path, 'r', encoding='utf-8') as f:
                source_code = f.read()
            
            # Parse file info
            file_info = self._parse_file_info(file_path)
            
            # Try to parse the AST
            try:
                parsed_ast = ast.parse(source_code, filename=str(file_path), mode=self.compile_mode)
                
                # Try to compile the AST
                try:
                    compile(parsed_ast, str(file_path), self.compile_mode, optimize=self.optimize_level)
                    
                    # Syntax is valid
                    completed_at = datetime.utcnow()
                    execution_time = (completed_at - started_at).total_seconds()
                    
                    # Analyze AST for additional metrics
                    ast_metrics = self._analyze_ast(parsed_ast, source_code)
                    
                    return VerificationResult(
                        success=True,
                        status=VerificationStatus.SUCCESS,
                        stage=VerificationStage.SYNTAX,
                        language=LanguageType.PYTHON,
                        started_at=started_at,
                        completed_at=completed_at,
                        execution_time=execution_time,
                        output=f"Python syntax is valid ({file_info.get('line_count', 0)} lines)",
                        metrics={
                            **file_info,
                            **ast_metrics,
                            "python_version": self.python_version,
                            "compile_mode": self.compile_mode
                        },
                        line_count=file_info.get('line_count'),
                        file_size=file_info.get('file_size'),
                        config={"python_version": self.python_version, "optimize_level": self.optimize_level}
                    )
                    
                except SyntaxError as e:
                    # Compilation failed
                    return self._create_syntax_error_result(e, started_at, file_info, "compilation")
                    
            except SyntaxError as e:
                # AST parsing failed
                return self._create_syntax_error_result(e, started_at, file_info, "parsing")
                
        except UnicodeDecodeError as e:
            return VerificationResult(
                success=False,
                status=VerificationStatus.ERROR,
                stage=VerificationStage.SYNTAX,
                language=LanguageType.PYTHON,
                started_at=started_at,
                completed_at=datetime.utcnow(),
                error_message=f"Unicode decode error: {str(e)}",
                error_details={"encoding_error": str(e), "file_path": str(file_path)}
            )
        except Exception as e:
            return VerificationResult(
                success=False,
                status=VerificationStatus.ERROR,
                stage=VerificationStage.SYNTAX,
                language=LanguageType.PYTHON,
                started_at=started_at,
                completed_at=datetime.utcnow(),
                error_message=f"Unexpected error during syntax check: {str(e)}",
                error_details={"exception": str(e), "type": type(e).__name__}
            )
    
    async def check_types(self, file_path: Path, context: VerificationContext) -> VerificationResult:
        """
        Check Python types using mypy.
        
        Args:
            file_path: Path to the Python file
            context: Verification context
            
        Returns:
            VerificationResult with type check results
        """
        started_at = datetime.utcnow()
        
        if not self.enable_mypy:
            return VerificationResult(
                success=True,
                status=VerificationStatus.SKIPPED,
                stage=VerificationStage.TYPE_CHECK,
                language=LanguageType.PYTHON,
                started_at=started_at,
                completed_at=datetime.utcnow(),
                output="Type checking disabled in configuration"
            )
        
        try:
            # Check if mypy is available
            if not await self._is_mypy_available():
                return VerificationResult(
                    success=True,
                    status=VerificationStatus.SKIPPED,
                    stage=VerificationStage.TYPE_CHECK,
                    language=LanguageType.PYTHON,
                    started_at=started_at,
                    completed_at=datetime.utcnow(),
                    output="mypy not available, skipping type check",
                    warnings=["mypy not installed or not in PATH"]
                )
            
            # Build mypy command
            mypy_command = ["mypy"]
            
            if self.strict_mypy:
                mypy_command.append("--strict")
            
            if self.mypy_config_file:
                mypy_command.extend(["--config-file", str(self.mypy_config_file)])
            
            # Add additional mypy options from config
            mypy_options = self.config.get("mypy_options", [])
            mypy_command.extend(mypy_options)
            
            # Add the file to check
            mypy_command.append(str(file_path))
            
            # Run mypy
            result = await self._run_command(
                mypy_command,
                working_dir=context.working_directory or context.project_root,
                timeout=self.config.get("mypy_timeout", 60)
            )
            
            completed_at = datetime.utcnow()
            
            # Parse mypy output
            success = result["returncode"] == 0
            status = VerificationStatus.SUCCESS if success else VerificationStatus.FAILED
            
            # Extract warnings and errors from mypy output
            mypy_issues = self._parse_mypy_output(result["stderr"] + result["stdout"])
            
            return VerificationResult(
                success=success,
                status=status,
                stage=VerificationStage.TYPE_CHECK,
                language=LanguageType.PYTHON,
                started_at=started_at,
                completed_at=completed_at,
                execution_time=result["execution_time"],
                output=result["stdout"] if success else "",
                error_message=result["stderr"] if not success else "",
                error_details={
                    "mypy_issues": mypy_issues,
                    "command": result["command"],
                    "returncode": result["returncode"]
                },
                warnings=[issue["message"] for issue in mypy_issues if issue["severity"] == "warning"],
                metrics={
                    "issues_count": len(mypy_issues),
                    "errors_count": len([i for i in mypy_issues if i["severity"] == "error"]),
                    "warnings_count": len([i for i in mypy_issues if i["severity"] == "warning"]),
                    "mypy_version": await self._get_mypy_version()
                },
                config={
                    "mypy_command": " ".join(mypy_command),
                    "strict_mode": self.strict_mypy,
                    "config_file": str(self.mypy_config_file) if self.mypy_config_file else None
                }
            )
            
        except Exception as e:
            return VerificationResult(
                success=False,
                status=VerificationStatus.ERROR,
                stage=VerificationStage.TYPE_CHECK,
                language=LanguageType.PYTHON,
                started_at=started_at,
                completed_at=datetime.utcnow(),
                error_message=f"Type checking error: {str(e)}",
                error_details={"exception": str(e), "type": type(e).__name__}
            )
    
    async def is_available(self) -> bool:
        """Check if Python compiler verifier is available."""
        try:
            # Check if we can import ast (should always be available)
            import ast
            
            # Check Python version compatibility
            if sys.version_info < (3, 7):
                self.logger.warning(f"Python version {sys.version_info} may not be fully supported")
            
            return True
        except Exception as e:
            self.logger.error(f"Python compiler verifier not available: {str(e)}")
            return False
    
    def _create_syntax_error_result(
        self, 
        syntax_error: SyntaxError, 
        started_at: datetime,
        file_info: Dict[str, Any],
        stage: str
    ) -> VerificationResult:
        """Create a VerificationResult for syntax errors."""
        return VerificationResult(
            success=False,
            status=VerificationStatus.FAILED,
            stage=VerificationStage.SYNTAX,
            language=LanguageType.PYTHON,
            started_at=started_at,
            completed_at=datetime.utcnow(),
            error_message=f"Python syntax error: {syntax_error.msg}",
            error_details={
                "syntax_error": {
                    "message": syntax_error.msg,
                    "filename": syntax_error.filename,
                    "line_number": syntax_error.lineno,
                    "column": syntax_error.offset,
                    "text": syntax_error.text,
                    "stage": stage
                }
            },
            metrics=file_info,
            line_count=file_info.get('line_count'),
            file_size=file_info.get('file_size')
        )
    
    def _analyze_ast(self, ast_node: ast.AST, source_code: str) -> Dict[str, Any]:
        """Analyze the AST to extract metrics."""
        try:
            metrics = {
                "functions": 0,
                "classes": 0,
                "imports": 0,
                "complexity_estimate": 0
            }
            
            for node in ast.walk(ast_node):
                if isinstance(node, ast.FunctionDef):
                    metrics["functions"] += 1
                elif isinstance(node, ast.ClassDef):
                    metrics["classes"] += 1
                elif isinstance(node, (ast.Import, ast.ImportFrom)):
                    metrics["imports"] += 1
                elif isinstance(node, (ast.If, ast.For, ast.While, ast.Try)):
                    metrics["complexity_estimate"] += 1
            
            return metrics
        except Exception as e:
            self.logger.warning(f"Failed to analyze AST: {str(e)}")
            return {"ast_analysis_error": str(e)}
    
    async def _is_mypy_available(self) -> bool:
        """Check if mypy is available."""
        try:
            result = await self._run_command(["mypy", "--version"], timeout=10)
            return result["returncode"] == 0
        except Exception:
            return False
    
    async def _get_mypy_version(self) -> str:
        """Get mypy version."""
        try:
            result = await self._run_command(["mypy", "--version"], timeout=10)
            if result["returncode"] == 0:
                return result["stdout"].strip()
            return "unknown"
        except Exception:
            return "unknown"
    
    def _parse_mypy_output(self, output: str) -> List[Dict[str, Any]]:
        """Parse mypy output to extract issues."""
        issues = []
        
        for line in output.splitlines():
            line = line.strip()
            if not line:
                continue
            
            # Parse mypy output format: filename:line:column: severity: message
            parts = line.split(":", 4)
            if len(parts) >= 4:
                try:
                    filename = parts[0]
                    line_no = int(parts[1]) if parts[1].isdigit() else 0
                    column = int(parts[2]) if parts[2].isdigit() else 0
                    
                    # Determine severity and message
                    rest = ":".join(parts[3:])
                    if "error:" in rest:
                        severity = "error"
                        message = rest.split("error:", 1)[-1].strip()
                    elif "warning:" in rest:
                        severity = "warning"
                        message = rest.split("warning:", 1)[-1].strip()
                    else:
                        severity = "info"
                        message = rest.strip()
                    
                    issues.append({
                        "filename": filename,
                        "line": line_no,
                        "column": column,
                        "severity": severity,
                        "message": message,
                        "raw_line": line
                    })
                except (ValueError, IndexError):
                    # Couldn't parse this line, treat as general message
                    issues.append({
                        "filename": "",
                        "line": 0,
                        "column": 0,
                        "severity": "info",
                        "message": line,
                        "raw_line": line
                    })
        
        return issues