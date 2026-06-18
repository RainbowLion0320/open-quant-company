<template>
  <div class="ceo-office view-page">
    <section v-if="error" class="ceo-alert">{{ error }}</section>
    <section v-if="slashNotice" class="ceo-notice">{{ slashNotice }}</section>

    <section class="desk-status-strip" :aria-label="t('ceoOffice.departmentStatusAria')">
      <article
        v-for="card in deskStatusCards"
        :key="card.deskId"
        :class="['desk-status-card', `desk-status-${card.state}`, `desk-color-${card.deskId}`]"
        :aria-label="`${card.label}: ${card.statusLabel}`"
      >
        <strong>{{ card.label }}</strong>
        <p>{{ card.description }}</p>
      </article>
    </section>

    <section class="ceo-grid">
      <article class="conversation-panel">
        <div v-if="!messages.length" class="ceo-empty">{{ t("ceoOffice.noMessages") }}</div>
        <div v-else class="message-list">
          <div v-for="message in messages" :key="message.message_id" class="message-row" :class="message.role">
            <div class="message-meta">
              <strong>{{ message.role }}</strong>
              <span v-if="message.role !== 'ceo'" :class="['message-desk-label', `desk-color-${message.desk}`]">{{ deskLabel(message.desk) }}</span>
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
          <div v-if="showSlashMenu && filteredSlashCommands.length" class="slash-command-menu">
            <button
              v-for="(command, index) in filteredSlashCommands"
              :key="command.name"
              type="button"
              class="slash-command-option"
              :class="{ selected: index === selectedSlashIndex }"
              :aria-selected="index === selectedSlashIndex"
              @click="selectSlashCommand(command.name)"
            >
              <code>{{ command.name }}</code>
              <span>{{ command.description }}</span>
            </button>
          </div>
          <div class="composer-input-row">
            <input v-model="draft" type="text" :placeholder="t('ceoOffice.messagePlaceholder')" @keydown="handleComposerKeydown" />
            <button class="btn btn-primary" type="submit" :disabled="sending || !draft.trim()">
              {{ t("ceoOffice.send") }}
            </button>
          </div>
        </form>
      </article>

    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { api, type AgentAction, type AgentActionDetail, type AgentDesk, type AgentEvidenceSnapshot, type AgentMessage, type AgentSession, type EvidenceNavigation, type EvidenceRef } from "../api";
import { useI18n } from "../i18n";

const { t } = useI18n();

const sessions = ref<AgentSession[]>([]);
const activeSession = ref<AgentSession | null>(null);
const messages = ref<AgentMessage[]>([]);
const actions = ref<AgentAction[]>([]);
const agentDesks = ref<AgentDesk[]>([]);
const sessionStream = ref<AbortController | null>(null);
const sessionStreamId = ref("");
const lastStreamSignature = ref("");
const runStream = ref<AbortController | null>(null);
const runStreamId = ref("");
const lastRunStreamSignature = ref("");
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
const slashNotice = ref("");
const selectedSlashIndex = ref(0);

const paperOrderPreview = computed(() => objectParam(selectedAction.value?.action.parameters.paper_order_preview));
const paperRiskGate = computed(() => objectParam(paperOrderPreview.value?.risk_gate));
const paperRiskGatePassed = computed(() => Boolean(paperRiskGate.value?.passed));
const deskOrder = ["data", "research", "portfolio", "risk", "execution", "engineering", "reporting"];
const slashCommands = computed(() => [
  { name: "/new", description: t("ceoOffice.slashNewDescription") },
  { name: "/clear", description: t("ceoOffice.slashClearDescription") },
  { name: "/help", description: t("ceoOffice.slashHelpDescription") },
]);
const deskNames = computed<Record<string, string>>(() => ({
  data: t("ceoOffice.dataDesk"),
  research: t("ceoOffice.researchDesk"),
  portfolio: t("ceoOffice.portfolioDesk"),
  risk: t("ceoOffice.riskDesk"),
  execution: t("ceoOffice.executionDesk"),
  engineering: t("ceoOffice.engineeringDesk"),
  reporting: t("ceoOffice.reportingDesk"),
}));
const deskDescriptions = computed<Record<string, string>>(() => ({
  data: t("ceoOffice.dataDeskBrief"),
  research: t("ceoOffice.researchDeskBrief"),
  portfolio: t("ceoOffice.portfolioDeskBrief"),
  risk: t("ceoOffice.riskDeskBrief"),
  execution: t("ceoOffice.executionDeskBrief"),
  engineering: t("ceoOffice.engineeringDeskBrief"),
  reporting: t("ceoOffice.reportingDeskBrief"),
}));
const deskRegistryById = computed<Record<string, AgentDesk>>(() =>
  Object.fromEntries(agentDesks.value.map(desk => [desk.desk_id, desk])),
);
const currentSessionActions = computed(() => {
  const sessionId = activeSession.value?.session_id || "";
  if (!sessionId) return [];
  return actions.value.filter(action => action.session_id === sessionId);
});
const deskStatusCards = computed(() =>
  deskOrder.map(deskId => {
    const state = deskCardState(deskId);
    return {
      deskId,
      state,
      label: deskLabel(deskId),
      description: deskDescriptions.value[deskId],
      statusLabel: deskStateLabel(state),
    };
  }),
);
const slashCommandQuery = computed(() => draft.value.trim().toLowerCase());
const slashSearchText = computed(() => slashCommandQuery.value.replace(/^\/+/, ""));
const showSlashMenu = computed(() => slashCommandQuery.value.startsWith("/"));
const filteredSlashCommands = computed(() => {
  const query = slashSearchText.value;
  return slashCommands.value
    .map(command => ({ command, rank: slashCommandRank(command, query) }))
    .filter(row => slashMatchesCommand(row.command, query))
    .sort((left, right) => left.rank - right.rank || left.command.name.localeCompare(right.command.name))
    .map(row => row.command);
});
const selectedSlashCommand = computed(() => filteredSlashCommands.value[selectedSlashIndex.value] || null);

