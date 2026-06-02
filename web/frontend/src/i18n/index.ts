import { computed, readonly, ref } from "vue";
import { messages } from "./messages";

export type Locale = keyof typeof messages;

type Primitive = string | number | boolean | null | undefined;
type MessageNode = string | { [key: string]: MessageNode };

const STORAGE_KEY = "astrolabe.locale";
const DEFAULT_LOCALE: Locale = "zh-CN";

export const locales: Locale[] = ["zh-CN", "en-US"];

function isLocale(value: string | null | undefined): value is Locale {
  return Boolean(value && locales.includes(value as Locale));
}

function detectInitialLocale(): Locale {
  if (typeof window === "undefined") return DEFAULT_LOCALE;

  const stored = window.localStorage.getItem(STORAGE_KEY);
  if (isLocale(stored)) return stored;

  const browserLocale = window.navigator.language?.toLowerCase() || "";
  return browserLocale.startsWith("en") ? "en-US" : DEFAULT_LOCALE;
}

export const locale = ref<Locale>(detectInitialLocale());

function syncDocumentLanguage(next: Locale) {
  if (typeof document !== "undefined") {
    document.documentElement.lang = next;
  }
}

syncDocumentLanguage(locale.value);

function readMessage(root: MessageNode, key: string): string | undefined {
  const parts = key.split(".");
  let cursor: MessageNode | undefined = root;

  for (const part of parts) {
    if (!cursor || typeof cursor === "string") return undefined;
    cursor = cursor[part];
  }

  return typeof cursor === "string" ? cursor : undefined;
}

function interpolate(template: string, params: Record<string, Primitive>) {
  return template.replace(/\{(\w+)\}/g, (_, name: string) => {
    const value = params[name];
    return value === undefined || value === null ? `{${name}}` : String(value);
  });
}

export function setLocale(next: Locale) {
  locale.value = next;
  if (typeof window !== "undefined") {
    window.localStorage.setItem(STORAGE_KEY, next);
  }
  syncDocumentLanguage(next);
}

export function toggleLocale() {
  setLocale(locale.value === "zh-CN" ? "en-US" : "zh-CN");
}

export function translate(key: string, params: Record<string, Primitive> = {}) {
  const current = readMessage(messages[locale.value] as MessageNode, key);
  const fallback = readMessage(messages[DEFAULT_LOCALE] as MessageNode, key);
  return interpolate(current || fallback || key, params);
}

export function useI18n() {
  return {
    locale: readonly(locale),
    currentLocale: computed(() => locale.value),
    locales,
    setLocale,
    toggleLocale,
    t: translate,
  };
}
