# air-crewai-trust

[![CI](https://github.com/airblackbox/trust-crewai/actions/workflows/ci.yml/badge.svg)](https://github.com/airblackbox/trust-crewai/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://github.com/airblackbox/trust-crewai/blob/main/LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-3776AB.svg?logo=python&logoColor=white)](https://python.org)


**AIR Trust Layer for CrewAI** — Drop-in security, audit, and compliance for your AI agents.

Part of the [AIR Blackbox](https://airblackbox.com) ecosystem. Adds tamper-proof audit trails, sensitive data tokenization, consent gates for destructive tools, and prompt injection detection to any CrewAI project.

> **[View Interactive Demo](https://htmlpreview.github.io/?https://github.com/airblackbox/trust-crewai/blob/main/demo.html)** — Walk through every feature with animated examples.


## Quick Start

```bash
pip install air-crewai-trust
```

```python
from crewai import Agent, Task, Crew
from air_crewai_trust import activate_trust

# One line activates all trust hooks
plugin = activate_trust()

# Your CrewAI code runs as normal — trust layer works transparently
agent = Agent(role="Researcher", goal="Find information", backstory="...")
task = Task(description="Research AI safety", agent=agent)
crew = Crew(agents=[agent], tasks=[task])
crew.kickoff()

# Check what happened
print(plugin.get_audit_stats())
print(plugin.verify_chain())
```

## What It Does

### Tamper-Proof Audit Trail
Every tool call and LLM interaction is logged to an HMAC-SHA256 signed chain. Each entry references the previous entry's hash — modify any record and the chain breaks. Like a blockchain, but for your AI agent's actions.

### Sensitive Data Tokenization
API keys, credentials, PII (emails, SSNs, phone numbers, credit cards) are automatically detected and replaced with opaque tokens before they reach the LLM. Original values are stored locally in the vault and can be restored when the tool actually needs them.

**14 built-in patterns** covering:
- API keys (OpenAI, Anthropic, AWS, GitHub, Stripe)
- Credentials (Bearer tokens, private keys, connection strings, passwords)
- PII (emails, phone numbers, SSNs, credit cards)

### Consent Gate
Destructive tools (exec, shell, deploy, file_delete) are blocked until the user explicitly approves them. Risk classification:

| Risk Level | Tools | Action |
|-----------|-------|--------|
| **Critical** | exec, spawn, shell | Always requires consent |
| **High** | fs_write, deploy, git_push | Requires consent (default threshold) |
| **Medium** | send_email, http_request | Configurable |
| **Low** | fs_read, search, query | Auto-approved |

### Prompt Injection Detection
15+ weighted patterns detect prompt injection attempts including role overrides, jailbreaks, delimiter injection, privilege escalation, and data exfiltration. Configurable sensitivity (low/medium/high) and block threshold.

## Configuration

```python
from air_crewai_trust import activate_trust, AirTrustConfig

config = AirTrustConfig(
    consent_gate={
        "enabled": True,
        "always_require": ["exec", "spawn", "shell", "deploy"],
        "risk_threshold": "high",
    },
    vault={
        "enabled": True,
        "categories": ["api_key", "credential", "pii"],
    },
    injection_detection={
        "enabled": True,
        "sensitivity": "medium",
        "block_threshold": 0.8,
    },
    audit_ledger={
        "enabled": True,
        "max_entries": 10000,
    },
    # Optional: forward audit records to AIR Blackbox gateway
    gateway_url="https://your-gateway.example.com",
    gateway_key="your-api-key",
)

plugin = activate_trust(config)
```

## CrewAI Hook Mapping

| CrewAI Hook | Trust Components |
|-------------|-----------------|
| `before_tool_call` | ConsentGate → DataVault → AuditLedger |
| `after_tool_call` | AuditLedger |
| `before_llm_call` | InjectionDetector → DataVault → AuditLedger |
| `after_llm_call` | AuditLedger |

## API Reference

```python
from air_crewai_trust import activate_trust, deactivate_trust, get_plugin

# Activate / deactivate
plugin = activate_trust(config=None)  # Returns AirTrustPlugin
deactivate_trust()                     # Unregisters all hooks

# Plugin methods
plugin.get_audit_stats()   # → {"total_entries": 42, "chain_valid": True, ...}
plugin.verify_chain()      # → {"valid": True, "total_entries": 42}
plugin.export_audit()      # → [{"id": "...", "action": "tool_call", ...}, ...]
plugin.get_vault_stats()   # → {"total_tokens": 5, "by_category": {"api_key": 3, "pii": 2}}
```

## AIR Blackbox Ecosystem

This plugin is part of the AIR Blackbox observability and trust platform:

| Repository | Purpose |
|-----------|---------|
| [gateway](https://github.com/airblackbox/gateway) | Go proxy gateway with detection, prevention, and optimization |
| [python-sdk](https://github.com/airblackbox/python-sdk) | Python SDK for the gateway |
| [trust-openclaw](https://github.com/airblackbox/trust-openclaw) | TypeScript trust layer for OpenClaw |
| **trust-crewai** | **Python trust layer for CrewAI** (this repo) |

## Development

```bash
git clone https://github.com/airblackbox/trust-crewai.git
cd trust-crewai
pip install -e ".[dev]"
pytest tests/ -v
```

## License

MIT
