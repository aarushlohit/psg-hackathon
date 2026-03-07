"""Security scanning service — subprocess wrappers for bandit, pip-audit, semgrep."""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


@dataclass
class SecurityFinding:
    """A single finding from a security scanner."""

    scanner: str
    severity: Severity
    title: str
    file: str = ""
    line: int = 0
    detail: str = ""


@dataclass
class ScanResult:
    """Aggregated result of a scan run."""

    scanner: str
    success: bool
    findings: list[SecurityFinding] = field(default_factory=list)
    error: str = ""
    raw_output: str = ""


# ---- individual scanners ----


class BanditScanner:
    """Wrapper around the bandit Python static analysis tool."""

    name = "bandit"

    @staticmethod
    def available() -> bool:
        return shutil.which("bandit") is not None

    @staticmethod
    def scan(path: str = ".") -> ScanResult:
        if not BanditScanner.available():
            return ScanResult(scanner="bandit", success=False, error="bandit not installed. Run: pip install bandit")
        try:
            proc = subprocess.run(
                ["bandit", "-r", path, "-f", "json", "--quiet"],
                capture_output=True,
                text=True,
                timeout=120,
            )
            raw = proc.stdout
            findings: list[SecurityFinding] = []
            try:
                import json
                data = json.loads(raw)
                for r in data.get("results", []):
                    findings.append(
                        SecurityFinding(
                            scanner="bandit",
                            severity=Severity(r.get("issue_severity", "UNKNOWN").lower()),
                            title=r.get("issue_text", ""),
                            file=r.get("filename", ""),
                            line=r.get("line_number", 0),
                            detail=r.get("test_id", ""),
                        )
                    )
            except (json.JSONDecodeError, KeyError):
                pass
            return ScanResult(scanner="bandit", success=True, findings=findings, raw_output=raw)
        except subprocess.TimeoutExpired:
            return ScanResult(scanner="bandit", success=False, error="bandit scan timed out.")


class PipAuditScanner:
    """Wrapper around pip-audit for dependency vulnerability scanning."""

    name = "pip-audit"

    @staticmethod
    def available() -> bool:
        return shutil.which("pip-audit") is not None

    @staticmethod
    def scan(path: str = ".") -> ScanResult:
        if not PipAuditScanner.available():
            return ScanResult(scanner="pip-audit", success=False, error="pip-audit not installed. Run: pip install pip-audit")
        try:
            proc = subprocess.run(
                ["pip-audit", "--format", "json"],
                capture_output=True,
                text=True,
                timeout=120,
            )
            raw = proc.stdout
            findings: list[SecurityFinding] = []
            try:
                import json
                data = json.loads(raw)
                for vuln in data if isinstance(data, list) else data.get("dependencies", []):
                    for v in vuln.get("vulns", []):
                        findings.append(
                            SecurityFinding(
                                scanner="pip-audit",
                                severity=Severity.HIGH,
                                title=f"{vuln.get('name', '?')} {vuln.get('version', '?')}: {v.get('id', '')}",
                                detail=v.get("description", ""),
                            )
                        )
            except (Exception,):
                pass
            return ScanResult(scanner="pip-audit", success=True, findings=findings, raw_output=raw)
        except subprocess.TimeoutExpired:
            return ScanResult(scanner="pip-audit", success=False, error="pip-audit timed out.")


class SemgrepScanner:
    """Wrapper around semgrep for broader static analysis."""

    name = "semgrep"

    @staticmethod
    def available() -> bool:
        return shutil.which("semgrep") is not None

    @staticmethod
    def scan(path: str = ".") -> ScanResult:
        if not SemgrepScanner.available():
            return ScanResult(scanner="semgrep", success=False, error="semgrep not installed. See: https://semgrep.dev/docs/getting-started/")
        try:
            proc = subprocess.run(
                ["semgrep", "--config", "auto", "--json", "--quiet", path],
                capture_output=True,
                text=True,
                timeout=180,
            )
            raw = proc.stdout
            findings: list[SecurityFinding] = []
            try:
                import json
                data = json.loads(raw)
                for r in data.get("results", []):
                    sev_str = r.get("extra", {}).get("severity", "unknown").lower()
                    sev = Severity(sev_str) if sev_str in Severity.__members__.values() else Severity.UNKNOWN
                    findings.append(
                        SecurityFinding(
                            scanner="semgrep",
                            severity=sev,
                            title=r.get("check_id", ""),
                            file=r.get("path", ""),
                            line=r.get("start", {}).get("line", 0),
                            detail=r.get("extra", {}).get("message", ""),
                        )
                    )
            except (Exception,):
                pass
            return ScanResult(scanner="semgrep", success=True, findings=findings, raw_output=raw)
        except subprocess.TimeoutExpired:
            return ScanResult(scanner="semgrep", success=False, error="semgrep timed out.")


class SecretScanner:
    """Simple regex-based secret detection."""

    name = "secrets"

    _PATTERNS: list[tuple[str, re.Pattern[str]]] = [
        ("AWS Key", re.compile(r"AKIA[0-9A-Z]{16}", re.IGNORECASE)),
        ("Generic Secret", re.compile(r"""(?:secret|password|token|api_key)\s*[=:]\s*['"][^'"]{8,}['"]""", re.IGNORECASE)),
        ("Private Key", re.compile(r"-----BEGIN (?:RSA |EC )?PRIVATE KEY-----")),
    ]

    @staticmethod
    def available() -> bool:
        return True  # pure Python, always available

    @staticmethod
    def scan(path: str = ".") -> ScanResult:
        from pathlib import Path

        findings: list[SecurityFinding] = []
        root = Path(path)
        patterns = SecretScanner._PATTERNS

        try:
            for file in root.rglob("*"):
                if file.is_dir() or file.suffix in (".pyc", ".so", ".whl", ".egg"):
                    continue
                if any(part.startswith(".") for part in file.parts):
                    continue
                try:
                    text = file.read_text(encoding="utf-8", errors="ignore")
                except (OSError, UnicodeDecodeError):
                    continue
                for line_num, line in enumerate(text.splitlines(), start=1):
                    for label, pattern in patterns:
                        if pattern.search(line):
                            findings.append(
                                SecurityFinding(
                                    scanner="secrets",
                                    severity=Severity.HIGH,
                                    title=f"Potential {label}",
                                    file=str(file),
                                    line=line_num,
                                )
                            )
        except Exception as exc:
            return ScanResult(scanner="secrets", success=False, error=str(exc))

        return ScanResult(scanner="secrets", success=True, findings=findings)


# ---- orchestrator ----


class SecurityOrchestrator:
    """Runs multiple scanners and merges results."""

    def __init__(self) -> None:
        self._scanners = {
            "code": BanditScanner,
            "deps": PipAuditScanner,
            "secrets": SecretScanner,
            "semgrep": SemgrepScanner,
        }

    def scan_code(self, path: str = ".") -> ScanResult:
        return BanditScanner.scan(path)

    def scan_deps(self, path: str = ".") -> ScanResult:
        return PipAuditScanner.scan(path)

    def scan_secrets(self, path: str = ".") -> ScanResult:
        return SecretScanner.scan(path)

    def scan_all(self, path: str = ".") -> list[ScanResult]:
        """Run all available scanners."""
        results: list[ScanResult] = []
        for name, scanner_cls in self._scanners.items():
            if scanner_cls.available():
                results.append(scanner_cls.scan(path))
            else:
                results.append(
                    ScanResult(scanner=scanner_cls.name, success=False, error=f"{scanner_cls.name} not available")
                )
        return results
