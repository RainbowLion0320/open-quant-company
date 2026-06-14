<template>
  <div class="ceo-office view-page">
    <section class="ceo-toolbar">
      <div>
        <p class="eyebrow">{{ t("ceoOffice.subtitle") }}</p>
        <h2>{{ t("ceoOffice.title") }}</h2>
      </div>
      <div class="ceo-actions">
        <button class="btn btn-ghost" type="button" @click="load">{{ t("ceoOffice.refresh") }}</button>
        <button
          v-if="activeSession && activeSession.status !== 'archived'"
          class="btn btn-ghost"
          type="button"
          :disabled="archivingSession"
          @click="archiveSession"
        >
          {{ t("ceoOffice.archiveSession") }}
        </button>
        <button class="btn btn-primary" type="button" @click="createSession">{{ t("ceoOffice.createSession") }}</button>
      </div>
    </section>

    <section v-if="error" class="ceo-alert">{{ error }}</section>

    <section class="ceo-summary">
      <article class="ceo-metric">
        <span>{{ t("ceoOffice.session") }}</span>
        <strong>{{ activeSession?.title || t("ceoOffice.noSession") }}</strong>
        <small v-if="activeSession">{{ statusLabel(activeSession.status) }}</small>
      </article>
      <article class="ceo-metric">
        <span>{{ t("ceoOffice.deskStatus") }}</span>
        <strong>{{ desks.length }}</strong>
      </article>
      <article class="ceo-metric">
        <span>{{ t("ceoOffice.actionQueue") }}</span>
        <strong>{{ pendingActions.length }}</strong>
      </article>
      <article class="ceo-metric">
        <span>{{ t("ceoOffice.handoffs") }}</span>
        <strong>{{ handoffs.length }}</strong>
      </article>
      <article class="ceo-metric">
        <span>{{ t("ceoOffice.evidence") }}</span>
        <strong>{{ evidenceCount }}</strong>
      </article>
      <article class="ceo-metric">
        <span>{{ t("ceoOffice.reports") }}</span>
        <strong>{{ reports.length }}</strong>
      </article>
      <article class="ceo-metric">
        <span>{{ t("ceoOffice.liveReadiness") }}</span>
        <strong>{{ statusLabel(liveReadiness?.mode || "unknown") }}</strong>
        <small>{{ liveReadiness?.paper_fallback === false ? t("ceoOffice.noPaperFallback") : "—" }}</small>
      </article>
    </section>

    <section class="ceo-grid">
      <article class="ceo-panel conversation-panel">
        <header class="panel-head">
          <span>{{ t("ceoOffice.messages") }}</span>
          <small>{{ activeSession?.session_id || "—" }}</small>
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
          </div>
        </div>

        <form class="message-composer" @submit.prevent="sendMessage">
          <input v-model="draft" type="text" :placeholder="t('ceoOffice.messagePlaceholder')" />
          <button class="btn btn-primary" type="submit" :disabled="sending || !draft.trim()">
            {{ t("ceoOffice.send") }}
          </button>
        </form>
      </article>

      <aside class="ceo-side">
        <article class="ceo-panel">
          <header class="panel-head">
            <span>{{ t("ceoOffice.deskStatus") }}</span>
            <small>{{ desks.length }}</small>
          </header>
          <div class="desk-list">
            <div v-for="desk in desks" :key="desk.desk_id" class="desk-row">
              <span class="status-dot" :class="desk.status"></span>
              <div>
                <strong>{{ deskLabel(desk.desk_id) }}</strong>
                <small>{{ desk.allowed_tools.length }} tools</small>
              </div>
            </div>
          </div>
        </article>

        <article class="ceo-panel">
          <header class="panel-head">
            <span>{{ t("ceoOffice.handoffs") }}</span>
            <small>{{ handoffs.length }}</small>
          </header>
          <div v-if="!handoffs.length" class="ceo-empty">{{ t("ceoOffice.noHandoffs") }}</div>
          <div v-else class="handoff-list">
            <div v-for="handoff in handoffs" :key="handoff.handoff_id" class="handoff-row">
              <div class="handoff-route">
                <strong>{{ deskLabel(handoff.source_desk) }}</strong>
                <span>→</span>
                <strong>{{ deskLabel(handoff.target_desk) }}</strong>
              </div>
              <p>{{ handoff.reason }}</p>
              <small>{{ statusLabel(handoff.status) }} · {{ formatTime(handoff.created_at) }}</small>
              <div v-if="handoff.status === 'open'" class="handoff-actions">
                <button
                  class="btn btn-xs"
                  type="button"
                  :disabled="resolvingHandoff === handoff.handoff_id"
                  @click="resolveHandoff(handoff.handoff_id)"
                >
                  {{ t("ceoOffice.resolveHandoff") }}
                </button>
              </div>
            </div>
          </div>
        </article>

        <article class="ceo-panel">
          <header class="panel-head">
            <span>{{ t("ceoOffice.liveReadiness") }}</span>
            <small>{{ liveReadiness?.broker || "—" }}</small>
          </header>
          <div v-if="!liveReadiness" class="ceo-empty">{{ t("ceoOffice.noLiveReadiness") }}</div>
          <div v-else class="detail-stack">
            <div class="detail-row">
              <span>{{ t("ceoOffice.liveMode") }}</span>
              <code>{{ liveReadiness.mode }}</code>
            </div>
            <div class="detail-row">
              <span>{{ t("ceoOffice.noPaperFallback") }}</span>
              <code>{{ String(liveReadiness.paper_fallback === false) }}</code>
            </div>
            <div class="detail-row">
              <span>{{ t("ceoOffice.blockers") }}</span>
              <div v-if="!liveReadiness.blockers.length" class="ceo-empty compact">
                {{ t("ceoOffice.noBlockers") }}
              </div>
              <div v-else class="run-list">
                <div v-for="blocker in liveReadiness.blockers" :key="blocker" class="run-row">
                  <strong>{{ blocker }}</strong>
                </div>
              </div>
            </div>
          </div>
        </article>

        <article class="ceo-panel">
          <header class="panel-head">
            <span>{{ t("ceoOffice.reports") }}</span>
            <div class="report-toolbar">
              <label>
                <span>{{ t("ceoOffice.reportKind") }}</span>
                <select v-model="selectedReportKind" :disabled="generatingReport">
                  <option v-for="option in reportKindOptions" :key="option.value" :value="option.value">
                    {{ option.label }}
                  </option>
                </select>
              </label>
              <button class="btn btn-xs" type="button" :disabled="generatingReport" @click="generateReport">
                {{ t("ceoOffice.generateReport") }}
              </button>
              <button class="btn btn-xs btn-ghost" type="button" :disabled="runningRhythm" @click="runReportRhythm">
                {{ t("ceoOffice.runRhythm") }}
              </button>
            </div>
          </header>
          <div v-if="rhythmResult" class="rhythm-status">
            <span>{{ t("ceoOffice.rhythmStatus") }}</span>
            <strong>
              {{ t("ceoOffice.generated") }} {{ rhythmResult.generated_count }} ·
              {{ t("ceoOffice.skipped") }} {{ rhythmResult.skipped_count }}
            </strong>
            <small>{{ rhythmResult.checked_at }}</small>
          </div>
          <div v-if="!reports.length" class="ceo-empty">{{ t("ceoOffice.noReports") }}</div>
          <div v-else class="report-list">
            <div v-for="report in reports" :key="report.report_id" class="report-row">
              <div class="action-title">
                <strong>{{ report.title }}</strong>
                <span>{{ formatTime(report.generated_at) }}</span>
              </div>
              <p>{{ report.summary }}</p>
              <small>{{ report.kind }} · {{ report.evidence_refs.length }} evidence refs</small>
              <div class="approval-buttons">
                <button class="btn btn-xs" type="button" @click="loadEvidence(report.evidence_id)">
                  {{ t("ceoOffice.openEvidence") }}
                </button>
              </div>
            </div>
          </div>
        </article>

        <article class="ceo-panel">
          <header class="panel-head">
            <span>{{ t("ceoOffice.actionQueue") }}</span>
            <small>{{ actions.length }}</small>
          </header>
          <div v-if="!actions.length" class="ceo-empty">{{ t("ceoOffice.noActions") }}</div>
          <div v-else class="action-list">
            <div v-for="action in actions" :key="action.action_id" class="action-row" :class="{ selected: selectedAction?.action.action_id === action.action_id }">
              <div class="action-title">
                <strong>{{ action.summary }}</strong>
                <span :class="['action-status', action.status]">{{ statusLabel(action.status) }}</span>
              </div>
              <small>{{ deskLabel(action.desk) }} · {{ action.risk_level }}</small>
              <button class="btn btn-xs" type="button" @click="selectAction(action.action_id)">
                {{ t("ceoOffice.viewDetails") }}
              </button>
              <div v-if="action.status === 'approval_required' || canCancelAction(action)" class="approval-buttons">
                <button v-if="action.status === 'approval_required'" class="btn btn-xs" type="button" @click="approveAction(action.action_id)">
                  {{ t("ceoOffice.approved") }}
                </button>
                <button v-if="action.status === 'approval_required'" class="btn btn-xs btn-danger" type="button" @click="rejectAction(action.action_id)">
                  {{ t("ceoOffice.rejected") }}
                </button>
                <button
                  v-if="canSubmitPaperAction(action)"
                  class="btn btn-xs btn-primary"
                  type="button"
                  :disabled="submittingPaperAction === action.action_id"
                  @click="submitPaperAction(action.action_id)"
                >
                  {{ t("ceoOffice.submitPaperOrder") }}
                </button>
                <button
                  v-if="canCancelAction(action)"
                  class="btn btn-xs btn-ghost"
                  type="button"
                  :disabled="cancelingAction === action.action_id"
                  @click="cancelAction(action.action_id)"
                >
                  {{ t("ceoOffice.cancelAction") }}
                </button>
              </div>
            </div>
          </div>
        </article>

        <article class="ceo-panel">
          <header class="panel-head">
            <span>{{ t("ceoOffice.actionDetail") }}</span>
            <small>{{ selectedAction?.action.action_id || "—" }}</small>
          </header>
          <div v-if="!selectedAction" class="ceo-empty">{{ t("ceoOffice.noActions") }}</div>
          <div v-else class="detail-stack">
            <div class="detail-row">
              <span>{{ t("ceoOffice.expectedEffect") }}</span>
              <p>{{ selectedAction.action.expected_effect || "—" }}</p>
            </div>
            <div class="detail-row">
              <span>{{ t("ceoOffice.expiresAt") }}</span>
              <code>{{ formatTime(selectedAction.action.expires_at) }}</code>
            </div>
            <div class="detail-row">
              <span>{{ t("ceoOffice.parameters") }}</span>
              <pre>{{ formatJson(selectedAction.action.parameters) }}</pre>
            </div>
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
              <div class="paper-blockers">
                <small>{{ t("ceoOffice.blockers") }}</small>
                <span v-if="!paperRiskBlockers.length">{{ t("ceoOffice.noBlockers") }}</span>
                <code v-for="blocker in paperRiskBlockers" :key="blocker">{{ blocker }}</code>
              </div>
            </div>
            <div v-if="paperReconciliationSummary" class="detail-row">
              <span>{{ t("ceoOffice.paperReconciliation") }}</span>
              <div class="paper-preview-grid paper-reconciliation-grid">
                <div class="paper-preview-cell">
                  <small>{{ t("ceoOffice.status") }}</small>
                  <strong>{{ statusLabel(paperReconciliationSummary.status) }}</strong>
                </div>
                <div class="paper-preview-cell">
                  <small>{{ t("ceoOffice.orderId") }}</small>
                  <strong>{{ paperReconciliationSummary.orderId || "—" }}</strong>
                </div>
                <div class="paper-preview-cell">
                  <small>{{ t("ceoOffice.cashAfter") }}</small>
                  <strong>{{ formatNumber(paperReconciliationSummary.cashAfter) }}</strong>
                </div>
                <div class="paper-preview-cell">
                  <small>{{ t("ceoOffice.marketValueAfter") }}</small>
                  <strong>{{ formatNumber(paperReconciliationSummary.marketValueAfter) }}</strong>
                </div>
              </div>
              <div v-if="paperReconciliationSummary.error" class="paper-blockers">
                <small>{{ t("ceoOffice.stderr") }}</small>
                <code>{{ paperReconciliationSummary.error }}</code>
              </div>
            </div>
            <div class="detail-row">
              <span>{{ t("ceoOffice.evidenceRefs") }}</span>
              <div v-if="!selectedAction.action.evidence_refs.length" class="ceo-empty compact">
                {{ t("ceoOffice.noEvidence") }}
              </div>
              <div v-else class="evidence-ref-list">
                <button
                  v-for="evidenceId in selectedAction.action.evidence_refs"
                  :key="evidenceId"
                  class="btn btn-xs"
                  type="button"
                  @click="loadEvidence(evidenceId)"
                >
                  {{ t("ceoOffice.openEvidence") }}
                </button>
              </div>
            </div>
            <div class="approval-buttons">
              <button
                v-if="canSubmitPaperAction(selectedAction.action)"
                class="btn btn-xs btn-primary"
                type="button"
                :disabled="submittingPaperAction === selectedAction.action.action_id"
                @click="submitPaperAction(selectedAction.action.action_id)"
              >
                {{ t("ceoOffice.submitPaperOrder") }}
              </button>
              <button
                v-else
                class="btn btn-xs"
                type="button"
                :disabled="runningAction === selectedAction.action.action_id || !canRunAction(selectedAction.action)"
                @click="runAction(selectedAction.action.action_id)"
              >
                {{ t("ceoOffice.runAction") }}
              </button>
              <button
                v-if="canCancelAction(selectedAction.action)"
                class="btn btn-xs btn-ghost"
                type="button"
                :disabled="cancelingAction === selectedAction.action.action_id"
                @click="cancelAction(selectedAction.action.action_id)"
              >
                {{ t("ceoOffice.cancelAction") }}
              </button>
            </div>
            <div class="detail-row">
              <span>{{ t("ceoOffice.runHistory") }}</span>
              <div v-if="!selectedAction.runs.length" class="ceo-empty compact">
                {{ t("ceoOffice.noRuns") }}
              </div>
              <div v-else class="run-list">
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
            </div>
          </div>
        </article>

        <article class="ceo-panel">
          <header class="panel-head">
            <span>{{ t("ceoOffice.evidenceDetail") }}</span>
            <small>{{ selectedEvidence?.evidence_id || "—" }}</small>
          </header>
          <div v-if="!selectedEvidence" class="ceo-empty">{{ t("ceoOffice.noEvidence") }}</div>
          <div v-else class="detail-stack">
            <strong>{{ selectedEvidence.label }}</strong>
            <p>{{ selectedEvidence.summary }}</p>
            <div class="detail-row">
              <span>{{ t("ceoOffice.uri") }}</span>
              <code>{{ selectedEvidence.uri }}</code>
            </div>
            <div v-if="selectedEvidenceNavigation" class="detail-row">
              <span>{{ t("ceoOffice.linkedView") }}</span>
              <a class="evidence-link" :href="selectedEvidenceNavigation.href">
                {{ t("ceoOffice.openLinkedView") }}
              </a>
            </div>
            <div class="detail-row">
              <span>{{ t("ceoOffice.freshness") }}</span>
              <code>{{ selectedEvidenceStatus || selectedEvidence.freshness_status }}</code>
            </div>
            <div v-if="selectedEvidence.hash" class="detail-row">
              <span>{{ t("ceoOffice.sourceHash") }}</span>
              <code>{{ selectedEvidence.hash }}</code>
            </div>
            <div v-if="selectedEvidence.current_hash" class="detail-row">
              <span>{{ t("ceoOffice.currentHash") }}</span>
              <code>{{ selectedEvidence.current_hash }}</code>
            </div>
            <div v-if="selectedEvidenceSnapshot" class="detail-row">
              <span>{{ t("ceoOffice.evidenceSnapshot") }}</span>
              <code>{{ selectedEvidenceSnapshot.uri }}</code>
            </div>
          </div>
        </article>
      </aside>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { api, type AgentAction, type AgentActionDetail, type AgentDesk, type AgentEvidenceSnapshot, type AgentHandoff, type AgentLiveReadiness, type AgentMessage, type AgentReport, type AgentReportRhythm, type AgentSession, type EvidenceNavigation, type EvidenceRef } from "../api";
