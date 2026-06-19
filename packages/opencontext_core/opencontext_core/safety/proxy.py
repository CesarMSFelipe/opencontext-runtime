"""LLM Context Firewall — transparent proxy for context safety scanning.

Intercepts requests to LLM providers, scans context for PII, secrets,
prompt injection, and DLP violations. Applies policies (allow/redact/block)
and logs all decisions for audit.
"""

from __future__ import annotations

import json
import logging
import re
import threading
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any

from opencontext_core.context.budgeting import estimate_tokens

logger = logging.getLogger(__name__)


# ── Policy Model ────────────────────────────────────────────────────────────


class ProxyAction(StrEnum):
    """Action the firewall takes after scanning context."""

    ALLOW = "allow"
    REDACT = "redact"
    BLOCK = "block"
    LOG_ONLY = "log_only"


class ProxyPolicy:
    """Configuration for firewall behavior."""

    def __init__(
        self,
        action_on_pii: ProxyAction = ProxyAction.REDACT,
        action_on_secrets: ProxyAction = ProxyAction.BLOCK,
        action_on_injection: ProxyAction = ProxyAction.BLOCK,
        action_on_dlp: ProxyAction = ProxyAction.BLOCK,
        redact_placeholder: str = "[REDACTED]",
        allowed_providers: list[str] | None = None,
        blocked_providers: list[str] | None = None,
        max_context_tokens: int = 128_000,
        audit_log_path: str = "",
    ):
        self.action_on_pii = action_on_pii
        self.action_on_secrets = action_on_secrets
        self.action_on_injection = action_on_injection
        self.action_on_dlp = action_on_dlp
        self.redact_placeholder = redact_placeholder
        self.allowed_providers = allowed_providers or ["*"]
        self.blocked_providers = blocked_providers or []
        self.max_context_tokens = max_context_tokens
        self.audit_log_path = audit_log_path

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_on_pii": self.action_on_pii.value,
            "action_on_secrets": self.action_on_secrets.value,
            "action_on_injection": self.action_on_injection.value,
            "action_on_dlp": self.action_on_dlp.value,
            "redact_placeholder": self.redact_placeholder,
            "max_context_tokens": self.max_context_tokens,
            "allowed_providers": self.allowed_providers,
            "blocked_providers": self.blocked_providers,
        }


# ── Data Models ─────────────────────────────────────────────────────────────


@dataclass
class AuditEntry:
    """Record of a single proxy decision."""

    timestamp: str
    trace_id: str
    provider: str
    model: str
    action: ProxyAction
    findings: list[dict[str, Any]]
    context_size_tokens: int
    duration_ms: float
    policy_snapshot: dict[str, Any]


@dataclass
class ProxyDecision:
    """Result of scanning context through the firewall."""

    action: ProxyAction
    findings: list[dict[str, Any]]
    redacted_text: str | None = None
    reason: str = ""
    audit_entry: AuditEntry | None = None


# ── Built-in Scanners (no external deps) ────────────────────────────────────


# Patterns for PII detection
_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
_PHONE_RE = re.compile(r"\+?1?\d{1,4}[ .-]?\(?\d{2,4}\)?[ .-]?\d{3,4}[ .-]?\d{3,4}")
_IP_RE = re.compile(r"\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b")
_SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")


def _luhn_check(digits: str) -> bool:
    """Luhn algorithm check for credit card numbers."""
    total = 0
    reverse_digits = digits[::-1]
    for i, d in enumerate(reverse_digits):
        n = int(d)
        if i % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0


_CC_RE = re.compile(r"\b(?:\d[ -]*?){13,16}\b")


def _scan_pii_simple(text: str) -> list[dict[str, Any]]:
    """Scan text for PII using regex patterns."""
    findings: list[dict[str, Any]] = []
    seen: set[tuple[str, int, int]] = set()

    for pattern, kind in [
        (_EMAIL_RE, "email"),
        (_PHONE_RE, "phone"),
        (_IP_RE, "ip_address"),
        (_SSN_RE, "ssn"),
    ]:
        for match in pattern.finditer(text):
            key = (kind, match.start(), match.end())
            if key not in seen:
                seen.add(key)
                findings.append(
                    {
                        "kind": f"pii.{kind}",
                        "start": match.start(),
                        "end": match.end(),
                        "value": match.group()[:40],
                        "severity": "high" if kind in ("ssn",) else "medium",
                    }
                )

    # Credit cards (with Luhn check)
    for match in _CC_RE.finditer(text):
        digits = re.sub(r"[ -]", "", match.group())
        if len(digits) >= 13 and len(digits) <= 16 and _luhn_check(digits):
            key = ("cc", match.start(), match.end())
            if key not in seen:
                seen.add(key)
                findings.append(
                    {
                        "kind": "pii.credit_card",
                        "start": match.start(),
                        "end": match.end(),
                        "value": digits[:4] + "****" + digits[-4:],
                        "severity": "critical",
                    }
                )

    return findings


