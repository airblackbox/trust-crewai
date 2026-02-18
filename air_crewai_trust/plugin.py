"""
air-crewai-trust — CrewAI Plugin

Wires the trust layer components into CrewAI's hook system:
  - before_tool_call → ConsentGate + DataVault + AuditLedger
  - after_tool_call  → AuditLedger
  - before_llm_call  → InjectionDetector + DataVault + AuditLedger
  - after_llm_call   → AuditLedger

Usage:
    from air_crewai_trust import activate_trust
    activate_trust()  # registers all hooks with CrewAI
"""

from __future__ import annotations

import json
import logging
from typing import Any

from .config import AirTrustConfig
from .audit_ledger import AuditLedger
from .consent_gate import ConsentGate
from .data_vault import DataVault
from .injection_detector import InjectionDetector

logger = logging.getLogger("air_crewai_trust")


class AirTrustPlugin:
    """
    Orchestrates all trust layer components and registers
    them as CrewAI hooks.
    """

    def __init__(self, config: AirTrustConfig | None = None) -> None:
        self.config = config or AirTrustConfig()
        self._active = False

        # Initialize components
        self.ledger = AuditLedger(
            self.config.audit_ledger,
            self.config.gateway_url,
            self.config.gateway_key,
        )
        self.consent_gate = ConsentGate(self.config.consent_gate, self.ledger)
        self.vault = DataVault(
            self.config.vault,
            self.config.gateway_url,
            self.config.gateway_key,
        )
        self.injection_detector = InjectionDetector(self.config.injection_detection)

    def activate(self) -> None:
        """Register all trust hooks with CrewAI."""
        if self._active:
            logger.warning("AIR Trust is already active")
            return

        try:
            from crewai.utilities.hooks import (
                register_before_tool_call_hook,
                register_after_tool_call_hook,
                register_before_llm_call_hook,
                register_after_llm_call_hook,
            )
        except ImportError:
            raise ImportError(
                "CrewAI is required but not installed. "
                "Install it with: pip install crewai"
            )

        register_before_tool_call_hook(self._before_tool_call)
        register_after_tool_call_hook(self._after_tool_call)
        register_before_llm_call_hook(self._before_llm_call)
        register_after_llm_call_hook(self._after_llm_call)

        self._active = True
        logger.info("AIR Trust activated — all hooks registered with CrewAI")

    def deactivate(self) -> None:
        """Unregister all trust hooks from CrewAI."""
        if not self._active:
            return

        try:
            from crewai.utilities.hooks import (
                unregister_before_tool_call_hook,
                unregister_after_tool_call_hook,
                unregister_before_llm_call_hook,
                unregister_after_llm_call_hook,
            )

            unregister_before_tool_call_hook(self._before_tool_call)
            unregister_after_tool_call_hook(self._after_tool_call)
            unregister_before_llm_call_hook(self._before_llm_call)
            unregister_after_llm_call_hook(self._after_llm_call)
        except ImportError:
            pass  # If CrewAI isn't available, hooks are already gone

        self._active = False
        logger.info("AIR Trust deactivated — all hooks unregistered")

    @property
    def is_active(self) -> bool:
        return self._active

    # ─── Hook Handlers ────────────────────────────────────────

    def _before_tool_call(self, context: Any) -> bool | None:
        """
        Called before each tool call.
        Returns False to block, True/None to allow.
        """
        if not self.config.enabled:
            return None

        tool_name = getattr(context, "tool_name", "unknown")
        tool_input = getattr(context, "tool_input", {})

        if isinstance(tool_input, str):
            try:
                tool_input = json.loads(tool_input)
            except (json.JSONDecodeError, TypeError):
                tool_input = {"input": tool_input}

        # 1. Tokenize sensitive data in tool input
        data_tokenized = False
        if self.config.vault.enabled and tool_input:
            input_str = json.dumps(tool_input)
            result = self.vault.tokenize(input_str)
            if result["tokenized"]:
                data_tokenized = True
                try:
                    tokenized_input = json.loads(result["result"])
                    # Mutate the tool input if possible
                    if hasattr(context, "tool_input") and isinstance(
                        context.tool_input, dict
                    ):
                        context.tool_input.clear()
                        context.tool_input.update(tokenized_input)
                except (json.JSONDecodeError, TypeError):
                    pass

        # 2. Check consent gate
        if self.config.consent_gate.enabled:
            consent_result = self.consent_gate.intercept(tool_name, tool_input)
            if consent_result.get("blocked"):
                logger.warning(
                    f"Tool call blocked by consent gate: {tool_name}"
                )
                return False

        # 3. Log the tool call
        if self.config.audit_ledger.enabled:
            self.ledger.append(
                action="tool_call",
                tool_name=tool_name,
                risk_level=self.consent_gate.classify_risk(tool_name).value,
                consent_required=self.consent_gate.requires_consent(tool_name),
                consent_granted=True,
                data_tokenized=data_tokenized,
                injection_detected=False,
            )

        return None  # Allow

    def _after_tool_call(self, context: Any) -> None:
        """Called after each tool call completes."""
        if not self.config.enabled or not self.config.audit_ledger.enabled:
            return

        tool_name = getattr(context, "tool_name", "unknown")

        self.ledger.append(
            action="tool_result",
            tool_name=tool_name,
            risk_level=self.consent_gate.classify_risk(tool_name).value,
            consent_required=False,
            data_tokenized=False,
            injection_detected=False,
        )

    def _before_llm_call(self, context: Any) -> bool | None:
        """
        Called before content is sent to the LLM.
        Returns False to block, True/None to allow.
        """
        if not self.config.enabled:
            return None

        messages = getattr(context, "messages", [])
        if not messages:
            return None

        # Extract text content from messages
        content_parts: list[str] = []
        for msg in messages:
            if isinstance(msg, dict):
                content_parts.append(str(msg.get("content", "")))
            elif isinstance(msg, str):
                content_parts.append(msg)
            elif hasattr(msg, "content"):
                content_parts.append(str(msg.content))

        full_content = "\n".join(content_parts)
        if not full_content.strip():
            return None

        data_tokenized = False
        injection_detected = False

        # 1. Tokenize sensitive data before it reaches the LLM
        if self.config.vault.enabled:
            result = self.vault.tokenize(full_content)
            if result["tokenized"]:
                data_tokenized = True
                # Try to mutate messages with tokenized content
                tokenized_content = result["result"]
                if hasattr(context, "messages") and isinstance(context.messages, list):
                    for i, msg in enumerate(context.messages):
                        if isinstance(msg, dict) and "content" in msg:
                            msg_content = str(msg["content"])
                            tokenized_msg = self.vault.tokenize(msg_content)
                            if tokenized_msg["tokenized"]:
                                msg["content"] = tokenized_msg["result"]

        # 2. Check for injection patterns
        if self.config.injection_detection.enabled:
            scan_result = self.injection_detector.scan(full_content)
            if scan_result.detected:
                injection_detected = True

                if (
                    self.config.injection_detection.log_detections
                    and self.config.audit_ledger.enabled
                ):
                    risk = "critical" if scan_result.score >= 0.8 else (
                        "high" if scan_result.score >= 0.5 else "medium"
                    )
                    self.ledger.append(
                        action="injection_detected",
                        risk_level=risk,
                        consent_required=False,
                        data_tokenized=data_tokenized,
                        injection_detected=True,
                        metadata={
                            "score": scan_result.score,
                            "patterns": scan_result.patterns,
                            "blocked": scan_result.blocked,
                            "source": "llm_input",
                        },
                    )

                if scan_result.blocked:
                    logger.warning(
                        f"LLM input blocked by injection detector "
                        f"(score: {scan_result.score:.2f}, "
                        f"patterns: {', '.join(scan_result.patterns)})"
                    )
                    return False

        return None  # Allow

    def _after_llm_call(self, context: Any) -> None:
        """Called after LLM responds."""
        if not self.config.enabled or not self.config.audit_ledger.enabled:
            return

        response = getattr(context, "response", None)
        content_length = 0
        if response:
            if isinstance(response, str):
                content_length = len(response)
            elif hasattr(response, "content"):
                content_length = len(str(response.content))

        model = getattr(context, "llm", "unknown")
        if hasattr(model, "model_name"):
            model = model.model_name
        elif hasattr(model, "model"):
            model = model.model

        self.ledger.append(
            action="llm_output",
            risk_level="none",
            consent_required=False,
            data_tokenized=False,
            injection_detected=False,
            metadata={
                "model": str(model),
                "content_length": content_length,
            },
        )

    # ─── Public API ───────────────────────────────────────────

    def get_audit_stats(self) -> dict:
        """Get audit chain statistics."""
        return self.ledger.stats()

    def verify_chain(self) -> dict:
        """Verify audit chain integrity."""
        return self.ledger.verify().to_dict()

    def export_audit(self) -> list[dict]:
        """Export all audit entries."""
        return self.ledger.export()

    def get_vault_stats(self) -> dict:
        """Get data vault statistics."""
        return self.vault.stats()
