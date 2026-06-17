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
          </div>
        </div>

        <form class="message-composer" @submit.prevent="sendMessage">
          <label class="desk-target-control">
            <span>{{ t("ceoOffice.messageDesk") }}</span>
            <select v-model="selectedDraftDesk" @change="selectDesk(selectedDraftDesk)">
              <option v-for="desk in desks" :key="desk.desk_id" :value="desk.desk_id">
                {{ deskLabel(desk.desk_id) }}
              </option>
            </select>
          </label>
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
            <button
              v-for="desk in desks"
              :key="desk.desk_id"
              class="desk-row"
              :class="{ selected: selectedDeskId === desk.desk_id }"
              type="button"
              @click="selectDesk(desk.desk_id)"
            >
              <span class="status-dot" :class="desk.status"></span>
              <div>
                <strong>{{ deskLabel(desk.desk_id) }}</strong>
                <small>{{ desk.allowed_tools.length }} tools</small>
              </div>
            </button>
          </div>
          <div v-if="selectedDesk" class="desk-detail">
            <div class="detail-row">
              <span>{{ t("ceoOffice.deskMandate") }}</span>
              <p>{{ selectedDesk.mandate }}</p>
            </div>
            <div class="detail-row">
              <span>{{ t("ceoOffice.defaultPolicy") }}</span>
              <code>{{ selectedDesk.default_policy }}</code>
            </div>
            <div class="desk-chip-section">
              <small>{{ t("ceoOffice.capabilities") }}</small>
              <div class="desk-chip-list">
                <code v-for="capability in selectedDesk.capabilities || []" :key="capability">{{ capability }}</code>
              </div>
            </div>
            <div class="desk-chip-section">
              <small>{{ t("ceoOffice.allowedTools") }}</small>
              <div class="desk-chip-list">
                <code v-for="tool in selectedDesk.allowed_tools" :key="tool">{{ tool }}</code>
              </div>
            </div>
            <div class="desk-chip-section">
              <small>{{ t("ceoOffice.forbiddenActions") }}</small>
              <div class="desk-chip-list">
                <code v-for="actionType in selectedDesk.forbidden_actions" :key="actionType">{{ actionType }}</code>
              </div>
            </div>
            <div class="desk-chip-section">
              <small>{{ t("ceoOffice.evidenceRequired") }}</small>
              <div class="desk-chip-list">
                <code v-for="evidenceKind in selectedDesk.evidence_required" :key="evidenceKind">{{ evidenceKind }}</code>
              </div>
            </div>
            <div class="desk-activity-grid">
              <div>
                <span>{{ t("ceoOffice.relatedMessages") }}</span>
                <strong>{{ deskScopedMessages.length }}</strong>
              </div>
              <div>
                <span>{{ t("ceoOffice.relatedActions") }}</span>
                <strong>{{ deskScopedActions.length }}</strong>
              </div>
              <div>
                <span>{{ t("ceoOffice.relatedHandoffs") }}</span>
                <strong>{{ deskScopedHandoffs.length }}</strong>
              </div>
            </div>
            <div v-if="deskScopedActions.length" class="desk-related-list">
              <small>{{ t("ceoOffice.relatedActions") }}</small>
              <button
                v-for="action in deskScopedActions.slice(0, 3)"
                :key="action.action_id"
                class="desk-related-row"
                type="button"
                @click="selectAction(action.action_id)"
              >
                <strong>{{ action.summary }}</strong>
                <span>{{ statusLabel(action.status) }}</span>
              </button>
            </div>
            <div v-if="deskScopedHandoffs.length" class="desk-related-list">
              <small>{{ t("ceoOffice.relatedHandoffs") }}</small>
              <div v-for="handoff in deskScopedHandoffs.slice(0, 3)" :key="handoff.handoff_id" class="desk-related-row passive">
                <strong>{{ deskLabel(handoff.source_desk) }} → {{ deskLabel(handoff.target_desk) }}</strong>
                <span>{{ statusLabel(handoff.status) }}</span>
              </div>
            </div>
          </div>
        </article>

        <article class="ceo-panel">
          <header class="panel-head">
            <span>{{ t("ceoOffice.approvalPolicies") }}</span>
            <small>{{ approvalPolicies.length }}</small>
          </header>
          <div v-if="!approvalPolicies.length" class="ceo-empty">{{ t("ceoOffice.noApprovalPolicies") }}</div>
          <div v-else class="policy-list">
            <div v-for="policy in approvalPolicies" :key="policy.policy_id" class="policy-row">
              <div class="action-title">
                <strong>{{ policy.risk_level }}</strong>
                <span :class="['action-status', policy.default_decision]">{{ policyDecisionLabel(policy.default_decision) }}</span>
              </div>
              <div class="policy-grid">
                <div>
                  <small>{{ t("ceoOffice.defaultDecision") }}</small>
                  <code>{{ policyDecisionLabel(policy.default_decision) }}</code>
                </div>
                <div>
                  <small>{{ t("ceoOffice.requiredRole") }}</small>
                  <code>{{ policy.required_role || "—" }}</code>
                </div>
              </div>
              <small>{{ t("ceoOffice.policyReason") }}</small>
              <p>{{ policy.reason }}</p>
            </div>
          </div>
        </article>

        <article class="ceo-panel">
          <header class="panel-head">
            <span>{{ t("ceoOffice.workOrders") }}</span>
            <small>{{ workOrders.length }}</small>
          </header>
          <div v-if="!workOrders.length" class="ceo-empty">{{ t("ceoOffice.noWorkOrders") }}</div>
          <div v-else class="work-order-list">
            <div v-for="workOrder in workOrders" :key="workOrder.work_order_id" class="work-order-row">
              <div class="action-title">
                <strong>{{ workOrder.title }}</strong>
                <span :class="['action-status', workOrder.status]">{{ statusLabel(workOrder.status) }}</span>
              </div>
              <p>{{ workOrder.summary }}</p>
              <small>{{ workOrder.impact }}</small>
              <p v-if="workOrder.resolution" class="muted-line">{{ t("ceoOffice.resolution") }}: {{ workOrder.resolution }}</p>
              <div v-if="workOrder.affected_files.length" class="desk-chip-section">
                <small>{{ t("ceoOffice.affectedFiles") }}</small>
                <div class="desk-chip-list">
                  <code v-for="file in workOrder.affected_files" :key="`${workOrder.work_order_id}-${file}`">{{ file }}</code>
                </div>
              </div>
              <div v-if="workOrder.suggested_verification.length" class="desk-chip-section">
                <small>{{ t("ceoOffice.suggestedVerification") }}</small>
                <div class="desk-chip-list">
                  <code v-for="command in workOrder.suggested_verification" :key="`${workOrder.work_order_id}-${command}`">{{ command }}</code>
                </div>
              </div>
              <div v-if="workOrder.evidence_refs.length" class="approval-buttons">
                <button
                  v-for="evidenceId in workOrder.evidence_refs"
                  :key="`${workOrder.work_order_id}-${evidenceId}`"
                  class="btn btn-xs"
                  type="button"
                  @click="loadEvidence(evidenceId)"
                >
                  {{ t("ceoOffice.openEvidence") }}
                </button>
              </div>
              <div v-if="workOrder.status !== 'resolved' && workOrder.status !== 'canceled'" class="approval-buttons">
                <button
                  v-if="workOrder.status === 'open'"
                  class="btn btn-xs"
                  type="button"
                  :disabled="updatingWorkOrder === workOrder.work_order_id"
                  @click="updateWorkOrder(workOrder.work_order_id, 'in_progress', 'Accepted from CEO Office')"
                >
                  {{ t("ceoOffice.startWorkOrder") }}
                </button>
                <button
                  class="btn btn-xs"
                  type="button"
                  :disabled="updatingWorkOrder === workOrder.work_order_id"
                  @click="updateWorkOrder(workOrder.work_order_id, 'resolved', 'Resolved from CEO Office')"
                >
                  {{ t("ceoOffice.resolveHandoff") }}
                </button>
                <button
                  class="btn btn-xs danger"
                  type="button"
                  :disabled="updatingWorkOrder === workOrder.work_order_id"
                  @click="updateWorkOrder(workOrder.work_order_id, 'canceled', 'Canceled from CEO Office')"
                >
                  {{ t("ceoOffice.cancelWorkOrder") }}
                </button>
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
              <span>{{ t("ceoOffice.liveEnvironment") }}</span>
              <code>{{ liveEnvironment?.status || "unknown" }}</code>
            </div>
            <div class="detail-row">
              <span>{{ t("ceoOffice.liveMonitor") }}</span>
              <code>{{ liveMonitor?.status || t("ceoOffice.unknown") }}</code>
            </div>
            <div class="detail-row">
              <span>{{ t("ceoOffice.environmentChecks") }}</span>
              <div v-if="!liveEnvironmentChecks.length" class="ceo-empty compact">
                {{ t("ceoOffice.noEnvironmentChecks") }}
              </div>
              <div v-else class="run-list">
                <div v-for="check in liveEnvironmentChecks" :key="check.name" class="run-row">
                  <strong>{{ check.name }}</strong>
                  <small>{{ check.status }}{{ check.blocker ? ` · ${check.blocker}` : "" }}</small>
                </div>
              </div>
            </div>
            <div class="detail-row">
              <span>{{ t("ceoOffice.liveKillSwitch") }}</span>
              <div class="kill-switch-state" :class="{ active: liveKillSwitch?.active, invalid: liveKillSwitch?.status === 'invalid' }">
                <code>{{ statusLabel(liveKillSwitch?.status || "inactive") }}</code>
                <small>{{ liveKillSwitch?.reason || t("ceoOffice.killSwitchClear") }}</small>
              </div>
            </div>
            <div class="approval-buttons">
              <button
                v-if="!liveKillSwitch?.active"
                class="btn btn-xs btn-danger"
                type="button"
                :disabled="operatingLiveKillSwitch === 'activate'"
                @click="operateLiveKillSwitch('activate')"
              >
                {{ t("ceoOffice.activateKillSwitch") }}
              </button>
              <button
                v-else
                class="btn btn-xs btn-ghost"
                type="button"
                :disabled="operatingLiveKillSwitch === 'deactivate'"
                @click="operateLiveKillSwitch('deactivate')"
              >
                {{ t("ceoOffice.deactivateKillSwitch") }}
              </button>
              <button
                class="btn btn-xs"
                type="button"
                :disabled="runningLiveMonitor"
                @click="runLiveMonitor"
              >
                {{ t("ceoOffice.runLiveMonitor") }}
              </button>
              <button
                class="btn btn-xs"
                type="button"
                :disabled="runningLiveReconciliation"
                @click="runLiveReconciliation"
              >
                {{ t("ceoOffice.runLiveReconciliation") }}
              </button>
            </div>
            <div v-if="liveReconciliation" class="rhythm-status">
              <span>{{ t("ceoOffice.liveReconciliation") }}</span>
              <strong>
                {{ statusLabel(liveReconciliation.status) }} ·
                {{ t("ceoOffice.reconciled") }} {{ liveReconciliation.reconciled_count }} ·
                {{ t("ceoOffice.skipped") }} {{ liveReconciliation.skipped_count }} ·
                {{ t("ceoOffice.blocked") }} {{ liveReconciliation.blocked_count }}
              </strong>
              <small>{{ liveReconciliation.checked_at }}</small>
            </div>
            <div v-if="liveMonitor" class="rhythm-status">
              <span>{{ t("ceoOffice.liveMonitor") }}</span>
              <strong>
                {{ statusLabel(liveMonitor.status) }} ·
                {{ t("ceoOffice.liveReconciliation") }} {{ statusLabel(liveMonitor.reconciliation.status) }}
              </strong>
              <small>{{ liveMonitor.checked_at }}</small>
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
              <button class="btn btn-xs btn-ghost" type="button" :disabled="runningScheduledRhythm" @click="runScheduledReportRhythm">
                {{ t("ceoOffice.runScheduledRhythm") }}
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
          <div v-if="scheduledRhythmResult" class="rhythm-status">
            <span>{{ t("ceoOffice.scheduledRhythmStatus") }}</span>
            <strong>
              {{ t("ceoOffice.generated") }} {{ scheduledRhythmResult.generated_count }} ·
              {{ t("ceoOffice.skipped") }} {{ scheduledRhythmResult.skipped_count }} ·
              {{ t("ceoOffice.sent") }} {{ scheduledRhythmResult.notification_count }}
            </strong>
            <small>{{ scheduledRhythmResult.checked_at }} · {{ t("ceoOffice.failed") }} {{ scheduledRhythmResult.failed_count }}</small>
          </div>
          <div v-if="notificationResult" class="rhythm-status">
            <span>{{ t("ceoOffice.notificationStatus") }}</span>
            <strong>
              {{ statusLabel(notificationResult.status) }} ·
              {{ t("ceoOffice.sent") }} {{ notificationResult.sent_count }} ·
              {{ t("ceoOffice.blocked") }} {{ notificationResult.blocked_count }} ·
              {{ t("ceoOffice.failed") }} {{ notificationResult.failed_count }}
            </strong>
            <small>{{ notificationResult.checked_at }}</small>
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
              <div v-if="reportSectionPreview(report).length" class="report-section-preview">
                <small>{{ t("ceoOffice.reportSections") }}</small>
                <div
                  v-for="section in reportSectionPreview(report)"
                  :key="`${report.report_id}-${section.sectionId}`"
                  class="report-section-row"
                >
                  <code>{{ section.sectionId }}</code>
                  <strong>{{ section.title }}</strong>
                  <p>{{ section.body }}</p>
                </div>
              </div>
              <div class="approval-buttons">
                <button class="btn btn-xs" type="button" @click="loadEvidence(report.evidence_id)">
                  {{ t("ceoOffice.openEvidence") }}
                </button>
                <button
                  class="btn btn-xs btn-ghost"
                  type="button"
                  :disabled="notifyingReport === report.report_id"
                  @click="notifyReport(report.report_id)"
                >
                  {{ t("ceoOffice.notifyReport") }}
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
              <small v-if="selectedAction.runs.length">
                {{ t("ceoOffice.runStream") }} {{ statusLabel(runStreamStatus) }}
              </small>
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
                  <div v-if="run.events?.length" class="run-timeline">
                    <small>{{ t("ceoOffice.runTimeline") }}</small>
                    <div v-for="event in run.events" :key="event.event_id" class="run-event-row">
                      <code>#{{ event.sequence }}</code>
                      <strong>{{ statusLabel(event.event_type) }}</strong>
                      <span>{{ statusLabel(event.status) }}</span>
                      <p>{{ event.message }}</p>
                    </div>
                  </div>
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
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { api, type AgentAction, type AgentActionDetail, type AgentApprovalPolicy, type AgentDesk, type AgentEvidenceSnapshot, type AgentHandoff, type AgentLiveEnvironment, type AgentLiveKillSwitch, type AgentLiveMonitor, type AgentLiveReadiness, type AgentLiveReconciliation, type AgentMessage, type AgentReport, type AgentReportNotification, type AgentReportRhythm, type AgentScheduledReportRhythm, type AgentSession, type AgentWorkOrder, type EvidenceNavigation, type EvidenceRef } from "../api";
import { useI18n } from "../i18n";

