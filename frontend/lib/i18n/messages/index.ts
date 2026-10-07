// The interface dictionary: [French, English] per key, one namespace per
// area. Every visible text of the interface lives here (or in values.ts for
// the labels of API values) -- never a per-component translation.
import { common } from "@/lib/i18n/messages/common";

export const MESSAGES = {
  ...common,
} as const;

export type MessageKey = keyof typeof MESSAGES;
