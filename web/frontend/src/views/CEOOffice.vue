<template>
  <div class="ceo-office view-page">
    <section v-if="error" class="ceo-alert">{{ error }}</section>

    <section class="ceo-grid">
      <article class="ceo-panel conversation-panel">
        <header class="panel-head">
          <span>{{ t("ceoOffice.messages") }}</span>
          <small>{{ messages.length }}</small>
        </header>

        <div v-if="!messages.length" class="ceo-empty">{{ t("ceoOffice.noMessages") }}</div>
        <div v-else class="message-list">
          <div v-for="message in messages" :key="message.message_id" class="message-row" :class="message.role">
            <div class="message-meta">
              <strong>{{ message.role }}</strong>
              <span>{{ deskLabel(message.desk) }}</span>
              <time>{{ formatTime(message.created_at) }}</time>
            </div>
            <p>{{ message.content }}</p>
            <div v-if="message.evidence_refs.length" class="message-ref-list">
              <button
                v-for="evidenceId in message.evidence_refs"
                :key="`${message.message_id}-evidence-${evidenceId}`"
                class="btn btn-xs"
                type="button"
                @click="loadEvidence(evidenceId)"
              >
                {{ t("ceoOffice.openEvidence") }}
              </button>
            </div>
            <div v-if="message.action_refs.length" class="message-action-list">
              <div
                v-for="actionId in message.action_refs"
                :key="`${message.message_id}-inline-action-${actionId}`"
                class="inline-action-card"
                :class="{ selected: selectedAction?.action.action_id === actionId }"
              >
                <template v-if="actionById(actionId)">
                  <div class="action-title">
                    <strong>{{ actionById(actionId)?.summary }}</strong>
                    <span :class="['action-status', actionById(actionId)?.status || 'unknown']">
                      {{ statusLabel(actionById(actionId)?.status || "unknown") }}
                    </span>
                  </div>
                  <small>{{ deskLabel(actionById(actionId)?.desk || "") }} · {{ actionById(actionId)?.risk_level }}</small>
                  <div class="approval-buttons">
                    <button v-if="actionById(actionId)?.status === 'approval_required'" class="btn btn-xs" type="button" @click="approveAction(actionId)">
                      {{ t("ceoOffice.approved") }}
                    </button>
                    <button v-if="actionById(actionId)?.status === 'approval_required'" class="btn btn-xs btn-danger" type="button" @click="rejectAction(actionId)">
                      {{ t("ceoOffice.rejected") }}
                    </button>
                    <button
                      v-if="canSubmitPaperAction(actionById(actionId))"
                      class="btn btn-xs btn-primary"
                      type="button"
                      :disabled="submittingPaperAction === actionId"
                      @click="submitPaperAction(actionId)"
                    >
                      {{ t("ceoOffice.submitPaperOrder") }}
                    </button>
                    <button
                      v-if="canCancelAction(actionById(actionId))"
                      class="btn btn-xs btn-ghost"
                      type="button"
                      :disabled="cancelingAction === actionId"
                      @click="cancelAction(actionId)"
                    >
                      {{ t("ceoOffice.cancelAction") }}
                    </button>
                    <button class="btn btn-xs btn-ghost" type="button" @click="selectAction(actionId)">
                      {{ t("ceoOffice.viewDetails") }}
                    </button>
                  </div>
                </template>
              </div>
            </div>
            <div v-if="selectedAction && message.action_refs.includes(selectedAction.action.action_id)" class="inline-detail detail-stack">
              <div class="detail-row">
                <span>{{ t("ceoOffice.expectedEffect") }}</span>
                <p>{{ selectedAction.action.expected_effect || "—" }}</p>
              </div>
              <div class="detail-row">
                <span>{{ t("ceoOffice.expiresAt") }}</span>
                <code>{{ formatTime(selectedAction.action.expires_at) }}</code>
              </div>
              <details class="detail-row">
                <summary>{{ t("ceoOffice.parameters") }}</summary>
                <pre>{{ formatJson(selectedAction.action.parameters) }}</pre>
              </details>
              <div v-if="paperOrderPreview" class="detail-row">
                <span>{{ t("ceoOffice.paperOrderPreview") }}</span>
                <div class="paper-preview-grid">
                  <div class="paper-preview-cell">
                    <small>{{ t("ceoOffice.status") }}</small>
                    <strong>{{ statusLabel(String(paperOrderPreview.status || "unknown")) }}</strong>
                  </div>
                  <div class="paper-preview-cell">
                    <small>{{ t("ceoOffice.riskGate") }}</small>
                    <strong>{{ paperRiskGatePassed ? t("ceoOffice.passed") : t("ceoOffice.blocked") }}</strong>
                  </div>
                  <div class="paper-preview-cell">
                    <small>{{ t("ceoOffice.cashEffect") }}</small>
                    <strong>{{ formatNumber(paperOrderPreview.estimated_cash_effect) }}</strong>
                  </div>
                </div>
              </div>
              <div v-if="selectedAction.action.evidence_refs.length" class="detail-row">
                <span>{{ t("ceoOffice.evidenceRefs") }}</span>
                <div class="evidence-ref-list">
                  <button
                    v-for="evidenceId in selectedAction.action.evidence_refs"
                    :key="`${selectedAction.action.action_id}-${evidenceId}`"
                    class="btn btn-xs"
                    type="button"
                    @click="loadEvidence(evidenceId)"
                  >
                    {{ t("ceoOffice.openEvidence") }}
                  </button>
                </div>
              </div>
              <details v-if="selectedAction.runs.length" class="detail-row">
                <summary>{{ t("ceoOffice.runHistory") }}</summary>
                <div class="run-list">
                  <div v-for="run in selectedAction.runs" :key="run.run_id" class="run-row">
                    <strong>{{ statusLabel(run.status) }}</strong>
                    <small>{{ run.tool_name }} · {{ run.return_code ?? "—" }}</small>
                    <code>{{ run.command.join(" ") }}</code>
                    <p v-if="run.stdout_summary">{{ t("ceoOffice.stdout") }}: {{ run.stdout_summary }}</p>
                    <p v-if="run.stderr_summary">{{ t("ceoOffice.stderr") }}: {{ run.stderr_summary }}</p>
                    <div v-if="run.artifact_refs.length" class="run-evidence-list">
                      <small>{{ t("ceoOffice.runEvidence") }}</small>
                      <button
                        v-for="evidenceId in run.artifact_refs"
                        :key="`${run.run_id}-${evidenceId}`"
                        class="btn btn-xs"
                        type="button"
                        @click="loadEvidence(evidenceId)"
                      >
                        {{ t("ceoOffice.openEvidence") }}
                      </button>
                    </div>
                  </div>
                </div>
              </details>
            </div>
            <div v-if="selectedEvidence && messageHasSelectedEvidence(message)" class="inline-detail detail-stack">
              <strong>{{ selectedEvidence.label }}</strong>
              <p>{{ selectedEvidence.summary }}</p>
              <div v-if="selectedEvidenceNavigation" class="detail-row">
                <span>{{ t("ceoOffice.linkedView") }}</span>
                <a class="evidence-link" :href="selectedEvidenceNavigation.href">
                  {{ t("ceoOffice.openLinkedView") }}
                </a>
              </div>
              <details class="detail-row">
                <summary>{{ t("ceoOffice.evidenceDetail") }}</summary>
                <code>{{ selectedEvidence.uri }}</code>
                <code>{{ selectedEvidenceStatus || selectedEvidence.freshness_status }}</code>
                <code v-if="selectedEvidence.hash">{{ selectedEvidence.hash }}</code>
                <code v-if="selectedEvidenceSnapshot">{{ selectedEvidenceSnapshot.uri }}</code>
              </details>
            </div>
          </div>
        </div>

        <form class="message-composer" @submit.prevent="sendMessage">
          <div class="composer-input-row">
            <input v-model="draft" type="text" :placeholder="t('ceoOffice.messagePlaceholder')" />
            <button class="btn btn-primary" type="submit" :disabled="sending || !draft.trim()">
              {{ t("ceoOffice.send") }}
            </button>
          </div>
          <div v-if="modelRuntime" class="model-runtime-line composer-status-line" :aria-label="t('ceoOffice.modelRuntimeA11y')">
            <template v-for="(segment, index) in modelRuntimeSegments" :key="segment.key">
              <span v-if="index" class="runtime-separator">·</span>
              <span :class="['runtime-segment', `runtime-segment-${segment.kind}`]">
                <span
                  v-if="segment.kind === 'context-progress'"
                  class="runtime-progress"
                  :class="`runtime-progress-${segment.status}`"
                  role="meter"
                  :aria-valuenow="segment.progress"
                  aria-valuemin="0"
                  aria-valuemax="100"
                  :aria-label="`${t('ceoOffice.contextShort')} ${segment.progress}%`"
                >
                  <span
                    v-for="cell in runtimeBatteryCells"
                    :key="cell"
                    class="runtime-progress-cell"
                    :class="{ active: cell <= segment.cells }"
                  ></span>
                </span>
                <template v-else>{{ segment.text }}</template>
              </span>
            </template>
          </div>
        </form>
      </article>

    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { api, type AgentAction, type AgentActionDetail, type AgentEvidenceSnapshot, type AgentMessage, type AgentModelRuntimeResponse, type AgentSession, type EvidenceNavigation, type EvidenceRef } from "../api";