function deskLabel(desk: string) {
  return deskNames.value[desk] || desk;
}

function slashMatchesCommand(command: { name: string; description: string }, query: string) {
  return Number.isFinite(slashCommandRank(command, query));
}

function slashCommandRank(command: { name: string; description: string }, query: string) {
  if (!query) return 0;
  const name = command.name.toLowerCase().replace(/^\/+/, "");
  const description = command.description.toLowerCase();
  if (name.startsWith(query)) return 1;
  if (name.includes(query)) return 2;
  let cursor = 0;
  for (const char of name) {
    if (char === query[cursor]) cursor += 1;
    if (cursor === query.length) return 3;
  }
  if (description.includes(query)) return 4;
  return Number.POSITIVE_INFINITY;
}

function deskCardState(deskId: string) {
  const registry = deskRegistryById.value[deskId];
  if (!registry || registry.status !== "available") return "unavailable";
  const relatedActions = currentSessionActions.value.filter(action => action.desk === deskId);
  if (relatedActions.some(action => action.status === "failed" || action.status === "blocked")) return "failed";
  if (relatedActions.some(action => action.status === "running")) return "running";
  return "standby";
}

function deskStateLabel(state: string) {
  if (state === "running") return t("ceoOffice.departmentStateRunning");
  if (state === "failed") return t("ceoOffice.departmentStateFailed");
  if (state === "unavailable") return t("ceoOffice.departmentStateUnavailable");
  return t("ceoOffice.departmentStateStandby");
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
  notifyModelRuntimeSession(sessionId);
  if (options.connectStream !== false) {
    connectSessionStream(sessionId);
  }
}

async function loadOfficeState() {
  error.value = "";
  try {
    const [sessionPayload, actionPayload, deskPayload] = await Promise.all([
      api.agentSessions(),
      api.agentActions(),
      api.agentDesks().catch(() => ({ desks: [] })),
    ]);
    sessions.value = sessionPayload.sessions || [];
    actions.value = actionPayload.actions || [];
    agentDesks.value = deskPayload.desks || [];
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

function notifyModelRuntimeSession(sessionId: string) {
  window.dispatchEvent(new CustomEvent("oqc-agent-runtime-session", { detail: { sessionId } }));
}

watch(slashCommandQuery, () => {
  selectedSlashIndex.value = 0;
});

watch(filteredSlashCommands, commands => {
  if (!commands.length) {
    selectedSlashIndex.value = 0;
    return;
  }
  if (selectedSlashIndex.value >= commands.length) {
    selectedSlashIndex.value = commands.length - 1;
  }
});

async function createFreshSession() {
  const payload = await api.agentCreateSession({
    title: t("ceoOffice.defaultControlTitle"),
    default_desk: "reporting",
  });
  activeSession.value = payload.session;
  sessions.value = [payload.session, ...sessions.value];
  messages.value = [];
  actions.value = [];
  selectedAction.value = null;
  selectedEvidence.value = null;
  selectedEvidenceSnapshot.value = null;
  selectedEvidenceNavigation.value = null;
  selectedEvidenceStatus.value = "";
  await loadSession(payload.session.session_id);
  return payload.session;
}

async function ensureSession(): Promise<AgentSession> {
  if (activeSession.value) return activeSession.value;
  return createFreshSession();
}

function selectSlashCommand(commandName: string) {
  draft.value = commandName;
}

function completeSlashCommand() {
  if (!selectedSlashCommand.value) return false;
  draft.value = selectedSlashCommand.value.name;
  return true;
}

function moveSlashSelection(delta: number) {
  const count = filteredSlashCommands.value.length;
  if (!count) return;
  selectedSlashIndex.value = (selectedSlashIndex.value + delta + count) % count;
}

function handleComposerKeydown(event: KeyboardEvent) {
  if (!showSlashMenu.value) return;
  if (event.key === "ArrowDown") {
    event.preventDefault();
    moveSlashSelection(1);
    return;
  }
  if (event.key === "ArrowUp") {
    event.preventDefault();
    moveSlashSelection(-1);
    return;
  }
  if (event.key === "Tab") {
    if (!selectedSlashCommand.value) return;
    event.preventDefault();
    completeSlashCommand();
    return;
  }
  if (event.key === "Enter" && selectedSlashCommand.value && slashCommandQuery.value !== selectedSlashCommand.value.name) {
    event.preventDefault();
    draft.value = selectedSlashCommand.value.name;
    void sendMessage();
  }
}

async function runSlashCommand(commandName: string) {
  if (commandName === "/new") {
    await createFreshSession();
    draft.value = "";
    return true;
  }
  if (commandName === "/clear") {
    if (activeSession.value) {
      await api.agentUpdateSession(activeSession.value.session_id, { status: "archived" });
    }
    await createFreshSession();
    draft.value = "";
    return true;
  }
  if (commandName === "/help") {
    slashNotice.value = t("ceoOffice.slashHelpMessage");
    draft.value = "";
    return true;
  }
  error.value = `${t("ceoOffice.unknownSlashCommand")}: ${commandName}`;
  slashNotice.value = "";
  return true;
}

async function sendMessage() {
  const text = draft.value.trim();
  if (!text) return;
  sending.value = true;
  error.value = "";
  slashNotice.value = "";
  try {
    if (text.startsWith("/")) {
      await runSlashCommand(text.toLowerCase());
      return;
    }
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
