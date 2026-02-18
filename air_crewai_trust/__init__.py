"""
air-crewai-trust — AIR Trust Layer for CrewAI

Drop-in security, audit, and compliance layer for CrewAI agents.
Adds tamper-proof audit trails, sensitive data tokenization,
consent gates for destructive tools, and prompt injection detection.

Usage:
    from air_crewai_trust import activate_trust

    # Activate with defaults
    plugin = activate_trust()

    # Or with custom config
    from air_crewai_trust import AirTrustConfig, activate_trust
    config = AirTrustConfig(
        injection_detection={"sensitivity": "high"},
    )
    plugin = activate_trust(config)

    # Later...
    deactivate_trust()
"""

from __future__ import annotations

from .config import (
    RISK_ORDER,
    AirTrustConfig,
    AuditLedgerConfig,
    ConsentGateConfig,
    InjectionDetectionConfig,
    RiskLevel,
    VaultConfig,
)
from .plugin import AirTrustPlugin

__version__ = "0.1.0"
__all__ = [
    "activate_trust",
    "deactivate_trust",
    "get_plugin",
    "AirTrustPlugin",
    "AirTrustConfig",
    "AuditLedgerConfig",
    "ConsentGateConfig",
    "InjectionDetectionConfig",
    "RiskLevel",
    "RISK_ORDER",
    "VaultConfig",
]

_plugin: AirTrustPlugin | None = None


def activate_trust(config: AirTrustConfig | None = None) -> AirTrustPlugin:
    """
    Activate the AIR trust layer for CrewAI.

    Registers all trust hooks (audit, consent, vault, injection detection)
    with CrewAI's hook system. Call once before running your Crew.

    Args:
        config: Optional custom configuration. Uses sensible defaults if omitted.

    Returns:
        The active AirTrustPlugin instance.
    """
    global _plugin

    if _plugin is not None and _plugin.is_active:
        return _plugin

    _plugin = AirTrustPlugin(config)
    _plugin.activate()
    return _plugin


def deactivate_trust() -> None:
    """
    Deactivate the AIR trust layer.

    Unregisters all hooks from CrewAI. Safe to call even if not active.
    """
    global _plugin

    if _plugin is not None:
        _plugin.deactivate()
        _plugin = None


def get_plugin() -> AirTrustPlugin | None:
    """Get the current active plugin instance, or None if not active."""
    return _plugin
