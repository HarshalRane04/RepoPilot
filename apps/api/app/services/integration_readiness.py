from __future__ import annotations

from repopilot_contracts import IntegrationState, IntegrationStatus, RuntimeReadiness

from app.core.config import Settings, settings
from app.services.model_catalog import OPENROUTER_PROVIDER_ID, model_ids_for_provider, provider_by_id
from app.services.runtime_secrets import effective_settings


PLACEHOLDER_MARKERS = {"", "change-me", "change-me-local-dev", "change-me-session-secret", "placeholder", "todo"}


class IntegrationReadinessService:
    def __init__(self, config: Settings | None = None) -> None:
        self.config = config or effective_settings(settings)

    def readiness(self) -> RuntimeReadiness:
        integrations = [
            self._webhook_secret(),
            self._github_app_credentials(),
            self._github_oauth_credentials(),
            self._github_write_mode(),
            self._runtime_secret_key(),
            self._model_gateway(),
            self._model_fallback_policy(),
            self._security_tools(),
            self._observability(),
            self._session_secret(),
        ]
        blocker_states = {IntegrationState.MISSING, IntegrationState.PLACEHOLDER, IntegrationState.UNVERIFIED, IntegrationState.DISABLED}
        blockers = [
            f"{item.name}: {item.next_step}"
            for item in integrations
            if item.required_for_production and item.state in blocker_states
        ]
        warnings = [
            f"{item.name}: {item.detail}"
            for item in integrations
            if item.state == IntegrationState.DISABLED or not item.required_for_production
        ]
        return RuntimeReadiness(
            environment=self.config.environment,
            release_profile=self.config.release_profile,
            production_ready=not blockers,
            github_writes_enabled=self.config.github_writes_enabled,
            local_record_mode=not self.config.github_writes_enabled,
            github_mode=self._github_mode(),
            model_mode=self._model_mode(),
            integrations=integrations,
            blockers=blockers,
            warnings=warnings,
        )

    def _webhook_secret(self) -> IntegrationStatus:
        state = self._secret_state(self.config.github_webhook_secret)
        return IntegrationStatus(
            name="GitHub webhook secret",
            state=state,
            detail="Used to verify X-Hub-Signature-256 on all GitHub webhooks.",
            next_step="Set GITHUB_WEBHOOK_SECRET to the value configured in the GitHub App.",
        )

    def _github_app_credentials(self) -> IntegrationStatus:
        has_app_id = self._configured(self.config.github_app_id)
        has_key = self._configured(self.config.github_private_key) or self._configured(self.config.github_private_key_path)
        has_installation = self._configured(self.config.github_installation_id)
        if not (has_app_id and has_key):
            state = IntegrationState.MISSING
            detail = "Required for installation tokens, branch creation, commits, PRs, comments, labels, checks, and CI log reads."
            next_step = "Set GITHUB_APP_ID, GITHUB_APP_PRIVATE_KEY or GITHUB_PRIVATE_KEY_PATH, and GITHUB_INSTALLATION_ID."
            mode = "missing_credentials"
        elif not has_installation:
            state = IntegrationState.UNVERIFIED
            detail = "GitHub App key material is present, but no installation ID is configured for verification."
            next_step = "Set GITHUB_INSTALLATION_ID and run the GitHub App verification check."
            mode = "credentials_present_installation_missing"
        elif self._github_app_verified():
            state = IntegrationState.VERIFIED
            detail = f"Installation token verification passed for installation {self.config.github_installation_id}."
            next_step = "Run a disposable demo-repository smoke before enabling real write mode."
            mode = "read_only_verified"
        else:
            state = IntegrationState.UNVERIFIED
            detail = "GitHub App credentials and installation ID are present, but installation-token verification has not passed yet."
            next_step = "Run Settings > GitHub > Verify GitHub App before using live repository operations."
            mode = "credentials_unverified"
        return IntegrationStatus(
            name="GitHub App installation credentials",
            state=state,
            mode=mode,
            detail=detail,
            next_step=next_step,
        )

    def _github_oauth_credentials(self) -> IntegrationStatus:
        has_client = self._configured(self.config.github_client_id)
        has_secret = self._configured(self.config.github_client_secret)
        state = IntegrationState.CONFIGURED if has_client and has_secret else IntegrationState.MISSING
        return IntegrationStatus(
            name="GitHub OAuth credentials",
            state=state,
            mode="oauth_configured" if state == IntegrationState.CONFIGURED else "oauth_missing",
            detail="Required for real GitHub user sessions and repository import from the dashboard.",
            next_step="Set GITHUB_CLIENT_ID, GITHUB_CLIENT_SECRET, SESSION_SECRET_KEY, GITHUB_OAUTH_CALLBACK_URL, and WEB_APP_URL.",
        )

    def _github_write_mode(self) -> IntegrationStatus:
        production_profile = self._production_profile()
        if self.config.github_writes_enabled:
            if self._configured(self.config.github_write_smoke_verified_at):
                state = IntegrationState.VERIFIED
                detail = "Real GitHub write mode is enabled and a write-smoke verification marker is present."
                next_step = "Keep validation/security gates enabled and monitor audit logs during production use."
                mode = "write_enabled_verified"
            else:
                state = IntegrationState.UNVERIFIED
                detail = "Real GitHub write mode is enabled, but no branch/commit/draft-PR smoke verification marker is present."
                next_step = "Run the demo-repository write smoke test before public or portfolio claims."
                mode = "write_enabled_unverified"
            required_for_production = True
        else:
            state = IntegrationState.DISABLED
            detail = "Local record mode is active; branch and PR operations stay in the database."
            next_step = (
                "Set GITHUB_WRITES_ENABLED=true and run the demo-repository write smoke test before production release."
                if production_profile
                else "Set GITHUB_WRITES_ENABLED=true only after GitHub App credentials are configured."
            )
            mode = "local_record_mode"
            required_for_production = production_profile
        return IntegrationStatus(
            name="GitHub write mode",
            state=state,
            mode=mode,
            required_for_production=required_for_production,
            detail=detail,
            next_step=next_step,
        )

    def _runtime_secret_key(self) -> IntegrationStatus:
        if self._local_environment():
            return IntegrationStatus(
                name="Runtime secret key",
                state=IntegrationState.CONFIGURED,
                mode="managed_file_allowed_local",
                required_for_production=False,
                detail="Local mode may use the managed Fernet key file for the encrypted runtime secret store.",
                next_step="Use REPOPILOT_RUNTIME_SECRETS_KEY or a deployment secret manager outside local development.",
            )
        if self._configured(self.config.runtime_secrets_key):
            return IntegrationStatus(
                name="Runtime secret key",
                state=IntegrationState.CONFIGURED,
                mode="external_key_configured",
                detail="Runtime secret encryption key is supplied through the environment or deployment secret manager.",
                next_step="Keep the key outside source control and rotate it according to the deployment runbook.",
            )
        return IntegrationStatus(
            name="Runtime secret key",
            state=IntegrationState.UNVERIFIED,
            mode="managed_file_key_nonlocal",
            detail="The encrypted runtime secret store would use a managed local key file outside local mode.",
            next_step="Set REPOPILOT_RUNTIME_SECRETS_KEY or use an external secret manager before production deployment.",
        )

    def _model_gateway(self) -> IntegrationStatus:
        if self.config.model_provider == "mock":
            return IntegrationStatus(
                name="LLM model gateway",
                state=IntegrationState.PLACEHOLDER,
                mode="mock_model",
                detail="The deterministic mock model keeps tests stable but cannot perform real planning or patch generation.",
                next_step="Set MODEL_PROVIDER, MODEL_NAME, and MODEL_API_KEY for the selected provider.",
            )
        provider = provider_by_id(self.config.model_provider)
        if not provider:
            return IntegrationStatus(
                name="LLM model gateway",
                state=IntegrationState.MISSING,
                mode="provider_missing",
                detail=f"Provider {self.config.model_provider} is not in the supported inference provider catalog.",
                next_step="Select a supported provider and model in Settings > Models.",
            )
        model_known = (
            self._configured(self.config.model_name)
            if provider.id == OPENROUTER_PROVIDER_ID
            else self.config.model_name in model_ids_for_provider(self.config.model_provider)
        )
        if not model_known:
            return IntegrationStatus(
                name="LLM model gateway",
                state=IntegrationState.MISSING,
                mode="model_missing",
                detail=f"Model {self.config.model_name} is not listed for {provider.name}.",
                next_step="Select a current model from the provider catalog in Settings > Models.",
            )
        has_api_key = self._configured(self.config.model_api_key)
        verified = (
            has_api_key
            and self.config.model_provider_verified_model == f"{self.config.model_provider}:{self.config.model_name}"
            and self._configured(self.config.model_provider_verified_at)
        )
        if verified:
            state = IntegrationState.VERIFIED
            mode = "live_model_verified"
        elif has_api_key:
            state = IntegrationState.UNVERIFIED
            mode = "live_model_unverified"
        else:
            state = IntegrationState.MISSING
            mode = "live_model_key_missing"
        base_url = self.config.model_base_url or provider.default_base_url
        return IntegrationStatus(
            name="LLM model gateway",
            state=state,
            mode=mode,
            detail=f"Provider configured as {provider.name}/{self.config.model_name} at {base_url}.",
            next_step="Set MODEL_API_KEY and run provider verification before live planning/code-generation claims.",
        )

    def _model_fallback_policy(self) -> IntegrationStatus:
        if self._local_environment():
            return IntegrationStatus(
                name="Model fallback policy",
                state=IntegrationState.CONFIGURED,
                mode="fallback_allowed_local",
                required_for_production=False,
                detail="Local mode may use deterministic fallback for repeatable tests and offline demos.",
                next_step="Disable fallback outside local mode unless running a diagnostic environment.",
            )
        if self.config.allow_model_fallback:
            return IntegrationStatus(
                name="Model fallback policy",
                state=IntegrationState.UNVERIFIED,
                mode="fallback_enabled_nonlocal",
                detail="Live provider failures can fall back to deterministic output outside local mode.",
                next_step="Unset ALLOW_MODEL_FALLBACK before production release claims.",
            )
        return IntegrationStatus(
            name="Model fallback policy",
            state=IntegrationState.CONFIGURED,
            mode="fallback_disabled_nonlocal",
            detail="Non-local model calls fail closed instead of silently returning deterministic fallback output.",
            next_step="Keep fallback disabled for production and use evals/smoke tests to catch provider failures.",
        )

    def _security_tools(self) -> IntegrationStatus:
        enabled = [name for name, value in {
            "Semgrep": self.config.semgrep_enabled,
            "CodeQL": self.config.codeql_enabled,
            "dependency audit": self.config.dependency_audit_enabled,
        }.items() if value]
        return IntegrationStatus(
            name="External security tools",
            state=IntegrationState.CONFIGURED if enabled else IntegrationState.PLACEHOLDER,
            mode="external_scanners_enabled" if enabled else "regex_scanner_only",
            detail=f"Enabled tools: {', '.join(enabled) if enabled else 'deterministic regex scanner only'}.",
            next_step="Enable SEMGREP_ENABLED, CODEQL_ENABLED, and DEPENDENCY_AUDIT_ENABLED after tool installation/workflows exist.",
        )

    def _observability(self) -> IntegrationStatus:
        if self.config.enable_otel and self._configured(self.config.otel_exporter_otlp_endpoint):
            state = IntegrationState.CONFIGURED
            detail = "OpenTelemetry instrumentation and exporter endpoint are configured."
        elif self.config.enable_otel:
            state = IntegrationState.PLACEHOLDER
            detail = "OpenTelemetry instrumentation is enabled but no OTLP exporter endpoint is configured."
        else:
            state = IntegrationState.DISABLED
            detail = "OpenTelemetry instrumentation is disabled."
        return IntegrationStatus(
            name="OpenTelemetry export",
            state=state,
            mode="otel_export_configured" if state == IntegrationState.CONFIGURED else "otel_export_unconfigured",
            required_for_production=False,
            detail=detail,
            next_step="Set OTEL_EXPORTER_OTLP_ENDPOINT for real trace export.",
        )

    def _session_secret(self) -> IntegrationStatus:
        return IntegrationStatus(
            name="Dashboard session secret",
            state=self._secret_state(self.config.session_secret_key),
            mode="session_secret_ready" if self._configured(self.config.session_secret_key) else "session_secret_placeholder",
            detail="Required before replacing local header auth with cookie-backed GitHub sessions.",
            next_step="Set SESSION_SECRET_KEY to a long random secret.",
        )

    def _github_app_verified(self) -> bool:
        return (
            self._configured(self.config.github_app_verified_at)
            and self._configured(self.config.github_app_verified_installation_id)
            and self.config.github_app_verified_installation_id == self.config.github_installation_id
        )

    def _github_mode(self) -> str:
        has_app = self._configured(self.config.github_app_id) and (
            self._configured(self.config.github_private_key) or self._configured(self.config.github_private_key_path)
        )
        if not has_app:
            return "missing_credentials"
        if not self._configured(self.config.github_installation_id):
            return "credentials_present_installation_missing"
        if self.config.github_writes_enabled:
            return "write_enabled_verified" if self._configured(self.config.github_write_smoke_verified_at) else "write_enabled_unverified"
        return "read_only_verified" if self._github_app_verified() else "credentials_unverified"

    def _model_mode(self) -> str:
        if self.config.model_provider == "mock":
            return "mock_model"
        if not self._configured(self.config.model_api_key):
            return "live_model_key_missing"
        if (
            self.config.model_provider_verified_model == f"{self.config.model_provider}:{self.config.model_name}"
            and self._configured(self.config.model_provider_verified_at)
        ):
            return "live_model_verified"
        return "live_model_unverified"

    def _secret_state(self, value: str | None) -> IntegrationState:
        if value is None:
            return IntegrationState.MISSING
        lowered = value.strip().lower()
        if lowered in PLACEHOLDER_MARKERS or lowered.startswith("change-me"):
            return IntegrationState.PLACEHOLDER
        return IntegrationState.CONFIGURED

    def _configured(self, value: str | None) -> bool:
        return self._secret_state(value) == IntegrationState.CONFIGURED

    def _local_environment(self) -> bool:
        return self.config.environment.strip().lower() == "local"

    def _production_profile(self) -> bool:
        return self.config.release_profile.strip().lower() == "production"
