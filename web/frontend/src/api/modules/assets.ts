import { get } from "../client";

export const assetsApi = {
  assetsOverview: () => get<{ items: any[]; total: number }>("/api/assets/overview"),
};