import { useI18n } from "../i18n";

const { t } = useI18n();

const sessions = ref<AgentSession[]>([]);
const activeSession = ref<AgentSession | null>(null);
const messages = ref<AgentMessage[]>([]);
const actions = ref<AgentAction[]>([]);
const sessionStream = ref<AbortController | null>(null);
const sessionStreamId = ref("");
const lastStreamSignature = ref("");
const runStream = ref<AbortController | null>(null);
const runStreamId = ref("");
const lastRunStreamSignature = ref("");
const modelRuntime = ref<AgentModelRuntimeResponse | null>(null);
const selectedAction = ref<AgentActionDetail | null>(null);
const selectedEvidence = ref<EvidenceRef | null>(null);
const selectedEvidenceSnapshot = ref<AgentEvidenceSnapshot | null>(null);
const selectedEvidenceNavigation = ref<EvidenceNavigation | null>(null);
const selectedEvidenceStatus = ref("");
const submittingPaperAction = ref("");
const cancelingAction = ref("");
const draft = ref("");
const sending = ref(false);
const error = ref("");

const paperOrderPreview = computed(() => objectParam(selectedAction.value?.action.parameters.paper_order_preview));
const paperRiskGate = computed(() => objectParam(paperOrderPreview.value?.risk_gate));
const paperRiskGatePassed = computed(() => Boolean(paperRiskGate.value?.passed));
const modelRuntimeSegments = computed(() => {
  if (!modelRuntime.value) return [];
  const label = modelRuntime.value.runtime.label || modelRuntime.value.runtime.provider;
  const model = modelRuntime.value.runtime.model || "—";
  return [
    { key: "provider", kind: "provider", text: label },
    { key: "model", kind: "model", text: model },
    { key: "reasoning", kind: "reasoning", text: `${t("ceoOffice.reasoningShort")} ${reasoningLevelShort(modelRuntime.value.reasoning.level)}` },
    { key: "context", kind: "context", text: t("ceoOffice.contextShort") },
    { key: "context-progress", kind: "context-progress", text: "", progress: contextUsagePct.value, cells: contextBatteryCells.value, status: contextStatusKind(modelRuntime.value.context.status) },
    { key: "context-max", kind: "context", text: formatTokenK(modelRuntime.value.context.max_tokens) },
  ];
});
const draftContextTokens = computed(() => estimateTextTokens(draft.value));
const contextUsedTokens = computed(() => (modelRuntime.value?.context.used_tokens || 0) + draftContextTokens.value);
const contextUsagePct = computed(() => {
  const maxTokens = modelRuntime.value?.context.max_tokens || 0;
  if (!maxTokens) return 0;
  return Math.min(100, Math.round((contextUsedTokens.value / maxTokens) * 10000) / 100);
});
const runtimeBatteryCells = [1, 2, 3, 4, 5, 6, 7, 8];
const contextBatteryCells = computed(() => Math.min(runtimeBatteryCells.length, Math.max(0, Math.ceil((contextUsagePct.value / 100) * runtimeBatteryCells.length))));