import { useI18n } from "../i18n";

const { t } = useI18n();

const sessions = ref<AgentSession[]>([]);
const activeSession = ref<AgentSession | null>(null);
const messages = ref<AgentMessage[]>([]);
const actions = ref<AgentAction[]>([]);
const handoffs = ref<AgentHandoff[]>([]);
const reports = ref<AgentReport[]>([]);
const rhythmResult = ref<AgentReportRhythm | null>(null);
const liveReadiness = ref<AgentLiveReadiness | null>(null);
const desks = ref<AgentDesk[]>([]);
const selectedAction = ref<AgentActionDetail | null>(null);
const selectedEvidence = ref<EvidenceRef | null>(null);
const selectedEvidenceSnapshot = ref<AgentEvidenceSnapshot | null>(null);
const selectedEvidenceNavigation = ref<EvidenceNavigation | null>(null);
const selectedEvidenceStatus = ref("");
const runningAction = ref("");
const submittingPaperAction = ref("");
const cancelingAction = ref("");
const archivingSession = ref(false);
const resolvingHandoff = ref("");
const generatingReport = ref(false);
const runningRhythm = ref(false);
const selectedReportKind = ref("daily_brief");
const draft = ref("");
const sending = ref(false);
const error = ref("");

const pendingActions = computed(() => actions.value.filter(action => action.status === "approval_required"));
const evidenceCount = computed(() => [
  ...messages.value.flatMap(message => message.evidence_refs || []),
  ...actions.value.flatMap(action => action.evidence_refs || []),
].length);
const paperOrderPreview = computed(() => objectParam(selectedAction.value?.action.parameters.paper_order_preview));
const paperRiskGate = computed(() => objectParam(paperOrderPreview.value?.risk_gate));
const paperRiskGatePassed = computed(() => Boolean(paperRiskGate.value?.passed));
const paperRiskBlockers = computed(() => arrayParam(paperRiskGate.value?.blockers));
const paperReconciliation = computed(() => selectedAction.value?.paper_reconciliations?.[0] || null);
const paperReconciliationSummary = computed(() => {
  const reconciliation = paperReconciliation.value;
  const account = objectParam(reconciliation?.account_after);
  if (!reconciliation || !account) return null;
  return {
    status: String(reconciliation.status || "unknown"),
    orderId: String(reconciliation.order_id || ""),
    cashAfter: account.cash,
    marketValueAfter: account.market_value,
    error: String(reconciliation.error || ""),
  };
});
const reportKindOptions = computed(() => [
  { value: "daily_brief", label: t("ceoOffice.dailyBrief") },
  { value: "weekly_review", label: t("ceoOffice.weeklyReview") },
  { value: "audit_pack", label: t("ceoOffice.auditPack") },
  { value: "data_quality_review", label: t("ceoOffice.dataQualityReport") },
  { value: "risk_review", label: t("ceoOffice.riskReport") },
  { value: "execution_reconciliation", label: t("ceoOffice.executionReconciliation") },
  { value: "engineering_digest", label: t("ceoOffice.engineeringDigest") },
  { value: "release_audit", label: t("ceoOffice.releaseAudit") },
]);

