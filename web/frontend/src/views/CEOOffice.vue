<template>
  <div class="ceo-office view-page">
    <section class="ceo-toolbar">
      <div>
        <p class="eyebrow">{{ t("ceoOffice.subtitle") }}</p>
        <h2>{{ t("ceoOffice.title") }}</h2>
      </div>
      <div class="ceo-actions">
        <button class="btn btn-ghost" type="button" @click="load">{{ t("ceoOffice.refresh") }}</button>
        <button class="btn btn-primary" type="button" @click="createSession">{{ t("ceoOffice.createSession") }}</button>
      </div>
    </section>

    <section v-if="error" class="ceo-alert">{{ error }}</section>

    <section class="ceo-summary">
      <article class="ceo-metric">
        <span>{{ t("ceoOffice.session") }}</span>
        <strong>{{ activeSession?.title || t("ceoOffice.noSession") }}</strong>
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
        <span>{{ t("ceoOffice.evidence") }}</span>
        <strong>{{ evidenceCount }}</strong>
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
            <span>{{ t("ceoOffice.actionQueue") }}</span>
            <small>{{ actions.length }}</small>
          </header>
          <div v-if="!actions.length" class="ceo-empty">{{ t("ceoOffice.noActions") }}</div>
          <div v-else class="action-list">
            <div v-for="action in actions" :key="action.action_id" class="action-row">
              <div class="action-title">
                <strong>{{ action.summary }}</strong>
                <span :class="['action-status', action.status]">{{ statusLabel(action.status) }}</span>
              </div>
              <small>{{ deskLabel(action.desk) }} · {{ action.risk_level }}</small>
              <div v-if="action.status === 'approval_required'" class="approval-buttons">
                <button class="btn btn-xs" type="button" @click="approveAction(action.action_id)">
                  {{ t("ceoOffice.approved") }}
                </button>
                <button class="btn btn-xs btn-danger" type="button" @click="rejectAction(action.action_id)">
                  {{ t("ceoOffice.rejected") }}
                </button>
              </div>
            </div>
          </div>
        </article>
      </aside>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { api, type AgentAction, type AgentDesk, type AgentMessage, type AgentSession } from "../api";
import { useI18n } from "../i18n";

const { t } = useI18n();

const sessions = ref<AgentSession[]>([]);
const activeSession = ref<AgentSession | null>(null);
const messages = ref<AgentMessage[]>([]);
const actions = ref<AgentAction[]>([]);
const desks = ref<AgentDesk[]>([]);
const draft = ref("");
const sending = ref(false);
const error = ref("");

const pendingActions = computed(() => actions.value.filter(action => action.status === "approval_required"));
const evidenceCount = computed(() => [
  ...messages.value.flatMap(message => message.evidence_refs || []),
  ...actions.value.flatMap(action => action.evidence_refs || []),
].length);

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
  return status;
}

function formatTime(value: string) {
  if (!value) return "—";
  return value.replace("T", " ").replace("Z", "");
}

async function loadSession(sessionId: string) {
  const detail = await api.agentSession(sessionId);
  activeSession.value = detail.session;
  messages.value = detail.messages || [];
  actions.value = detail.actions || [];
}

async function load() {
  error.value = "";
  try {
    const [sessionPayload, deskPayload, actionPayload] = await Promise.all([
      api.agentSessions(),
      api.agentDesks(),
      api.agentActions(),
    ]);
    sessions.value = sessionPayload.sessions || [];
    desks.value = deskPayload.desks || [];
    actions.value = actionPayload.actions || [];
    if (sessions.value.length) {
      await loadSession(activeSession.value?.session_id || sessions.value[0].session_id);
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

onMounted(load);
</script>

<style scoped src="../styles/views/ceo-office.css"></style>