# Secrets detection
_SECRETS_RE = [
    (re.compile(r"\b(?:sk|pk|sk-[a-zA-Z0-9]{20,})\b"), "api_key.openai"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "aws_access_key"),
    (re.compile(r"-----BEGIN (RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----"), "private_key"),
    (re.compile(r"\bghp_[a-zA-Z0-9]{36}\b"), "github_token"),
    (re.compile(r"\bgithub_pat_[a-zA-Z0-9]{22,}\b"), "github_pat"),
    (re.compile(r"\b(?:ghr|gho|ghu|ghs)_[a-zA-Z0-9]{36}\b"), "github_token_alt"),
    (
        re.compile(
            r"(?i)(?:api[_-]?key|secret|token|password)\s*[:=]\s*['\"][a-zA-Z0-9_\-./+=]{8,}['\"]"
        ),
        "generic_secret",
    ),
]


def _scan_secrets_simple(text: str) -> list[dict[str, Any]]:
    """Scan text for secrets, API keys, tokens."""
    findings: list[dict[str, Any]] = []
    seen_ranges: list[tuple[int, int]] = []

    for pattern, kind in _SECRETS_RE:
        for match in pattern.finditer(text):
            # Deduplicate overlapping matches
            start, end = match.start(), match.end()
            if any(s <= start < e or s < end <= e for s, e in seen_ranges):
                continue
            seen_ranges.append((start, end))
            findings.append(
                {
                    "kind": f"secret.{kind}",
                    "start": start,
                    "end": end,
                    "value": match.group()[:30] + "..."
                    if len(match.group()) > 30
                    else match.group(),
                    "severity": "critical",
                }
            )

    return findings


# Prompt injection keywords (case-insensitive via flag)
_INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?previous\s+(instructions|directions|prompts?|commands?)",
    r"(you\s+are\s+now|pretend\s+(to\s+be|that)|act\s+as\s+if)",
    r"(system\s+prompt|override|jailbreak|jail.?break)",
    r"forget\s+(everything|all\s+(previous|prior))",
    r"do\s+(not\s+)?(follow|obey|listen|respect)\s+(the\s+)?(previous|original)",
    r"(new\s+)?(instruction|rule|prompt)[\s:]*[:=]",
    r"\bDAN\b",
    r"(print|output|show|reveal|display)\s+(your\s+)?(system\s+)?prompt",
    r"how\s+(to\s+)?(hack|jailbreak|bypass|exploit|crack)",
]

_INJECTION_RE = re.compile("|".join(_INJECTION_PATTERNS), re.IGNORECASE)


def _scan_prompt_injection_simple(text: str) -> list[dict[str, Any]]:
    """Scan text for prompt injection attempts."""
    findings: list[dict[str, Any]] = []
    seen: set[str] = set()

    for match in _INJECTION_RE.finditer(text):
        matched_text = match.group().lower().strip()
        if matched_text and matched_text not in seen:
            seen.add(matched_text)
            findings.append(
                {
                    "kind": "injection.keyword",
                    "start": match.start(),
                    "end": match.end(),
                    "value": matched_text[:60],
                    "severity": "high",
                }
            )

    return findings


# ── Context Firewall ────────────────────────────────────────────────────────


def _generate_trace_id() -> str:
    """Generate a short trace/request ID."""
    import uuid

    return uuid.uuid4().hex[:16]


