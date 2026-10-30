"""Fastn SDK configuration management.

Handles reading/writing .fastn/config.json, manifest.json, and registry.json.
Supports loading credentials from environment variables.

Configuration priority (highest wins):
    1. Constructor params:  FastnClient(api_key="...", project_id="...")
    2. Environment vars:    FASTN_API_KEY, FASTN_PROJECT_ID, FASTN_AUTH_TOKEN,
                            FASTN_TENANT_ID, FASTN_STAGE
    3. Config file:         .fastn/config.json (created by ``fastn login``)

Config file format (.fastn/config.json):
    {
        "api_key": "your-api-key",
        "project_id": "your-project-id",
        "tenant_id": "",
        "stage": "LIVE"
    }

Key classes:
    FastnConfig     Dataclass holding all config fields.
                    Fields: api_key, project_id, tenant_id, stage, timeout,
                    auth_token, refresh_token, token_expiry.

Key functions:
    load_config()   Load config from env vars + file (priority: env > file).
    save_config()   Write config to .fastn/config.json (chmod 0o600).
    load_registry() Load the cached tool registry (.fastn/registry.json).
    load_manifest() Load the manifest (.fastn/manifest.json).
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


DEFAULT_STAGE = "LIVE"
FASTN_DIR = ".fastn"
CONFIG_FILE = "config.json"
MANIFEST_FILE = "manifest.json"
REGISTRY_FILE = "registry.json"
MIGRATIONS_FILE = "migrations.json"

# Environment variable names
ENV_API_KEY = "FASTN_API_KEY"
ENV_PROJECT_ID = "FASTN_PROJECT_ID"
ENV_TENANT_ID = "FASTN_TENANT_ID"
ENV_AUTH_TOKEN = "FASTN_AUTH_TOKEN"
ENV_STAGE = "FASTN_STAGE"

# LLM provider environment variables (standard names used by each SDK)
ENV_OPENAI_API_KEY = "OPENAI_API_KEY"
ENV_ANTHROPIC_API_KEY = "ANTHROPIC_API_KEY"
ENV_GEMINI_API_KEY = "GEMINI_API_KEY"

# Supported LLM providers
LLM_PROVIDERS = {
    "openai": {
        "name": "OpenAI",
        "env_var": ENV_OPENAI_API_KEY,
        "pip_package": "openai",
        "key_url": "https://platform.openai.com/api-keys",
        "models": [
            "gpt-4.1",
            "gpt-4.1-mini",
            "gpt-4.1-nano",
            "gpt-4o",
            "gpt-4o-mini",
            "gpt-4-turbo",
            "o3",
            "o3-mini",
            "o4-mini",
            "o1",
            "o1-mini",
            "o1-pro",
        ],
        "default_model": "gpt-4.1-mini",
    },
    "anthropic": {
        "name": "Anthropic",
        "env_var": ENV_ANTHROPIC_API_KEY,
        "pip_package": "anthropic",
        "key_url": "https://console.anthropic.com/settings/keys",
        "models": [
            "claude-sonnet-4-20250514",
            "claude-haiku-4-20250514",
            "claude-opus-4-20250514",
            "claude-3.5-sonnet-20241022",
            "claude-3.5-haiku-20241022",
        ],
        "default_model": "claude-sonnet-4-20250514",
    },
    "gemini": {
        "name": "Google Gemini",
        "env_var": ENV_GEMINI_API_KEY,
        "pip_package": "google-genai",
        "key_url": "https://aistudio.google.com/apikey",
        "models": [
            "gemini-2.5-pro",
            "gemini-2.5-flash",
            "gemini-2.0-flash",
            "gemini-2.0-flash-lite",
        ],
        "default_model": "gemini-2.5-flash",
    },
}


# Model-name prefix → provider key mapping for auto-detection
_MODEL_PREFIX_MAP = {
    "gpt-": "openai",
    "o1": "openai",
    "o3": "openai",
    "o4": "openai",
    "claude-": "anthropic",
    "gemini-": "gemini",
}


def infer_provider_from_model(model_name: str) -> str | None:
    """Infer the LLM provider key from a model name, or None if unknown."""
    lower = model_name.lower()
    for prefix, provider in _MODEL_PREFIX_MAP.items():
        if lower.startswith(prefix):
            return provider
    return None


@dataclass
class FastnConfig:
    """SDK configuration loaded from env vars, .fastn/config.json, or explicit params."""

    api_key: str = ""
    project_id: str = ""
    tenant_id: str = ""
    stage: str = DEFAULT_STAGE
    timeout: float = 30.0
    auth_token: str = ""
    refresh_token: str = ""
    token_expiry: str = ""
    # LLM provider configuration (for fastn agent)
    llm_provider: str = ""  # "openai", "anthropic", "gemini"
    llm_api_key: str = ""   # API key for the selected provider
    llm_model: str = ""     # Model name override (optional)

    def validate(self) -> None:
        """Raise ConfigError if required fields are missing.

        Either api_key or auth_token must be set.
        project_id is always required.
        """
        from fastn.exceptions import ConfigError

        missing = []
        if not self.api_key and not self.auth_token:
            missing.append("api_key (or auth_token via `fastn login`)")
        if not self.project_id and not self.auth_token:
            missing.append("project_id")
        if missing:
            raise ConfigError(
                f"Missing required config fields: {', '.join(missing)}. "
                f"Run `fastn login` or set environment variables "
                f"(FASTN_API_KEY, FASTN_PROJECT_ID, etc.)."
            )

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "api_key": self.api_key,
            "project_id": self.project_id,
            "tenant_id": self.tenant_id,
            "stage": self.stage,
        }
        if self.auth_token:
            d["auth_token"] = self.auth_token
        if self.refresh_token:
            d["refresh_token"] = self.refresh_token
        if self.token_expiry:
            d["token_expiry"] = self.token_expiry
        if self.llm_provider:
            d["llm_provider"] = self.llm_provider
        if self.llm_api_key:
            d["llm_api_key"] = self.llm_api_key
        if self.llm_model:
            d["llm_model"] = self.llm_model
        return d

    def resolve_project_id(self) -> str:
        """Resolve project ID from project_id or JWT token.

        If project_id is set, use it directly (regardless of format).
        Only falls back to JWT extraction when project_id is empty.
        """
        if self.project_id:
            return self.project_id

        # Extract from JWT token only when no project_id is set
        if self.auth_token:
            try:
                from fastn.oauth import _decode_jwt_payload
                payload = _decode_jwt_payload(self.auth_token)
                roles = payload.get("realm_access", {}).get("roles", [])
                for role in roles:
                    if role.startswith("PROJECT#"):
                        parts = role.split("#")
                        if len(parts) >= 2:
                            return parts[1]
            except Exception:
                pass

        return self.project_id

    def get_headers(self) -> Dict[str, str]:
        workspace_id = self.resolve_project_id()
        headers = {
            "Content-Type": "application/json",
            "realm": "fastn",
            "stage": self.stage,
            "x-fastn-custom-auth": "false",
            "x-fastn-space-id": workspace_id,
            "x-fastn-space-tenantid": self.tenant_id,
        }
        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"
        if self.api_key:
            headers["x-fastn-api-key"] = self.api_key
        return headers


def _load_json(fastn_dir: Path, filename: str, default: Any = None) -> Any:
    """Load a JSON file from the .fastn directory, returning *default* if missing."""
    filepath = fastn_dir / filename
    if not filepath.exists():
        return default if default is not None else {}
    with open(filepath) as f:
        return json.load(f)


def _save_json(data: Any, fastn_dir: Path, filename: str) -> Path:
    """Write *data* as JSON to the .fastn directory, creating it if needed."""
    fastn_dir.mkdir(parents=True, exist_ok=True)
    filepath = fastn_dir / filename
    with open(filepath, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    return filepath


def find_fastn_dir(start_path: Optional[str] = None) -> Path:
    """Find the .fastn directory by walking up from start_path or cwd."""
    current = Path(start_path) if start_path else Path.cwd()
    while True:
        candidate = current / FASTN_DIR
        if candidate.is_dir():
            return candidate
        parent = current.parent
        if parent == current:
            break
        current = parent
    # Default to cwd
    return Path.cwd() / FASTN_DIR


def _load_env_config() -> Dict[str, str]:
    """Load configuration values from environment variables."""
    return {
        "api_key": os.environ.get(ENV_API_KEY, ""),
        "project_id": os.environ.get(ENV_PROJECT_ID, ""),
        "tenant_id": os.environ.get(ENV_TENANT_ID, ""),
        "auth_token": os.environ.get(ENV_AUTH_TOKEN, ""),
        "stage": os.environ.get(ENV_STAGE, ""),
    }


def load_config(config_path: Optional[str] = None) -> FastnConfig:
    """Load configuration from env vars, then .fastn/config.json as fallback.

    Priority: explicit params > env vars > config file.

    Args:
        config_path: Explicit path to config.json. If None, searches
            up from cwd for a .fastn directory.

    Returns:
        FastnConfig instance.
    """
    # Load from file
    if config_path:
        filepath = Path(config_path)
    else:
        fastn_dir = find_fastn_dir()
        filepath = fastn_dir / CONFIG_FILE

    file_data: Dict[str, str] = {}
    if filepath.exists():
        with open(filepath) as f:
            file_data = json.load(f)

    # Load from env vars
    env_data = _load_env_config()

    # LLM provider env vars (standard names for each SDK)
    llm_api_key = ""
    llm_provider = file_data.get("llm_provider", "")
    if llm_provider and llm_provider in LLM_PROVIDERS:
        env_var = LLM_PROVIDERS[llm_provider]["env_var"]
        llm_api_key = os.environ.get(env_var, "") or file_data.get("llm_api_key", "")
    else:
        llm_api_key = file_data.get("llm_api_key", "")

    # Env vars take precedence over file
    return FastnConfig(
        api_key=env_data.get("api_key") or file_data.get("api_key", ""),
        project_id=env_data.get("project_id") or file_data.get("project_id", "") or file_data.get("space_id", ""),
        tenant_id=env_data.get("tenant_id") or file_data.get("tenant_id", ""),
        stage=env_data.get("stage") or file_data.get("stage", DEFAULT_STAGE),
        auth_token=env_data.get("auth_token") or file_data.get("auth_token", ""),
        refresh_token=file_data.get("refresh_token", ""),
        token_expiry=file_data.get("token_expiry", ""),
        llm_provider=llm_provider,
        llm_api_key=llm_api_key,
        llm_model=file_data.get("llm_model", ""),
    )


def save_config(config: FastnConfig, directory: Optional[str] = None) -> Path:
    """Save configuration to .fastn/config.json.

    Args:
        config: The FastnConfig to save.
        directory: Directory to create .fastn in. Defaults to cwd.

    Returns:
        Path to the saved config file.
    """
    base = Path(directory) if directory else Path.cwd()
    fastn_dir = base / FASTN_DIR
    fastn_dir.mkdir(parents=True, exist_ok=True)

    filepath = fastn_dir / CONFIG_FILE
    with open(filepath, "w") as f:
        json.dump(config.to_dict(), f, indent=2)
        f.write("\n")

    # Restrict permissions to owner-only (contains API keys and tokens)
    try:
        os.chmod(filepath, 0o600)
    except OSError:
        pass  # Windows or other OS without POSIX permissions

    return filepath


def load_manifest(fastn_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Load manifest.json from the .fastn directory."""
    if fastn_dir is None:
        fastn_dir = find_fastn_dir()
    default = {"registry_version": "", "last_synced": "", "sdk": "python", "installed": {}}
    return _load_json(fastn_dir, MANIFEST_FILE, default)


