import { get, patch, put } from "../client";

export const settingsApi = {
  settings: async () => {
    const data = await get<any>("/api/settings");
    return data.config || {};
  },
  saveSettings: (data: Record<string, any>) => put<Record<string, any>>("/api/settings", data),
  settingsSchema: () => get<{ sections: any[]; total_sections: number; total_fields: number }>("/api/settings/schema"),
  saveSettingsSection: (section: string, data: Record<string, any>) =>
    patch<Record<string, any>>(`/api/settings/section/${encodeURIComponent(section)}`, data),
};