class ContextFirewall:
    """Main firewall — scans context and applies policies."""

    def __init__(self, policy: ProxyPolicy | None = None):
        self.policy = policy or ProxyPolicy()
        self._lock = threading.Lock()
        self._audit_log: list[AuditEntry] = []
        self._stats: dict[str, Any] = {
            "total_requests": 0,
            "blocked": 0,
            "redacted": 0,
            "allowed": 0,
            "by_provider": {},
        }

    def scan_context(
        self,
        text: str,
        provider: str = "",
        model: str = "",
    ) -> ProxyDecision:
        """Scan context text and return a proxy decision."""
        start = time.monotonic()
        trace_id = _generate_trace_id()
        all_findings: list[dict[str, Any]] = []
        ctx_tokens = estimate_tokens(text)

        # 1. Provider check
        provider_ok = self._check_provider(provider)
        if not provider_ok:
            decision = ProxyDecision(
                action=ProxyAction.BLOCK,
                findings=[],
                reason=f"Provider '{provider}' is not allowed",
            )
            self._record_stats(decision.action, provider)
            return decision

        # 2. Context size check
        if ctx_tokens > self.policy.max_context_tokens:
            decision = ProxyDecision(
                action=ProxyAction.BLOCK,
                findings=[
                    {
                        "kind": "context.too_large",
                        "start": 0,
                        "end": len(text),
                        "value": (
                            f"{ctx_tokens} tokens exceeds limit of {self.policy.max_context_tokens}"
                        ),
                        "severity": "medium",
                    }
                ],
                reason=f"Context too large: {ctx_tokens} > {self.policy.max_context_tokens} tokens",
            )
            self._record_stats(decision.action, provider)
            return decision

        # 3. Run all scanners
        pii_findings = _scan_pii_simple(text)
        secret_findings = _scan_secrets_simple(text)
        injection_findings = _scan_prompt_injection_simple(text)

        all_findings.extend(pii_findings)
        all_findings.extend(secret_findings)
        all_findings.extend(injection_findings)

        # 4. Determine action
        action = ProxyAction.ALLOW
        reason_parts: list[str] = []

        if injection_findings and self.policy.action_on_injection == ProxyAction.BLOCK:
            action = ProxyAction.BLOCK
            reason_parts.append(f"Prompt injection detected ({len(injection_findings)} patterns)")
        elif secret_findings and self.policy.action_on_secrets == ProxyAction.BLOCK:
            action = ProxyAction.BLOCK
            reason_parts.append(f"Secrets detected ({len(secret_findings)} matches)")
        elif pii_findings and self.policy.action_on_pii == ProxyAction.REDACT:
            action = ProxyAction.REDACT
            reason_parts.append(f"PII detected ({len(pii_findings)} items, will redact)")
        elif all_findings:
            action = ProxyAction.LOG_ONLY
            reason_parts.append(f"{len(all_findings)} finding(s) found, logging only")

        # 5. Redact if needed
        redacted = None
        if action == ProxyAction.REDACT or (
            action == ProxyAction.ALLOW
            and pii_findings
            and self.policy.action_on_pii == ProxyAction.REDACT
        ):
            redacted = self._redact_text(text, pii_findings)

        # 6. Create audit entry
        duration = (time.monotonic() - start) * 1000
        entry = AuditEntry(
            timestamp=datetime.now().isoformat(),
            trace_id=trace_id,
            provider=provider or "unknown",
            model=model or "unknown",
            action=action,
            findings=[
                {k: f["value"] if k == "value" else f[k] for k in ("kind", "severity", "value")}
                for f in all_findings[:20]
            ],
            context_size_tokens=ctx_tokens,
            duration_ms=round(duration, 1),
            policy_snapshot=self.policy.to_dict(),
        )

        decision = ProxyDecision(
            action=action,
            findings=all_findings,
            redacted_text=redacted,
            reason="; ".join(reason_parts) if reason_parts else "No issues detected",
            audit_entry=entry,
        )

        self._record_stats(action, provider)
        self._append_audit(entry)

        return decision

    def redact_context(self, text: str, findings: list[dict[str, Any]]) -> str:
        """Public method to redact text based on findings."""
        return self._redact_text(text, findings)

    def _redact_text(self, text: str, findings: list[dict[str, Any]]) -> str:
        """Replace sensitive ranges with placeholder."""
        sorted_findings = sorted(
            [f for f in findings if f["severity"] in ("critical", "high", "medium")],
            key=lambda f: f["start"],
            reverse=True,
        )
        result = text
        for f in sorted_findings:
            start = f["start"]
            end = f["end"]
            if start < end <= len(result):
                result = result[:start] + self.policy.redact_placeholder + result[end:]
        return result

    def get_audit_log(self, limit: int = 100) -> list[AuditEntry]:
        """Return recent audit entries."""
        with self._lock:
            return list(self._audit_log[-limit:])

    def export_audit_json(self, path: str) -> None:
        """Persist audit log to a JSON file."""
        with self._lock:
            entries = [asdict(e) for e in self._audit_log]
        with open(path, "w") as f:
            json.dump(entries, f, indent=2, default=str)

    def get_stats(self) -> dict[str, Any]:
        """Return aggregate firewall statistics."""
        with self._lock:
            return dict(self._stats)

    def _check_provider(self, provider: str) -> bool:
        """Check if a provider is allowed by policy."""
        if provider in self.policy.blocked_providers:
            return False
        if "*" in self.policy.allowed_providers:
            return True
        return provider in self.policy.allowed_providers

    def _record_stats(self, action: ProxyAction, provider: str) -> None:
        with self._lock:
            self._stats["total_requests"] += 1
            if action == ProxyAction.BLOCK:
                self._stats["blocked"] += 1
            elif action == ProxyAction.REDACT:
                self._stats["redacted"] += 1
            else:
                self._stats["allowed"] += 1
            if provider:
                prov_stats = self._stats["by_provider"].setdefault(
                    provider,
                    {
                        "total": 0,
                        "blocked": 0,
                        "redacted": 0,
                        "allowed": 0,
                    },
                )
                prov_stats["total"] += 1
                if action == ProxyAction.BLOCK:
                    prov_stats["blocked"] += 1
                elif action == ProxyAction.REDACT:
                    prov_stats["redacted"] += 1
                else:
                    prov_stats["allowed"] += 1

    def _append_audit(self, entry: AuditEntry) -> None:
        with self._lock:
            self._audit_log.append(entry)
            # Keep max 10K entries in memory
            if len(self._audit_log) > 10_000:
                self._audit_log = self._audit_log[-5_000:]


