from .fixtures import FixtureCheckSummary, FixtureVerifier
from .patch_quality import PatchQualityEvidence, PatchQualityResult, PatchQualityScorer
from .plan_quality import PlanQualityEvidence, PlanQualityResult, PlanQualityScorer
from .provider_comparison import ProviderComparisonResult, ProviderComparisonScorer, ProviderEvalEvidence


def __getattr__(name: str):
    if name in {"BenchmarkReport", "BenchmarkReportBuilder"}:
        from .report import BenchmarkReport, BenchmarkReportBuilder

        return {"BenchmarkReport": BenchmarkReport, "BenchmarkReportBuilder": BenchmarkReportBuilder}[name]
    if name in {"ProviderPlanningEvalRunner", "OpenAICompatibleChatClient", "ProviderChatClient"}:
        from .provider_harness import OpenAICompatibleChatClient, ProviderChatClient, ProviderPlanningEvalRunner

        return {
            "OpenAICompatibleChatClient": OpenAICompatibleChatClient,
            "ProviderChatClient": ProviderChatClient,
            "ProviderPlanningEvalRunner": ProviderPlanningEvalRunner,
        }[name]
    raise AttributeError(name)

__all__ = [
    "FixtureCheckSummary",
    "FixtureVerifier",
    "PatchQualityEvidence",
    "PatchQualityResult",
    "PatchQualityScorer",
    "PlanQualityEvidence",
    "PlanQualityResult",
    "PlanQualityScorer",
    "ProviderComparisonResult",
    "ProviderComparisonScorer",
    "ProviderEvalEvidence",
    "BenchmarkReport",
    "BenchmarkReportBuilder",
    "OpenAICompatibleChatClient",
    "ProviderChatClient",
    "ProviderPlanningEvalRunner",
]