const deskNames = computed<Record<string, string>>(() => ({
  data: t("ceoOffice.dataDesk"),
  research: t("ceoOffice.researchDesk"),
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
  if (status === "live_disabled") return t("ceoOffice.liveDisabled");
  if (status === "live_ready") return t("ceoOffice.liveReady");
  if (status === "unknown") return t("ceoOffice.unknown");
  if (status === "archived") return t("ceoOffice.archived");
  if (status === "active") return t("ceoOffice.active");
  if (status === "open") return t("ceoOffice.open");
  if (status === "resolved") return t("ceoOffice.resolved");
  return status;
}

function formatJson(value: Record<string, unknown>) {
  return JSON.stringify(value || {}, null, 2);
}

function canRunAction(action: AgentAction) {
  return ["proposed", "approved"].includes(action.status) && action.action_type !== "paper_order";
}

function isPaperAction(action: AgentAction | null | undefined) {
  return action?.action_type === "paper_order" && action?.risk_level === "paper_order";
}

function canSubmitPaperAction(action: AgentAction) {
  return isPaperAction(action) && action.status === "approved";
}

function canCancelAction(action: AgentAction) {
  return ["proposed", "approval_required", "approved"].includes(action.status) || (isPaperAction(action) && action.status === "succeeded");
}

function formatTime(value: string) {
  if (!value) return "—";
  return value.replace("T", " ").replace("Z", "");
}

function objectParam(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : null;
}

function arrayParam(value: unknown): string[] {
  return Array.isArray(value) ? value.map(item => String(item)).filter(Boolean) : [];
}

function formatNumber(value: unknown) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return "—";
  return numeric.toLocaleString(undefined, { maximumFractionDigits: 2 });
}

async function loadSession(sessionId: string) {
  const [detail, reportPayload] = await Promise.all([api.agentSession(sessionId), api.agentReports(sessionId)]);
  activeSession.value = detail.session;
  messages.value = detail.messages || [];
  actions.value = detail.actions || [];
  handoffs.value = detail.handoffs || [];
  reports.value = reportPayload.reports || [];
}

async function load() {
  error.value = "";
  try {
    const [sessionPayload, deskPayload, actionPayload, handoffPayload, livePayload] = await Promise.all([
      api.agentSessions(),
      api.agentDesks(),
      api.agentActions(),
      api.agentHandoffs(),
      api.agentLiveReadiness(),
    ]);
    sessions.value = sessionPayload.sessions || [];
    desks.value = deskPayload.desks || [];
    actions.value = actionPayload.actions || [];
    handoffs.value = handoffPayload.handoffs || [];
    liveReadiness.value = livePayload.health;
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

async function createSession() {
  error.value = "";
  try {
    const payload = await api.agentCreateSession({
      title: t("ceoOffice.defaultSessionTitle"),
      default_desk: "reporting",
    });
    activeSession.value = payload.session;
    sessions.value = [payload.session, ...sessions.value];
    messages.value = [];
    await load();
  } catch (err: any) {
    error.value = `${t("ceoOffice.writeFailed")}: ${err?.message || err}`;
  }
}

async function archiveSession() {
  if (!activeSession.value) return;
  archivingSession.value = true;
  error.value = "";
  try {
    await api.agentUpdateSession(activeSession.value.session_id, { status: "archived" });
    await load();
  } catch (err: any) {
    error.value = `${t("ceoOffice.archiveFailed")}: ${err?.message || err}`;
  } finally {
    archivingSession.value = false;
  }
}

async function ensureSession(): Promise<AgentSession> {
  if (activeSession.value) return activeSession.value;
  const payload = await api.agentCreateSession({
    title: t("ceoOffice.defaultSessionTitle"),
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
      desk: "reporting",
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
  await load();
}

async function rejectAction(actionId: string) {
  await api.agentRejectAction(actionId, "Rejected from CEO Office");
  await load();
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
    await load();
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
  } catch (err: any) {
    error.value = `${t("ceoOffice.loadFailed")}: ${err?.message || err}`;
  }
}

async function runAction(actionId: string) {
  runningAction.value = actionId;
  error.value = "";
  try {
    await api.agentRunAction(actionId);
    await selectAction(actionId);
    await load();
  } catch (err: any) {
    error.value = `${t("ceoOffice.runFailed")}: ${err?.message || err}`;
  } finally {
    runningAction.value = "";
  }
}

async function submitPaperAction(actionId: string) {
  submittingPaperAction.value = actionId;
  error.value = "";
  try {
    await api.agentPaperSubmitAction(actionId);
    await selectAction(actionId);
    await load();
  } catch (err: any) {
    error.value = `${t("ceoOffice.paperSubmitFailed")}: ${err?.message || err}`;
  } finally {
    submittingPaperAction.value = "";
  }
}

async function generateReport() {
  generatingReport.value = true;
  error.value = "";
  try {
    const session = await ensureSession();
    const payload = await api.agentGenerateReport({ kind: selectedReportKind.value, session_id: session.session_id });
    reports.value = [payload.report, ...reports.value.filter(report => report.report_id !== payload.report.report_id)];
    await loadEvidence(payload.report.evidence_id);
    await loadSession(session.session_id);
  } catch (err: any) {
    error.value = `${t("ceoOffice.reportFailed")}: ${err?.message || err}`;
  } finally {
    generatingReport.value = false;
  }
}

async function runReportRhythm() {
  runningRhythm.value = true;
  error.value = "";
  try {
    const session = await ensureSession();
    const payload = await api.agentRunReportRhythm({ session_id: session.session_id });
    rhythmResult.value = payload.rhythm;
    await loadSession(session.session_id);
  } catch (err: any) {
    error.value = `${t("ceoOffice.rhythmFailed")}: ${err?.message || err}`;
  } finally {
    runningRhythm.value = false;
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

async function resolveHandoff(handoffId: string) {
  resolvingHandoff.value = handoffId;
  error.value = "";
  try {
    await api.agentResolveHandoff(handoffId);
    await load();
  } catch (err: any) {
    error.value = `${t("ceoOffice.writeFailed")}: ${err?.message || err}`;
  } finally {
    resolvingHandoff.value = "";
  }
}

onMounted(load);
</script>

<style scoped src="../styles/views/ceo-office.css"></style>
