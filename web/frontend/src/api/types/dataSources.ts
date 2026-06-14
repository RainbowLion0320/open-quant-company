export interface DataSourceCatalogRow {
  source: string;
  label: string;
  status: string;
  requires_token: boolean;
  discovery_method: string;
  discovery_scope: string;
  notes: string;
  capability_count: number;
  discovered_count: number;
  sample_probed_count: number;
  contracted_count: number;
  project_integrated_count: number;
  probe_attempted_count: number;
  probe_planned_count: number;
  probe_blocked_count: number;
  probe_error_count: number;
  probe_ok_count: number;
  integrated_count: number;
  unmapped_count: number;
  access_statuses: Record<string, number>;
  discovery_statuses: Record<string, number>;
  probe_statuses: Record<string, number>;
  last_audited_at: string;
}

export interface DataSourceCapability {
  source: string;
  interface: string;
  asset_type: string;
  data_domain: string;
  frequency: string;
  requires_token: boolean;
  permission_status?: string;
  rate_limit_status?: string;
  access_status: string;
  probe_strategy: string;
  discovery_status: string;
  discovery_scope: string;
  probe_status: string;
  probe_contract_id?: string;
  probe_attempted_at?: string;
  probe_block_reason?: string;
  elapsed_ms?: number | null;
  row_count?: number | null;
  error_class?: string;
  sample_probe?: {
    status?: string;
    contract_id?: string;
    row_count?: number;
    field_sample?: string[];
    block_reason?: string;
    message?: string;
    resume_skipped?: boolean;
  };
  source_url?: string;
  endpoint_pattern?: string;
  field_sample?: string[];
  integration_status: string;
  mapped_dimensions: string[];
  module?: string;
  signature?: string;
  docstring_summary?: string;
  message?: string;
  notes?: string;
  backend?: string;
}

export interface DataSourceDiffSummary {
  capability_unmapped_count: number;
  registry_missing_source_count: number;
  field_frequency_mismatch_count: number;
}

export interface DataSourceDiff {
  summary: DataSourceDiffSummary;
  capability_unmapped: any[];
  registry_missing_source: any[];
  field_frequency_mismatch: any[];
}

export interface DataSourceCapabilitySummary {
  source_count: number;
  audited_source_count: number;
  capability_count: number;
  discovered_count: number;
  sample_probed_count: number;
  contracted_count: number;
  project_integrated_count: number;
  integrated_count: number;
  unmapped_count: number;
  candidate_count: number;
  manual_review_count: number;
  requires_token_count: number;
  probe_attempted_count: number;
  probe_planned_count: number;
  probe_blocked_count: number;
  probe_error_count: number;
  probe_ok_count: number;
  no_permission_count: number;
  rate_limited_count: number;
  probe_statuses?: Record<string, number>;
  discovery_statuses?: Record<string, number>;
  sources: Record<string, number>;
  artifact_age_seconds?: number | null;
}

export interface DataSourceCapabilityResponse {
  status: "ok" | "degraded" | "no_artifact" | string;
  generated_at?: string;
  latest: { generated_at?: string; artifact_path: string } | null;
  summary: DataSourceCapabilitySummary;
  sources: DataSourceCatalogRow[];
  capabilities: DataSourceCapability[];
  diff: DataSourceDiff;
  recommended_command: string;
  errors?: any[];
}
