import { NotificationSettings } from "@/components/notification-settings";

export default function NotificationSettingsPage() {
  return (
    <div className="mx-auto flex w-full max-w-2xl flex-col gap-7 px-8 py-9">
      <div className="flex flex-col gap-1">
        <div className="text-[11px] font-semibold tracking-wide text-muted-foreground uppercase">Settings</div>
        <h1 className="text-2xl font-semibold tracking-tight text-foreground">Notifications</h1>
        <p className="text-sm text-muted-foreground">Diagnostics for the configured notification channel(s)</p>
      </div>
      <NotificationSettings />
    </div>
  );
}
