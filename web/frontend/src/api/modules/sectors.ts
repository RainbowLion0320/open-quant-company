import { get } from "../client";
import type { SectorDetailResponse, SectorExposureResponse, SectorOverviewResponse } from "../types";

export const sectorsApi = {
  sectorOverview: () => get<SectorOverviewResponse>("/api/sectors/overview"),
  sectorExposure: () => get<SectorExposureResponse>("/api/sectors/exposure"),
  sectorDetail: (industry: string) => get<SectorDetailResponse>(`/api/sectors/${encodeURIComponent(industry)}`),
};
