from uuid import uuid4

from repopilot_contracts import (
    ActivityEvent,
    AgentRunState,
    CodeQLAlertFetchRequest,
    CodeQLRecommendationResponse,
    CodeQLSarifIngestionRequest,
    EmbeddingResponse,
    EvalReportsResponse,
    ImplementationPlan,
    LLMCallMode,
    LLMResponse,
    LLMTrace,
    PlanDetailResponse,
    PolicyDecision,
    PolicyDecisionType,
    PullRequestSummaryResponse,
    RunTraceResponse,
    SecurityFindingDetailResponse,
    TokenUsage,
    ToolBlockType,
)


def test_implementation_plan_requires_approval_by_default() -> None:
    plan = ImplementationPlan(
        plan_id="plan-1",
        issue_id="issue-1",
        rollback_plan="Revert the generated branch.",
    )

    assert plan.requires_human_approval is True


def test_policy_decision_can_deny_unknown_tool() -> None:
    decision = PolicyDecision(decision=PolicyDecisionType.DENY, reason="Unknown tool")

    assert decision.decision == PolicyDecisionType.DENY


def test_llm_gateway_contracts_are_exported() -> None:
    response = LLMResponse(content="{}", model="mock", tokens=TokenUsage(prompt=1, completion=1, total=2))
    embeddings = EmbeddingResponse(embeddings=[[0.1, 0.2]], provider="mock", model="mock-embedding", dimensions=2)

    assert response.mode == LLMCallMode.MOCK
    assert embeddings.provider == "mock"
    assert embeddings.dimensions == 2
    assert ToolBlockType.BUDGET_EXCEEDED == "budget_exceeded"


def test_llm_trace_contract_carries_provider_mode_and_hash_evidence() -> None:
    trace = LLMTrace(
        run_id=uuid4(),
        agent_name="planning",
        prompt_hash="prompt-hash",
        response_hash="response-hash",
        provider="openrouter",
        model="google/gemma-4-31b-it:free",
        mode="live",
        tokens=12,
        cost=0.0,
        latency_ms=163,
        metadata={"context_citations": ["README.md:1"]},
    )

    assert trace.provider == "openrouter"
    assert trace.mode == "live"
    assert trace.response_hash == "response-hash"
    assert trace.metadata["context_citations"] == ["README.md:1"]


def test_agent_state_includes_phase_one_control_plane_start() -> None:
    assert AgentRunState.NEW_EVENT == "NEW_EVENT"


def test_key_operator_response_contracts_are_exported() -> None:
    assert ActivityEvent.__name__ == "ActivityEvent"
    assert RunTraceResponse.__name__ == "RunTraceResponse"
    assert PlanDetailResponse.__name__ == "PlanDetailResponse"
    assert PullRequestSummaryResponse.__name__ == "PullRequestSummaryResponse"
    assert SecurityFindingDetailResponse.__name__ == "SecurityFindingDetailResponse"
    assert EvalReportsResponse.__name__ == "EvalReportsResponse"
    assert CodeQLSarifIngestionRequest.__name__ == "CodeQLSarifIngestionRequest"
    assert CodeQLAlertFetchRequest.__name__ == "CodeQLAlertFetchRequest"
    assert CodeQLRecommendationResponse.__name__ == "CodeQLRecommendationResponse"


def test_openapi_uses_typed_operator_response_models() -> None:
    from app.main import create_app

    schema = create_app().openapi()

    assert _response_ref(schema, "/activity", "get", list_item=True) == "#/components/schemas/ActivityEvent"
    assert _response_ref(schema, "/runs/{run_id}/trace", "get") == "#/components/schemas/RunTraceResponse"
    assert _response_ref(schema, "/plans/{plan_id}", "get") == "#/components/schemas/PlanDetailResponse"
    assert _response_ref(schema, "/prs/{pr_id}/summary", "get") == "#/components/schemas/PullRequestSummaryResponse"
    assert _response_ref(schema, "/security/findings/{finding_id}", "get") == "#/components/schemas/SecurityFindingDetailResponse"
    assert _response_ref(schema, "/security/codeql/recommendation", "get") == "#/components/schemas/CodeQLRecommendationResponse"
    assert _response_ref(schema, "/security/runs/{run_id}/codeql/sarif", "post") == "#/components/schemas/SecurityScanResult"
    assert _response_ref(schema, "/security/runs/{run_id}/codeql/alerts/fetch", "post") == "#/components/schemas/SecurityScanResult"
    assert _response_ref(schema, "/evals/reports", "get") == "#/components/schemas/EvalReportsResponse"
    assert _response_ref(schema, "/settings/readiness", "get") == "#/components/schemas/RuntimeReadiness"


def _response_ref(schema: dict[str, object], path: str, method: str, *, list_item: bool = False) -> str:
    path_item = schema["paths"][path]  # type: ignore[index]
    operation = path_item[method]  # type: ignore[index]
    response_schema = operation["responses"]["200"]["content"]["application/json"]["schema"]  # type: ignore[index]
    if list_item:
        return response_schema["items"]["$ref"]
    return response_schema["$ref"]