const { t } = useI18n();

const sessions = ref<AgentSession[]>([]);
const activeSession = ref<AgentSession | null>(null);
const messages = ref<AgentMessage[]>([]);
const actions = ref<AgentAction[]>([]);
const handoffs = ref<AgentHandoff[]>([]);
const workOrders = ref<AgentWorkOrder[]>([]);
const reports = ref<AgentReport[]>([]);
const rhythmResult = ref<AgentReportRhythm | null>(null);
const scheduledRhythmResult = ref<AgentScheduledReportRhythm | null>(null);
const notificationResult = ref<AgentReportNotification | null>(null);
const liveReadiness = ref<AgentLiveReadiness | null>(null);
const liveEnvironment = ref<AgentLiveEnvironment | null>(null);
const liveKillSwitch = ref<AgentLiveKillSwitch | null>(null);
const liveReconciliation = ref<AgentLiveReconciliation | null>(null);
const liveMonitor = ref<AgentLiveMonitor | null>(null);
const sessionStream = ref<AbortController | null>(null);
const sessionStreamId = ref("");
const lastStreamSignature = ref("");
const runStream = ref<AbortController | null>(null);
const runStreamId = ref("");
const runStreamStatus = ref("inactive");
const lastRunStreamSignature = ref("");
const desks = ref<AgentDesk[]>([]);
const approvalPolicies = ref<AgentApprovalPolicy[]>([]);
const selectedAction = ref<AgentActionDetail | null>(null);
const selectedEvidence = ref<EvidenceRef | null>(null);
const selectedEvidenceSnapshot = ref<AgentEvidenceSnapshot | null>(null);
const selectedEvidenceNavigation = ref<EvidenceNavigation | null>(null);
const selectedEvidenceStatus = ref("");
const runningAction = ref("");
const submittingPaperAction = ref("");
const cancelingAction = ref("");
const resolvingHandoff = ref("");
const updatingWorkOrder = ref("");
const generatingReport = ref(false);
const runningRhythm = ref(false);
const runningScheduledRhythm = ref(false);
const notifyingReport = ref("");
const operatingLiveKillSwitch = ref<"activate" | "deactivate" | "">("");
const runningLiveReconciliation = ref(false);
const runningLiveMonitor = ref(false);
const selectedReportKind = ref("daily_brief");
const selectedDraftDesk = ref("reporting");
const selectedDeskId = ref("reporting");
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
const liveEnvironmentChecks = computed(() => Object.entries(liveEnvironment.value?.checks || {}).slice(0, 6).map(([name, check]) => {
  const row = objectParam(check);
  return {
    name,
    status: String(row.status || "unknown"),
    blocker: String(row.blocker || ""),
  };
}));
const selectedDesk = computed(() => desks.value.find(desk => desk.desk_id === selectedDeskId.value) || desks.value[0] || null);
const deskScopedMessages = computed(() => messages.value.filter(message => message.desk === selectedDeskId.value));
const deskScopedActions = computed(() => actions.value.filter(action => action.desk === selectedDeskId.value));
const deskScopedHandoffs = computed(() => handoffs.value.filter(
  handoff => handoff.source_desk === selectedDeskId.value || handoff.target_desk === selectedDeskId.value,
));
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
  portfolio: t("ceoOffice.portfolioDesk"),
  risk: t("ceoOffice.riskDesk"),
  execution: t("ceoOffice.executionDesk"),
  engineering: t("ceoOffice.engineeringDesk"),
  reporting: t("ceoOffice.reportingDesk"),
}));