const deskNames = computed<Record<string, string>>(() => ({
  data: t("ceoOffice.dataDesk"),
  research: t("ceoOffice.researchDesk"),
  portfolio: t("ceoOffice.portfolioDesk"),
  risk: t("ceoOffice.riskDesk"),
  execution: t("ceoOffice.executionDesk"),
  engineering: t("ceoOffice.engineeringDesk"),
  reporting: t("ceoOffice.reportingDesk"),
}));

function deskLabel(desk: string) {
  return deskNames.value[desk] || desk;
}

function statusLabel(status: string) {
  if (status === "approval_required") return t("ceoOffice.approvalRequired");
  if (status === "approved") return t("ceoOffice.approved");
  if (status === "rejected") return t("ceoOffice.rejected");
  if (status === "proposed") return t("ceoOffice.proposed");
  if (status === "running") return t("ceoOffice.running");
  if (status === "succeeded") return t("ceoOffice.succeeded");
  if (status === "submitted") return t("ceoOffice.submitted");
  if (status === "order_canceled") return t("ceoOffice.orderCanceled");
  if (status === "queued_action_canceled") return t("ceoOffice.queuedActionCanceled");
  if (status === "failed") return t("ceoOffice.failed");
  if (status === "blocked") return t("ceoOffice.blocked");
  if (status === "canceled") return t("ceoOffice.canceled");
  if (status === "expired") return t("ceoOffice.expired");
  if (status === "unknown") return t("ceoOffice.unknown");
  if (status === "inactive") return t("ceoOffice.inactive");
  if (status === "connected") return t("ceoOffice.connected");
  if (status === "connecting") return t("ceoOffice.connecting");
  if (status === "dry_run") return t("ceoOffice.dryRun");
  if (status === "partial") return t("ceoOffice.partial");
  if (status === "missing_secret") return t("ceoOffice.missingSecret");
  return status;
}

