"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { Loader2, Siren } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { useCreateDebugSession } from "@/hooks/use-create-debug-session";
import { READ_ONLY } from "@/lib/api/client";
import type { Service } from "@/lib/api/types";

export function TriggerDebugSessionDialog({ service }: { service: Service }) {
  const [open, setOpen] = useState(false);
  const [logText, setLogText] = useState("");
  const [baseRef, setBaseRef] = useState(service.base_ref);
  const router = useRouter();
  const mutation = useCreateDebugSession();

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!logText.trim() || !service.repo_url) return;
    // No local bookkeeping on success: the backend links the new incident to
    // this service, so the card's health and history come back from the next
    // /api/services poll (use-create-debug-session invalidates it).
    mutation.mutate(
      {
        repo_url: service.repo_url,
        service_name: service.name,
        log_text: logText,
        base_ref: baseRef || "main",
      },
      {
        onSuccess: (data) => {
          setOpen(false);
          setLogText("");
          router.push(`/incidents/${data.reference}`);
        },
      }
    );
  }

  // Nothing to clone without a repository — a service registered without one
  // can't be the target of a debug session.
  if (!service.repo_url) {
    return (
      <Button
        variant="outline"
        size="sm"
        disabled
        className="flex-1 font-normal"
        title="No repository linked — add one to trigger a debug session"
      >
        <Siren className="h-3.5 w-3.5 text-muted-foreground" />
        Trigger
      </Button>
    );
  }

  // Creating a session is a write, and proxy-mode builds forward GET only
  // (lib/api/client.ts). Disabled rather than hidden so the demo still shows
  // the entrypoint exists and says how to reach it.
  if (READ_ONLY) {
    return (
      <Button
        variant="outline"
        size="sm"
        disabled
        className="flex-1 font-normal"
        title="Read-only dashboard — POST /api/debug-sessions with your own bearer token"
      >
        <Siren className="h-3.5 w-3.5 text-muted-foreground" />
        Trigger
      </Button>
    );
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger
        render={
          <Button variant="outline" size="sm" className="flex-1 font-normal">
            <Siren className="h-3.5 w-3.5 text-muted-foreground" />
            Trigger
          </Button>
        }
      />
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Trigger a debug session for {service.name}</DialogTitle>
          <DialogDescription>
            Submits the log text below to <code className="text-xs">POST /api/debug-sessions</code> — this
            opens a real incident and enqueues the agent.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="log-text">Log / traceback text</Label>
            <Textarea
              id="log-text"
              placeholder={"Traceback (most recent call last):\n  File \"app/pricing.py\", line 42..."}
              value={logText}
              onChange={(e) => setLogText(e.target.value)}
              className="min-h-40 font-mono text-xs"
              required
            />
          </div>

          <div className="flex flex-col gap-1.5">
            <Label htmlFor="base-ref">Base branch</Label>
            <Input id="base-ref" value={baseRef} onChange={(e) => setBaseRef(e.target.value)} />
          </div>

          {mutation.isError && <p className="text-xs text-rose-600">{mutation.error.message}</p>}

          <DialogFooter>
            <Button type="submit" className="w-full" disabled={!logText.trim() || mutation.isPending}>
              {mutation.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
              Submit
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