interface ReportSectionPreview {
  sectionId: string;
  title: string;
  body: string;
}

function deskLabel(desk: string) {
  return deskNames.value[desk] || desk;
}

function selectDesk(deskId: string) {
  selectedDeskId.value = deskId;
  selectedDraftDesk.value = deskId;
}

function reportSectionPreview(report: AgentReport): ReportSectionPreview[] {
  const priorities = new Map([
    ["causal_chain_synthesis", 0],
    ["semantic_synthesis", 1],
    ["trend_synthesis", 2],
    ["artifact_findings", 3],
    ["open_work", 4],
  ]);
  return (report.sections || [])
    .map(section => {
      const sectionId = String(section.section_id || "");
      const body = String(section.body || "").replace(/\s+/g, " ").trim();
      return {
        sectionId,
        title: String(section.title || sectionId || "Section"),
        body: body.length > 220 ? `${body.slice(0, 220)}...` : body,
        priority: priorities.get(sectionId) ?? 99,
      };
    })
    .filter(section => section.sectionId && section.body)
    .sort((left, right) => left.priority - right.priority)
    .slice(0, 3)
    .map(({ sectionId, title, body }) => ({ sectionId, title, body }));
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
  if (status === "in_progress") return t("ceoOffice.inProgress");
  if (status === "resolved") return t("ceoOffice.resolved");
  if (status === "sent") return t("ceoOffice.sent");
  if (status === "dry_run") return t("ceoOffice.dryRun");
  if (status === "partial") return t("ceoOffice.partial");
  if (status === "missing_secret") return t("ceoOffice.missingSecret");
  if (status === "inactive") return t("ceoOffice.inactive");
  if (status === "connected") return t("ceoOffice.connected");
  if (status === "connecting") return t("ceoOffice.connecting");
  if (status === "invalid") return t("ceoOffice.invalid");
  return status;
}

