"use client";

import { FormEvent, useState } from "react";
import { CheckCircle2, Loader2, XCircle } from "lucide-react";
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
import { useApproveIncident, useRejectIncident } from "@/hooks/use-approve-reject";

const ACTOR_STORAGE_KEY = "haaland-actor-name";

function useRememberedActor() {
  const [actor, setActor] = useState(() =>
    typeof window === "undefined" ? "" : window.localStorage.getItem(ACTOR_STORAGE_KEY) ?? ""
  );
  function remember(value: string) {
    setActor(value);
    if (typeof window !== "undefined") window.localStorage.setItem(ACTOR_STORAGE_KEY, value);
  }
  return [actor, remember] as const;
}

/** Pinned bottom action bar for the detail card — only rendered while the
 * incident is awaiting_approval. Solid primary "Approve", ghost red "Reject". */
export function ApprovalPanel({ reference }: { reference: string }) {
  const [actor, setActor] = useRememberedActor();
  const [rejectOpen, setRejectOpen] = useState(false);
  const [reason, setReason] = useState("");
  const approve = useApproveIncident(reference);
  const reject = useRejectIncident(reference);

  function handleApprove() {
    if (!actor.trim()) return;
    approve.mutate({ actor: actor.trim() });
  }

  function handleReject(e: FormEvent) {
    e.preventDefault();
    if (!actor.trim() || reason.trim().length < 3) return;
    reject.mutate(
      { actor: actor.trim(), reason: reason.trim() },
      { onSuccess: () => setRejectOpen(false) }
    );
  }

  const resuming = approve.isPending || approve.isSuccess || reject.isSuccess;
  const error = approve.error ?? reject.error;

  return (
    <div className="sticky bottom-0 flex flex-col gap-2 border-t border-border bg-card/95 px-6 py-4 backdrop-blur-sm">
      {error && <p className="text-xs text-rose-600">{error.message}</p>}
      {resuming ? (
        <div className="flex items-center gap-2 text-[13px] text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
          Resuming — the incident will move to the next stage shortly.
        </div>
      ) : (
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <Label htmlFor="actor" className="text-xs text-muted-foreground">
              Your name
            </Label>
            <Input
              id="actor"
              placeholder="jane@acme.com"
              value={actor}
              onChange={(e) => setActor(e.target.value)}
              className="h-8 w-48"
            />
          </div>

          <div className="flex items-center gap-2">
            <Dialog open={rejectOpen} onOpenChange={setRejectOpen}>
              <DialogTrigger
                render={
                  <Button
                    variant="ghost"
                    disabled={!actor.trim()}
                    className="text-rose-600 hover:bg-rose-50 hover:text-rose-700"
                  >
                    <XCircle className="h-4 w-4" />
                    Reject
                  </Button>
                }
              />
              <DialogContent className="sm:max-w-md">
                <DialogHeader>
                  <DialogTitle>Reject this remediation</DialogTitle>
                  <DialogDescription>
                    A reason is required — it&apos;s fed back into the agent&apos;s next draft and recorded in
                    the post-mortem.
                  </DialogDescription>
                </DialogHeader>
                <form onSubmit={handleReject} className="flex flex-col gap-4">
                  <div className="flex flex-col gap-1.5">
                    <Label htmlFor="reject-reason">Reason</Label>
                    <Textarea
                      id="reject-reason"
                      placeholder="The fix doesn't address the root cause because…"
                      value={reason}
                      onChange={(e) => setReason(e.target.value)}
                      required
                      minLength={3}
                    />
                  </div>
                  <DialogFooter>
                    <Button
                      type="submit"
                      variant="destructive"
                      className="w-full"
                      disabled={reason.trim().length < 3}
                    >
                      Confirm rejection
                    </Button>
                  </DialogFooter>
                </form>
              </DialogContent>
            </Dialog>

            <Button onClick={handleApprove} disabled={!actor.trim() || approve.isPending}>
              <CheckCircle2 className="h-4 w-4" />
              Approve
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