function actionById(actionId: string) {
  return actions.value.find(action => action.action_id === actionId) || null;
}

function messageHasSelectedEvidence(message: AgentMessage) {
  const evidenceId = selectedEvidence.value?.evidence_id;
  if (!evidenceId) return false;
  if (message.evidence_refs.includes(evidenceId)) return true;
  if (!selectedAction.value || !message.action_refs.includes(selectedAction.value.action.action_id)) return false;
  return selectedAction.value.action.evidence_refs.includes(evidenceId);
}

function contextStatusKind(status: string) {
  const normalized = (status || "ok").toLowerCase();
  if (normalized === "warn") return "warn";
  if (normalized === "compacted") return "compacted";
  if (normalized === "blocked") return "blocked";
  return "ok";
}

function formatJson(value: Record<string, unknown>) {
  return JSON.stringify(value || {}, null, 2);
}

function isPaperAction(action: AgentAction | null | undefined) {
  return action?.action_type === "paper_order" && action?.risk_level === "paper_order";
}

function canSubmitPaperAction(action: AgentAction | null | undefined) {
  return Boolean(action && isPaperAction(action) && action.status === "approved");
}

function canCancelPaperOrder(action: AgentAction | null | undefined) {
  return Boolean(action && isPaperAction(action) && action.status === "succeeded");
}

function canCancelAction(action: AgentAction | null | undefined) {
  return Boolean(action && (["proposed", "approval_required", "approved"].includes(action.status) || canCancelPaperOrder(action)));
}

function formatTime(value: string) {
  if (!value) return "—";
  return value.replace("T", " ").replace("Z", "");
}

function objectParam(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : null;
}

function formatNumber(value: unknown) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return "—";
  return numeric.toLocaleString(undefined, { maximumFractionDigits: 2 });
}

