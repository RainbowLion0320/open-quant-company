import { get } from "../client";
import type { DataSourceCapabilityResponse } from "../types/dataSources";

export const dataSourcesApi = {
  dataSourceCapabilities: () => get<DataSourceCapabilityResponse>("/api/data-sources/capabilities"),
};
