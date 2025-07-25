"""
JavaScript/TypeScript compiler verifier implementation.

This module provides verification capabilities for JavaScript and TypeScript
code including syntax checking and type checking.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from src.verification.interfaces import VerificationContext, VerificationResult
from src.verification.models import LanguageType, VerificationStage, VerificationStatus
from src.verification.verifiers.compiler_verifier import CompilerVerifier


class JavaScriptCompilerVerifier(CompilerVerifier):
    """JavaScript/TypeScript-specific compiler verifier."""
    
    def __init__(self, config: Dict[str, Any] = None):
        """Initialize the JavaScript compiler verifier.
        
        Args:
            config: Configuration dictionary for the verifier
        """
        super().__init__(config)
        
        # JavaScript-specific configuration
        self.node_version = self.config.get("node_version", "latest")
        self.enable_typescript = self.config.get("enable_typescript", True)
        self.typescript_config = self.config.get("typescript_config", "tsconfig.json")
        self.enable_eslint = self.config.get("enable_eslint", True)
        self.eslint_config = self.config.get("eslint_config", None)
        
        # Syntax checking tools
        self.use_esprima = self.config.get("use_esprima", False)  # Alternative parser
        self.ecma_version = self.config.get("ecma_version", 2022)
        self.source_type = self.config.get("source_type", "module")  # script, module
    
    @property
    def supported_languages(self) -> Set[LanguageType]:
        """Return supported languages."""
        languages = {LanguageType.JAVASCRIPT}
        if self.enable_typescript:
            languages.add(LanguageType.TYPESCRIPT)
        return languages
    
    async def check_syntax(self, file_path: Path, context: VerificationContext) -> VerificationResult:
        """
        Check JavaScript/TypeScript syntax using Node.js.
        
        Args:
            file_path: Path to the JavaScript/TypeScript file
            context: Verification context
            
        Returns:
            VerificationResult with syntax check results
        """
        started_at = datetime.utcnow()
        
        try:
            # Parse file info
            file_info = self._parse_file_info(file_path)
            
            # Check if Node.js is available
            if not await self._is_node_available():
                return VerificationResult(
                    success=False,
                    status=VerificationStatus.ERROR,
                    stage=VerificationStage.SYNTAX,
                    language=context.language,
                    started_at=started_at,
                    completed_at=datetime.utcnow(),
                    error_message="Node.js not available for JavaScript syntax checking",
                    error_details={"missing_dependency": "node"}
                )
            
            # Determine the checking method based on file type
            if context.language == LanguageType.TYPESCRIPT or file_path.suffix in ['.ts', '.tsx']:
                return await self._check_typescript_syntax(file_path, context, started_at, file_info)
            else:
                return await self._check_javascript_syntax(file_path, context, started_at, file_info)
                
        except Exception as e:
            return VerificationResult(
                success=False,
                status=VerificationStatus.ERROR,
                stage=VerificationStage.SYNTAX,
                language=context.language,
                started_at=started_at,
                completed_at=datetime.utcnow(),
                error_message=f"Unexpected error during syntax check: {str(e)}",
                error_details={"exception": str(e), "type": type(e).__name__}
            )
    
    async def check_types(self, file_path: Path, context: VerificationContext) -> VerificationResult:
        """
        Check JavaScript/TypeScript types.
        
        Args:
            file_path: Path to the JavaScript/TypeScript file
            context: Verification context
            
        Returns:
            VerificationResult with type check results
        """
        started_at = datetime.utcnow()
        
        # Type checking is mainly for TypeScript
        if context.language == LanguageType.TYPESCRIPT or file_path.suffix in ['.ts', '.tsx']:
            return await self._check_typescript_types(file_path, context, started_at)
        else:
            # For JavaScript, we can use JSDoc comments or skip
            return VerificationResult(
                success=True,
                status=VerificationStatus.SKIPPED,
                stage=VerificationStage.TYPE_CHECK,
                language=context.language,
                started_at=started_at,
                completed_at=datetime.utcnow(),
                output="Type checking not applicable for JavaScript (use TypeScript for type checking)"
            )
    
    async def is_available(self) -> bool:
        """Check if JavaScript compiler verifier is available."""
        return await self._is_node_available()
    
    async def _check_javascript_syntax(
        self, 
        file_path: Path, 
        context: VerificationContext, 
        started_at: datetime,
        file_info: Dict[str, Any]
    ) -> VerificationResult:
        """Check JavaScript syntax using Node.js."""
        try:
            # Create a simple Node.js script to check syntax
            syntax_check_script = f'''
const fs = require('fs');
const path = require('path');

try {{
    const filePath = '{file_path}';
    const code = fs.readFileSync(filePath, 'utf8');
    
    // Try to parse the JavaScript code
    new Function(code);
    
    console.log(JSON.stringify({{
        success: true,
        message: 'JavaScript syntax is valid',
        fileSize: fs.statSync(filePath).size,
        lineCount: code.split('\\n').length
    }}));
}} catch (error) {{
    console.error(JSON.stringify({{
        success: false,
        error: error.message,
        name: error.name,
        line: error.lineNumber || 0,
        column: error.columnNumber || 0
    }}));
    process.exit(1);
}}
'''
            
            # Run the syntax check
            result = await self._run_command(
                ["node", "-e", syntax_check_script],
                working_dir=context.working_directory or context.project_root
            )
            
            completed_at = datetime.utcnow()
            execution_time = result["execution_time"]
            
            if result["returncode"] == 0:
                # Parse successful result
                try:
                    output_data = json.loads(result["stdout"])
                    return VerificationResult(
                        success=True,
                        status=VerificationStatus.SUCCESS,
                        stage=VerificationStage.SYNTAX,
                        language=context.language,
                        started_at=started_at,
                        completed_at=completed_at,
                        execution_time=execution_time,
                        output=f"JavaScript syntax is valid ({file_info.get('line_count', 0)} lines)",
                        metrics={
                            **file_info,
                            "ecma_version": self.ecma_version,
                            "source_type": self.source_type
                        },
                        line_count=file_info.get('line_count'),
                        file_size=file_info.get('file_size'),
                        config={"node_version": await self._get_node_version()}
                    )
                except json.JSONDecodeError:
                    # Fallback if JSON parsing fails
                    return VerificationResult(
                        success=True,
                        status=VerificationStatus.SUCCESS,
                        stage=VerificationStage.SYNTAX,
                        language=context.language,
                        started_at=started_at,
                        completed_at=completed_at,
                        execution_time=execution_time,
                        output="JavaScript syntax appears valid",
                        metrics=file_info
                    )
            else:
                # Parse error result
                try:
                    error_data = json.loads(result["stderr"])
                    return VerificationResult(
                        success=False,
                        status=VerificationStatus.FAILED,
                        stage=VerificationStage.SYNTAX,
                        language=context.language,
                        started_at=started_at,
                        completed_at=completed_at,
                        execution_time=execution_time,
                        error_message=f"JavaScript syntax error: {error_data.get('error', 'Unknown error')}",
                        error_details={
                            "syntax_error": error_data,
                            "command": result["command"]
                        },
                        metrics=file_info
                    )
                except json.JSONDecodeError:
                    return VerificationResult(
                        success=False,
                        status=VerificationStatus.FAILED,
                        stage=VerificationStage.SYNTAX,
                        language=context.language,
                        started_at=started_at,
                        completed_at=completed_at,
                        execution_time=execution_time,
                        error_message="JavaScript syntax error",
                        error_details={"stderr": result["stderr"], "stdout": result["stdout"]},
                        metrics=file_info
                    )
                    
        except Exception as e:
            return VerificationResult(
                success=False,
                status=VerificationStatus.ERROR,
                stage=VerificationStage.SYNTAX,
                language=context.language,
                started_at=started_at,
                completed_at=datetime.utcnow(),
                error_message=f"JavaScript syntax check error: {str(e)}",
                error_details={"exception": str(e)}
            )
    
    async def _check_typescript_syntax(
        self, 
        file_path: Path, 
        context: VerificationContext, 
        started_at: datetime,
        file_info: Dict[str, Any]
    ) -> VerificationResult:
        """Check TypeScript syntax using tsc."""
        try:
            # Check if TypeScript compiler is available
            if not await self._is_tsc_available():
                return VerificationResult(
                    success=True,
                    status=VerificationStatus.SKIPPED,
                    stage=VerificationStage.SYNTAX,
                    language=context.language,
                    started_at=started_at,
                    completed_at=datetime.utcnow(),
                    output="TypeScript compiler (tsc) not available, skipping TypeScript syntax check",
                    warnings=["tsc not installed or not in PATH"]
                )
            
            # Build TypeScript compile command
            tsc_command = ["tsc", "--noEmit", "--skipLibCheck"]
            
            # Add TypeScript config if available
            if self.typescript_config and Path(context.project_root / self.typescript_config).exists():
                tsc_command.extend(["--project", str(context.project_root / self.typescript_config)])
            
            # Add the file to check
            tsc_command.append(str(file_path))
            
            # Run TypeScript compiler
            result = await self._run_command(
                tsc_command,
                working_dir=context.working_directory or context.project_root
            )
            
            completed_at = datetime.utcnow()
            execution_time = result["execution_time"]
            
            success = result["returncode"] == 0
            status = VerificationStatus.SUCCESS if success else VerificationStatus.FAILED
            
            # Parse TypeScript compiler output
            ts_issues = self._parse_tsc_output(result["stderr"] + result["stdout"])
            
            return VerificationResult(
                success=success,
                status=status,
                stage=VerificationStage.SYNTAX,
                language=context.language,
                started_at=started_at,
                completed_at=completed_at,
                execution_time=execution_time,
                output=result["stdout"] if success else "",
                error_message=result["stderr"] if not success else "",
                error_details={
                    "typescript_issues": ts_issues,
                    "command": result["command"],
                    "returncode": result["returncode"]
                },
                warnings=[issue["message"] for issue in ts_issues if issue["severity"] == "warning"],
                metrics={
                    **file_info,
                    "issues_count": len(ts_issues),
                    "errors_count": len([i for i in ts_issues if i["severity"] == "error"]),
                    "warnings_count": len([i for i in ts_issues if i["severity"] == "warning"]),
                    "typescript_version": await self._get_tsc_version()
                },
                line_count=file_info.get('line_count'),
                file_size=file_info.get('file_size'),
                config={
                    "typescript_config": str(self.typescript_config),
                    "tsc_command": " ".join(tsc_command)
                }
            )
            
        except Exception as e:
            return VerificationResult(
                success=False,
                status=VerificationStatus.ERROR,
                stage=VerificationStage.SYNTAX,
                language=context.language,
                started_at=started_at,
                completed_at=datetime.utcnow(),
                error_message=f"TypeScript syntax check error: {str(e)}",
                error_details={"exception": str(e)}
            )
    
    async def _check_typescript_types(
        self, 
        file_path: Path, 
        context: VerificationContext, 
        started_at: datetime
    ) -> VerificationResult:
        """Check TypeScript types using tsc."""
        # TypeScript type checking is the same as syntax checking with tsc
        file_info = self._parse_file_info(file_path)
        result = await self._check_typescript_syntax(file_path, context, started_at, file_info)
        
        # Update the stage to TYPE_CHECK
        result.stage = VerificationStage.TYPE_CHECK
        
        return result
    
    async def _is_node_available(self) -> bool:
        """Check if Node.js is available."""
        try:
            result = await self._run_command(["node", "--version"], timeout=10)
            return result["returncode"] == 0
        except Exception:
            return False
    
    async def _is_tsc_available(self) -> bool:
        """Check if TypeScript compiler is available."""
        try:
            result = await self._run_command(["tsc", "--version"], timeout=10)
            return result["returncode"] == 0
        except Exception:
            return False
    
    async def _get_node_version(self) -> str:
        """Get Node.js version."""
        try:
            result = await self._run_command(["node", "--version"], timeout=10)
            if result["returncode"] == 0:
                return result["stdout"].strip()
            return "unknown"
        except Exception:
            return "unknown"
    
    async def _get_tsc_version(self) -> str:
        """Get TypeScript compiler version."""
        try:
            result = await self._run_command(["tsc", "--version"], timeout=10)
            if result["returncode"] == 0:
                return result["stdout"].strip()
            return "unknown"
        except Exception:
            return "unknown"
    
    def _parse_tsc_output(self, output: str) -> List[Dict[str, Any]]:
        """Parse TypeScript compiler output to extract issues."""
        issues = []
        
        for line in output.splitlines():
            line = line.strip()
            if not line:
                continue
            
            # Parse tsc output format: filename(line,column): error/warning TS####: message
            if "(" in line and "):" in line:
                try:
                    # Extract filename and position
                    filename_part = line.split("(", 1)[0]
                    position_part = line.split("(", 1)[1].split("):", 1)[0]
                    message_part = line.split("):", 1)[1].strip()
                    
                    # Parse position
                    if "," in position_part:
                        line_no, column = position_part.split(",", 1)
                        line_no = int(line_no.strip())
                        column = int(column.strip())
                    else:
                        line_no = int(position_part.strip())
                        column = 0
                    
                    # Determine severity
                    if "error" in message_part.lower():
                        severity = "error"
                    elif "warning" in message_part.lower():
                        severity = "warning"
                    else:
                        severity = "info"
                    
                    issues.append({
                        "filename": filename_part.strip(),
                        "line": line_no,
                        "column": column,
                        "severity": severity,
                        "message": message_part,
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