function policyDecisionLabel(decision: string) {
  if (decision === "auto_run") return t("ceoOffice.autoRun");
  if (decision === "approval_required") return t("ceoOffice.approvalRequired");
  if (decision === "work_order_required") return t("ceoOffice.workOrderRequired");
  return decision;
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
  runStreamStatus.value = "inactive";
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
  runStreamStatus.value = "connecting";
  void api.agentRunStream(
    runId,
    {
      onSnapshot: snapshot => {
        if (snapshot.signature === lastRunStreamSignature.value) return;
        lastRunStreamSignature.value = snapshot.signature;
        runStreamStatus.value = "connected";
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
        runStreamStatus.value = "blocked";
      },
    },
    { signal: controller.signal },
  ).catch(err => {
    if (controller.signal.aborted) return;
    const name = err instanceof Error ? err.name : "";
    if (name === "AbortError") return;
    runStreamStatus.value = "blocked";
  });
}

async function loadSession(sessionId: string, options: { connectStream?: boolean } = {}) {
  const [detail, reportPayload] = await Promise.all([
    api.agentSession(sessionId),
    api.agentReports(sessionId),
  ]);
  activeSession.value = detail.session;
  if (!desks.value.some(desk => desk.desk_id === selectedDraftDesk.value)) {
    selectedDraftDesk.value = detail.session.default_desk || "reporting";
  }
  messages.value = detail.messages || [];
  actions.value = detail.actions || [];
  handoffs.value = detail.handoffs || [];
  workOrders.value = detail.work_orders || [];
  reports.value = reportPayload.reports || [];
  if (options.connectStream !== false) {
    connectSessionStream(sessionId);
  }
}

