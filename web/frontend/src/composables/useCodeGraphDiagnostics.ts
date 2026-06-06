import { computed, ref, watch, type Ref } from "vue";
import { api } from "../api";
import type { CodeGraphDiagnosticsResponse, CodeGraphIssue, CodeGraphNodeRisk } from "../api";
import type { CodeGraphLevel, CodeGraphTranslate } from "./codegraph/types";

type SeverityFilter = "all" | "P0" | "P1" | "P2";

export function useCodeGraphDiagnostics(
  t: CodeGraphTranslate,
  level: Ref<CodeGraphLevel>,
  root: Ref<string>,
  graphVersion: Ref<number>,
  applyNodeRisks: (risks: Record<string, CodeGraphNodeRisk>) => void,
) {
  const diagnostics = ref<CodeGraphDiagnosticsResponse | null>(null);
  const isDiagnosticsLoading = ref(false);
  const diagnosticsError = ref("");
  const severityFilter = ref<SeverityFilter>("all");
  const categoryFilter = ref("all");

  const diagnosticsSummary = computed(() => diagnostics.value?.summary || null);
  const diagnosticCategories = computed(() => {
    const categories = new Set(diagnostics.value?.issues.map(issue => issue.category) || []);
    return ["all", ...Array.from(categories).sort()];
  });
  const filteredIssues = computed(() => (diagnostics.value?.issues || []).filter(issue => (
    (severityFilter.value === "all" || issue.severity === severityFilter.value)
    && (categoryFilter.value === "all" || issue.category === categoryFilter.value)
  )));
  const riskTone = computed(() => {
    const counts = diagnosticsSummary.value?.severity_counts || {};
    if (counts.P0) return "p0";
    if (counts.P1) return "p1";
    if (counts.P2) return "p2";
    return "clean";
  });

  async function loadDiagnostics() {
    isDiagnosticsLoading.value = true;
    diagnosticsError.value = "";
    try {
      const payload = await api.codeGraphDiagnostics({
        scope: diagnosticsScope(level.value),
        root: root.value,
        limit: 80,
        include_git: true,
      });
      diagnostics.value = payload;
      applyNodeRisks(payload.node_scores);
    } catch (error) {
      diagnosticsError.value = error instanceof Error ? error.message : t("codegraph.diagnosticsError");
    } finally {
      isDiagnosticsLoading.value = false;
    }
  }

  function categoryLabel(category: string) {
    return category === "all" ? t("codegraph.allCategories") : t(`codegraph.issueCategories.${category}`);
  }

  function severityLabel(severity: string) {
    return severity === "all" ? t("codegraph.allSeverities") : severity;
  }

  watch([level, root], () => {
    void loadDiagnostics();
  }, { immediate: true });

  watch(graphVersion, () => {
    if (diagnostics.value) applyNodeRisks(diagnostics.value.node_scores);
  });

  return {
    diagnostics,
    diagnosticsSummary,
    isDiagnosticsLoading,
    diagnosticsError,
    severityFilter,
    categoryFilter,
    diagnosticCategories,
    filteredIssues,
    riskTone,
    loadDiagnostics,
    categoryLabel,
    severityLabel,
  };
}

function diagnosticsScope(level: CodeGraphLevel): "summary" | "module" | "file" | "symbol" {
  if (level === "module") return "summary";
  if (level === "neighborhood") return "symbol";
  return level;
}

export type { CodeGraphIssue };