function estimateTextTokens(value: string) {
  const text = value.trim();
  if (!text) return 0;
  return Math.max(1, Math.ceil(text.length / 4));
}

function formatTokenK(value: number) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric) || numeric < 0) return "—";
  return `${(numeric / 1000).toFixed(1)}k`;
}

function reasoningLevelShort(level: string) {
  if (level === "max") return t("ceoOffice.reasoningMaxShort");
  if (level === "xhigh") return t("ceoOffice.reasoningXHighShort");
  if (level === "high") return t("ceoOffice.reasoningHighShort");
  if (level === "mid") return t("ceoOffice.reasoningMidShort");
  if (level === "medium") return t("ceoOffice.reasoningMidShort");
  if (level === "low") return t("ceoOffice.reasoningLowShort");
  if (level === "thinking_enabled") return t("ceoOffice.reasoningThinkingShort");
  if (level === "thinking_disabled") return t("ceoOffice.reasoningOffShort");
  if (!level || level === "default") return t("ceoOffice.reasoningDefaultShort");
  return level;
}

function closeSessionStream() {
  sessionStream.value?.abort();
  sessionStream.value = null;
  sessionStreamId.value = "";
  lastStreamSignature.value = "";
}

function closeRunStream() {
  runStream.value?.abort();
  runStream.value = null;
  runStreamId.value = "";
  lastRunStreamSignature.value = "";
}

function connectSessionStream(sessionId: string) {
  if (sessionStream.value && sessionStreamId.value === sessionId) return;
  closeSessionStream();
  const controller = new AbortController();
  sessionStream.value = controller;
  sessionStreamId.value = sessionId;
  void api.agentSessionStream(
    sessionId,
    {
      onSnapshot: snapshot => {
        if (snapshot.signature === lastStreamSignature.value) return;
        lastStreamSignature.value = snapshot.signature;
        void loadSession(snapshot.session_id, { connectStream: false });
      },
      onMissing: () => {
        closeSessionStream();
      },
    },
    { signal: controller.signal },
  ).catch(err => {
    if (controller.signal.aborted) return;
    const name = err instanceof Error ? err.name : "";
    if (name === "AbortError") return;
  });
}

function connectRunStream(runId: string) {
  if (runStream.value && runStreamId.value === runId) return;
  closeRunStream();
  const controller = new AbortController();
  runStream.value = controller;
  runStreamId.value = runId;
  void api.agentRunStream(
    runId,
    {
      onSnapshot: snapshot => {
        if (snapshot.signature === lastRunStreamSignature.value) return;
        lastRunStreamSignature.value = snapshot.signature;
        if (!selectedAction.value || selectedAction.value.action.action_id !== snapshot.action_id) return;
        const nextRun = { ...snapshot.run, events: snapshot.events };
        const currentRuns = selectedAction.value.runs || [];
        const hasRun = currentRuns.some(run => run.run_id === snapshot.run_id);
        selectedAction.value = {
          ...selectedAction.value,
          runs: hasRun
            ? currentRuns.map(run => run.run_id === snapshot.run_id ? nextRun : run)
            : [nextRun, ...currentRuns],
        };
      },
      onMissing: () => {
        closeRunStream();
      },
    },
    { signal: controller.signal },
  ).catch(err => {
    if (controller.signal.aborted) return;
    const name = err instanceof Error ? err.name : "";
    if (name === "AbortError") return;
  });
}

async function loadSession(sessionId: string, options: { connectStream?: boolean } = {}) {
  const detail = await api.agentSession(sessionId);
  activeSession.value = detail.session;
  messages.value = detail.messages || [];
  actions.value = detail.actions || [];
  if (options.connectStream !== false) {
    connectSessionStream(sessionId);
  }
  await loadModelRuntime(sessionId);
}

