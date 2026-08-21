"use client";

import { useState } from "react";
import { Check, Copy, Loader2, Radio, Send, ShieldCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  useListLarkChats,
  useNotificationChannels,
  useSendTestNotification,
  useVerifyLarkCredentials,
} from "@/hooks/use-notifications";
import { READ_ONLY } from "@/lib/api/client";

function CopyChatId({ chatId }: { chatId: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      onClick={async () => {
        await navigator.clipboard.writeText(chatId);
        setCopied(true);
        setTimeout(() => setCopied(false), 1500);
      }}
      className="flex items-center gap-1.5 rounded-md border border-border px-2 py-1 font-mono text-xs text-muted-foreground transition-colors hover:border-foreground/20 hover:bg-muted"
    >
      {chatId}
      {copied ? <Check className="h-3 w-3 text-emerald-600" /> : <Copy className="h-3 w-3" />}
    </button>
  );
}

export function NotificationSettings() {
  const { data: channels, isPending: channelsPending } = useNotificationChannels();
  const verify = useVerifyLarkCredentials();
  const chats = useListLarkChats();
  const test = useSendTestNotification();
  const [target, setTarget] = useState("");

  const hasChannels = (channels?.channels.length ?? 0) > 0;

  return (
    <div className="flex flex-col gap-5">
      <section className="rounded-xl border border-border bg-card p-5 shadow-sm">
        <div className="mb-3 flex items-center gap-2 text-[13px] font-medium text-foreground">
          <Radio className="h-4 w-4 text-muted-foreground" />
          Configured channels
        </div>
        {channelsPending ? (
          <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
        ) : hasChannels ? (
          <div className="flex flex-wrap items-center gap-2 text-sm">
            {channels!.channels.map((c) => (
              <span key={c} className="rounded-full border border-border bg-muted px-2.5 py-1 text-xs text-foreground/90">
                {c}
              </span>
            ))}
            <span className="text-xs text-muted-foreground">
              (Lark mode: {channels!.lark_mode}, domain: {channels!.lark_domain})
            </span>
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">
            No channels configured — set <code className="text-xs">HAALAND_NOTIFY_CHANNELS</code> on the
            backend.
          </p>
        )}
      </section>

      <section className="rounded-xl border border-border bg-card p-5 shadow-sm">
        <div className="mb-3 flex items-center gap-2 text-[13px] font-medium text-foreground">
          <ShieldCheck className="h-4 w-4 text-muted-foreground" />
          Lark credentials
        </div>
        <Button size="sm" variant="outline" onClick={() => verify.mutate()} disabled={verify.isPending}>
          {verify.isPending && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
          Verify credentials
        </Button>
        {verify.isSuccess && (
          <p className="mt-2 text-xs text-emerald-600">
            OK — app_id {verify.data.app_id} against {verify.data.base_url}, token valid for{" "}
            {verify.data.token_expires_in_seconds}s.
          </p>
        )}
        {verify.isError && <p className="mt-2 text-xs text-rose-600">{verify.error.message}</p>}
      </section>

      <section className="rounded-xl border border-border bg-card p-5 shadow-sm">
        <div className="mb-3 text-[13px] font-medium text-foreground">Chats the bot can reach</div>
        <Button size="sm" variant="outline" onClick={() => chats.mutate()} disabled={chats.isPending}>
          {chats.isPending && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
          List chats
        </Button>
        {chats.isSuccess && chats.data.count === 0 && (
          <p className="mt-2 text-xs text-muted-foreground">
            The bot hasn&apos;t been added to any chat yet — this doesn&apos;t mean credentials are wrong.
          </p>
        )}
        {chats.isSuccess && chats.data.count > 0 && (
          <ul className="mt-2 flex flex-col gap-1.5">
            {chats.data.chats.map((c) => (
              <li key={c.chat_id} className="flex items-center justify-between gap-2 text-sm">
                <span className="truncate">{c.name ?? "(unnamed)"}</span>
                {c.chat_id && <CopyChatId chatId={c.chat_id} />}
              </li>
            ))}
          </ul>
        )}
        {chats.isError && <p className="mt-2 text-xs text-rose-600">{chats.error.message}</p>}
      </section>

      <section className="rounded-xl border border-border bg-card p-5 shadow-sm">
        <div className="mb-3 flex items-center gap-2 text-[13px] font-medium text-foreground">
          <Send className="h-4 w-4 text-muted-foreground" />
          Send a test notification
        </div>
        <div className="flex items-center gap-2">
          <Label htmlFor="target" className="sr-only">
            Target (optional)
          </Label>
          <Input
            id="target"
            placeholder="oc_… / ou_… / email (optional)"
            value={target}
            onChange={(e) => setTarget(e.target.value)}
            className="max-w-xs"
          />
          <Button
            size="sm"
            onClick={() => test.mutate(target.trim() || undefined)}
            disabled={test.isPending || READ_ONLY}
            title={
              READ_ONLY
                ? "Read-only dashboard — POST /api/notifications/test with your own bearer token"
                : undefined
            }
          >
            {test.isPending && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
            Send
          </Button>
        </div>
        {test.isSuccess && (
          <div className="mt-2 flex flex-col gap-1 text-xs">
            {"results" in test.data ? (
              test.data.results.map((d, i) => (
                <p key={i} className={d.status === "sent" ? "text-emerald-600" : "text-rose-600"}>
                  {d.channel}: {d.status}
                  {d.detail ? ` — ${d.detail}` : ""}
                </p>
              ))
            ) : (
              <p className="text-muted-foreground">{test.data.detail}</p>
            )}
          </div>
        )}
        {test.isError && <p className="mt-2 text-xs text-rose-600">{test.error.message}</p>}
      </section>
    </div>
  );
}
