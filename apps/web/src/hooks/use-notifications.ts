import { useMutation, useQuery } from "@tanstack/react-query";
import {
  listNotificationChannels,
  listLarkChats,
  sendTestNotification,
  verifyLarkCredentials,
} from "@/lib/api/notifications";

export function useNotificationChannels() {
  return useQuery({
    queryKey: ["notification-channels"],
    queryFn: listNotificationChannels,
  });
}

export function useVerifyLarkCredentials() {
  return useMutation({ mutationFn: verifyLarkCredentials });
}

export function useListLarkChats() {
  return useMutation({ mutationFn: listLarkChats });
}

export function useSendTestNotification() {
  return useMutation({ mutationFn: (target?: string) => sendTestNotification(target) });
}
