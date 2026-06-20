import { get } from "../client";

export const settingsApi = {
  settings: async () => {
    const data = await get<any>("/api/settings");
    return data.config || {};
  },
  settingsSchema: () => get<{ groups: any[]; sections: any[]; total_groups: number; total_sections: number; total_fields: number }>("/api/settings/schema"),
};