async function loadOfficeState() {
  error.value = "";
  try {
    const [sessionPayload, actionPayload, modelRuntimePayload] = await Promise.all([
      api.agentSessions(),
      api.agentActions(),
      api.agentModelRuntime(),
    ]);
    sessions.value = sessionPayload.sessions || [];
    actions.value = actionPayload.actions || [];
    modelRuntime.value = modelRuntimePayload;
    if (sessions.value.length) {
      await loadSession(activeSession.value?.session_id || sessions.value[0].session_id);
    }
    if (selectedAction.value) {
      await selectAction(selectedAction.value.action.action_id);
    }
  } catch (err: any) {
    error.value = `${t("ceoOffice.loadFailed")}: ${err?.message || err}`;
  }
}

async function loadModelRuntime(sessionId = "") {
  modelRuntime.value = await api.agentModelRuntime(sessionId);
}

async function ensureSession(): Promise<AgentSession> {
  if (activeSession.value) return activeSession.value;
  const payload = await api.agentCreateSession({
    title: t("ceoOffice.defaultControlTitle"),
    default_desk: "reporting",
  });
  activeSession.value = payload.session;
  sessions.value = [payload.session, ...sessions.value];
  return payload.session;
}

async function sendMessage() {
  const text = draft.value.trim();
  if (!text) return;
  sending.value = true;
  error.value = "";
  try {
    const session = await ensureSession();
    await api.agentAddMessage(session.session_id, {
      role: "ceo",
      content: text,
    });
    draft.value = "";
    await loadSession(session.session_id);
  } catch (err: any) {
    error.value = `${t("ceoOffice.writeFailed")}: ${err?.message || err}`;
  } finally {
    sending.value = false;
  }
}

async function approveAction(actionId: string) {
  await api.agentApproveAction(actionId);
  await loadOfficeState();
}

async function rejectAction(actionId: string) {
  await api.agentRejectAction(actionId, "Rejected from CEO Office");
  await loadOfficeState();
}

async function cancelAction(actionId: string) {
  cancelingAction.value = actionId;
  error.value = "";
  try {
    const action = selectedAction.value?.action.action_id === actionId
      ? selectedAction.value.action
      : actions.value.find(item => item.action_id === actionId);
    if (isPaperAction(action)) {
      await api.agentPaperCancelAction(actionId, "Canceled from CEO Office");
    } else {
      await api.agentCancelAction(actionId, "Canceled from CEO Office");
    }
    await loadOfficeState();
  } catch (err: any) {
    error.value = `${t("ceoOffice.cancelFailed")}: ${err?.message || err}`;
  } finally {
    cancelingAction.value = "";
  }
}

async function selectAction(actionId: string) {
  error.value = "";
  try {
    selectedAction.value = await api.agentAction(actionId);
    const latestRun = selectedAction.value.runs?.[0];
    if (latestRun) {
      connectRunStream(latestRun.run_id);
    } else {
      closeRunStream();
    }
  } catch (err: any) {
    error.value = `${t("ceoOffice.loadFailed")}: ${err?.message || err}`;
  }
}

async function submitPaperAction(actionId: string) {
  submittingPaperAction.value = actionId;
  error.value = "";
  try {
    await api.agentPaperSubmitAction(actionId);
    await selectAction(actionId);
    await loadOfficeState();
  } catch (err: any) {
    error.value = `${t("ceoOffice.paperSubmitFailed")}: ${err?.message || err}`;
  } finally {
    submittingPaperAction.value = "";
  }
}

async function loadEvidence(evidenceId: string) {
  error.value = "";
  selectedEvidenceNavigation.value = null;
  selectedEvidenceSnapshot.value = null;
  selectedEvidenceStatus.value = "";
  try {
    const payload = await api.agentEvidence(evidenceId);
    selectedEvidence.value = payload.evidence;
    selectedEvidenceNavigation.value = payload.navigation;
    selectedEvidenceSnapshot.value = payload.snapshot;
    selectedEvidenceStatus.value = payload.status;
  } catch (err: any) {
    error.value = `${t("ceoOffice.evidenceLoadFailed")}: ${err?.message || err}`;
  }
}

onMounted(loadOfficeState);
onBeforeUnmount(closeSessionStream);
onBeforeUnmount(closeRunStream);
</script>

<style scoped src="../styles/views/ceo-office.css"></style>