async function loadOfficeState() {
  error.value = "";
  try {
    const [sessionPayload, deskPayload, policyPayload, actionPayload, handoffPayload, workOrderPayload, livePayload, environmentPayload, killSwitchPayload] = await Promise.all([
      api.agentSessions(),
      api.agentDesks(),
      api.agentApprovalPolicies(),
      api.agentActions(),
      api.agentHandoffs(),
      api.agentWorkOrders(),
      api.agentLiveReadiness(),
      api.agentLiveEnvironment(),
      api.agentLiveKillSwitch(),
    ]);
    sessions.value = sessionPayload.sessions || [];
    desks.value = deskPayload.desks || [];
    approvalPolicies.value = policyPayload.policies || [];
    if (!desks.value.some(desk => desk.desk_id === selectedDeskId.value)) {
      selectedDeskId.value = activeSession.value?.default_desk || desks.value[0]?.desk_id || "reporting";
    }
    actions.value = actionPayload.actions || [];
    handoffs.value = handoffPayload.handoffs || [];
    workOrders.value = workOrderPayload.work_orders || [];
    liveReadiness.value = livePayload.health;
    liveEnvironment.value = environmentPayload.environment;
    liveKillSwitch.value = killSwitchPayload.kill_switch || livePayload.health.live_kill_switch || environmentPayload.environment.live_kill_switch || null;
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
      desk: selectedDraftDesk.value,
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

async function runAction(actionId: string) {
  runningAction.value = actionId;
  error.value = "";
  try {
    await api.agentRunAction(actionId);
    await selectAction(actionId);
    await loadOfficeState();
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
    await loadOfficeState();
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

async function runScheduledReportRhythm() {
  runningScheduledRhythm.value = true;
  error.value = "";
  try {
    const payload = await api.agentRunScheduledReportRhythm();
    scheduledRhythmResult.value = payload.schedule;
    if (activeSession.value) {
      await loadSession(activeSession.value.session_id);
    } else {
      await loadOfficeState();
    }
  } catch (err: any) {
    error.value = `${t("ceoOffice.rhythmFailed")}: ${err?.message || err}`;
  } finally {
    runningScheduledRhythm.value = false;
  }
}

async function notifyReport(reportId: string) {
  notifyingReport.value = reportId;
  error.value = "";
  try {
    const payload = await api.agentNotifyReport(reportId);
    notificationResult.value = payload.notification;
    await loadEvidence(payload.notification.evidence.evidence_id);
  } catch (err: any) {
    error.value = `${t("ceoOffice.notificationFailed")}: ${err?.message || err}`;
  } finally {
    notifyingReport.value = "";
  }
}

async function operateLiveKillSwitch(nextState: "activate" | "deactivate") {
  operatingLiveKillSwitch.value = nextState;
  error.value = "";
  try {
    const reason = nextState === "activate"
      ? t("ceoOffice.killSwitchActivateReason")
      : t("ceoOffice.killSwitchDeactivateReason");
    const payload = nextState === "activate"
      ? await api.agentLiveKillSwitchActivate(reason)
      : await api.agentLiveKillSwitchDeactivate(reason);
    liveKillSwitch.value = payload.kill_switch;
    await loadOfficeState();
  } catch (err: any) {
    error.value = `${t("ceoOffice.killSwitchFailed")}: ${err?.message || err}`;
  } finally {
    operatingLiveKillSwitch.value = "";
  }
}

async function runLiveReconciliation() {
  runningLiveReconciliation.value = true;
  error.value = "";
  try {
    const payload = await api.agentLiveReconciliation({
      session_id: activeSession.value?.session_id || undefined,
    });
    liveReconciliation.value = payload.reconciliation;
    if (payload.reconciliation.evidence?.evidence_id) {
      await loadEvidence(payload.reconciliation.evidence.evidence_id);
    }
  } catch (err: any) {
    error.value = `${t("ceoOffice.liveReconciliationFailed")}: ${err?.message || err}`;
  } finally {
    runningLiveReconciliation.value = false;
  }
}

async function runLiveMonitor() {
  runningLiveMonitor.value = true;
  error.value = "";
  try {
    const payload = await api.agentLiveMonitor({
      session_id: activeSession.value?.session_id || undefined,
    });
    liveMonitor.value = payload.monitor;
    liveKillSwitch.value = payload.monitor.kill_switch || liveKillSwitch.value;
    liveReconciliation.value = payload.monitor.reconciliation;
    if (payload.monitor.evidence?.evidence_id) {
      await loadEvidence(payload.monitor.evidence.evidence_id);
    }
  } catch (err: any) {
    error.value = `${t("ceoOffice.liveMonitorFailed")}: ${err?.message || err}`;
  } finally {
    runningLiveMonitor.value = false;
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
    await loadOfficeState();
  } catch (err: any) {
    error.value = `${t("ceoOffice.writeFailed")}: ${err?.message || err}`;
  } finally {
    resolvingHandoff.value = "";
  }
}

async function updateWorkOrder(workOrderId: string, status: string, resolution: string) {
  updatingWorkOrder.value = workOrderId;
  error.value = "";
  try {
    await api.agentUpdateWorkOrder(workOrderId, { status, resolution });
    await loadOfficeState();
  } catch (err: any) {
    error.value = `${t("ceoOffice.updateWorkOrderFailed")}: ${err?.message || err}`;
  } finally {
    updatingWorkOrder.value = "";
  }
}

onMounted(loadOfficeState);
onBeforeUnmount(closeSessionStream);
onBeforeUnmount(closeRunStream);
</script>

<style scoped src="../styles/views/ceo-office.css"></style>
