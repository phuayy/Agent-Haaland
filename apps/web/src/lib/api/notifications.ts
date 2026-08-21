import { apiGet, apiPost } from "./client";
import type {
  LarkChatsResult,
  LarkVerifyResult,
  NotificationChannels,
  NotificationTestResult,
} from "./types";

export const listNotificationChannels = () =>
  apiGet<NotificationChannels>("/api/notifications/channels");

export const verifyLarkCredentials = () =>
  apiGet<LarkVerifyResult>("/api/notifications/lark/verify");

export const listLarkChats = () => apiGet<LarkChatsResult>("/api/notifications/lark/chats");

export const sendTestNotification = (target?: string) =>
  apiPost<NotificationTestResult>(
    target ? `/api/notifications/test?target=${encodeURIComponent(target)}` : "/api/notifications/test"
  );
