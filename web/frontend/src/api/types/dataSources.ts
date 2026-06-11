export interface DataSourceCatalogRow {
  source: string;
  label: string;
  status: string;
  requires_token: boolean;
  discovery_method: string;
  notes: string;
  capability_count: number;
  integrated_count: number;
  unmapped_count: number;
  access_statuses: Record<string, number>;
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
  integrated_count: number;
  unmapped_count: number;
  candidate_count: number;
  requires_token_count: number;
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