# ── Simple Proxy Server ─────────────────────────────────────────────────────


class SimpleProxyServer:
    """Minimal HTTP proxy that wraps ContextFirewall.

    Starts a local HTTP server that accepts LLM-style request payloads,
    scans them through the firewall, and returns the decision.
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 9099,
        firewall: ContextFirewall | None = None,
    ):
        self.host = host
        self.port = port
        self.firewall = firewall or ContextFirewall()
        self._server: Any = None
        self._thread: threading.Thread | None = None

    @property
    def proxy_url(self) -> str:
        return f"http://{self.host}:{self.port}/proxy"

    @property
    def is_running(self) -> bool:
        return self._server is not None

    def _make_handler(self) -> type:
        """Create a request handler class for http.server."""
        firewall = self.firewall

        import http.server as server

        class ProxyHandler(server.BaseHTTPRequestHandler):
            def log_message(self, fmt: str, *args: Any) -> None:
                logger.debug(fmt, *args)

            def _send_json(self, status: int, data: dict[str, Any]) -> None:
                body = json.dumps(data).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self) -> None:
                if self.path == "/health":
                    stats = firewall.get_stats()
                    self._send_json(
                        200,
                        {
                            "status": "ok",
                            "total_scanned": stats["total_requests"],
                            "blocked": stats["blocked"],
                            "redacted": stats["redacted"],
                        },
                    )
                elif self.path == "/stats":
                    self._send_json(200, firewall.get_stats())
                elif self.path == "/policy":
                    self._send_json(200, firewall.policy.to_dict())
                else:
                    self._send_json(404, {"error": "not_found"})

            def do_POST(self) -> None:
                if self.path != "/proxy":
                    self._send_json(404, {"error": "not_found"})
                    return

                content_len = int(self.headers.get("Content-Length", 0))
                if content_len == 0:
                    self._send_json(400, {"error": "empty_body"})
                    return

                try:
                    body = self.rfile.read(content_len)
                    data = json.loads(body)
                    text = data.get("prompt", data.get("text", ""))
                    provider = data.get("provider", data.get("model", ""))
                    model = data.get("model", "")

                    decision = firewall.scan_context(text, provider=provider, model=model)
                    self._send_json(
                        200,
                        {
                            "action": decision.action.value,
                            "text": decision.redacted_text or text,
                            "findings": [
                                {"kind": f["kind"], "severity": f["severity"]}
                                for f in decision.findings[:10]
                            ],
                            "reason": decision.reason,
                            "trace_id": decision.audit_entry.trace_id
                            if decision.audit_entry
                            else "",
                        },
                    )
                except json.JSONDecodeError:
                    self._send_json(400, {"error": "invalid_json"})
                except Exception as exc:
                    logger.exception("Proxy error")
                    self._send_json(500, {"error": str(exc)})

        return ProxyHandler

    def start(self) -> None:
        """Start the proxy server (blocking call)."""
        import http.server as server

        handler = self._make_handler()
        self._server = server.HTTPServer((self.host, self.port), handler)
        logger.info("Context Firewall proxy listening on %s", self.proxy_url)
        try:
            self._server.serve_forever()
        except KeyboardInterrupt:
            self.stop()

    def start_background(self) -> None:
        """Start proxy in a background daemon thread."""
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self.start, daemon=True)
        self._thread.start()
        # Wait briefly for server to start (Windows CI needs longer)
        import time as _time

        _time.sleep(0.3)

    def stop(self) -> None:
        """Stop the proxy server."""
        if self._server:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
            logger.info("Context Firewall proxy stopped")