def save_manifest(manifest: Dict[str, Any], fastn_dir: Optional[Path] = None) -> Path:
    """Save manifest.json to the .fastn directory."""
    if fastn_dir is None:
        fastn_dir = find_fastn_dir()
    return _save_json(manifest, fastn_dir, MANIFEST_FILE)


def load_registry(fastn_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Load registry.json from the .fastn directory."""
    if fastn_dir is None:
        fastn_dir = find_fastn_dir()
    return _load_json(fastn_dir, REGISTRY_FILE, {"version": "", "connectors": {}})


def save_registry(
    registry: Dict[str, Any], fastn_dir: Optional[Path] = None
) -> Path:
    """Save registry.json to the .fastn directory."""
    if fastn_dir is None:
        fastn_dir = find_fastn_dir()
    return _save_json(registry, fastn_dir, REGISTRY_FILE)


def get_installed_connectors(fastn_dir: Optional[Path] = None) -> List[str]:
    """Get list of installed connector names from manifest."""
    manifest = load_manifest(fastn_dir)
    return list(manifest.get("installed", {}).keys())


def add_connector_to_manifest(
    connector_name: str, version: str, fastn_dir: Optional[Path] = None
) -> None:
    """Add a connector to the installed list in manifest."""
    manifest = load_manifest(fastn_dir)
    manifest.setdefault("installed", {})[connector_name] = {
        "version": version,
        "added_at": datetime.now(timezone.utc).isoformat(),
    }
    save_manifest(manifest, fastn_dir)


def remove_connector_from_manifest(
    connector_name: str, fastn_dir: Optional[Path] = None
) -> bool:
    """Remove a connector from the installed list. Returns True if it was present."""
    manifest = load_manifest(fastn_dir)
    installed = manifest.get("installed", {})
    if connector_name in installed:
        del installed[connector_name]
        save_manifest(manifest, fastn_dir)
        return True
    return False


def load_migrations(fastn_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Load migrations.json from the .fastn directory.

    Returns the migrations map used by DynamicTool for backward
    compatibility when action schemas change.
    """
    if fastn_dir is None:
        fastn_dir = find_fastn_dir()
    return _load_json(fastn_dir, MIGRATIONS_FILE)


def save_migrations(
    migrations: Dict[str, Any], fastn_dir: Optional[Path] = None
) -> Path:
    """Save migrations.json to the .fastn directory."""
    if fastn_dir is None:
        fastn_dir = find_fastn_dir()
    return _save_json(migrations, fastn_dir, MIGRATIONS_FILE)


def ensure_gitignore(directory: Optional[str] = None) -> None:
    """Ensure .fastn/config.json is in .gitignore."""
    base = Path(directory) if directory else Path.cwd()
    gitignore = base / ".gitignore"

    entry = ".fastn/config.json"
    if gitignore.exists():
        content = gitignore.read_text()
        if entry in content:
            return
        with open(gitignore, "a") as f:
            if not content.endswith("\n"):
                f.write("\n")
            f.write(f"{entry}\n")
    else:
        gitignore.write_text(f"{entry}\n")
