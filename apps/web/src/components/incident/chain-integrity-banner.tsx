"use client";

import { ShieldCheck, ShieldAlert, Loader2 } from "lucide-react";
import { useChainVerify } from "@/hooks/use-chain-verify";
import { cn } from "@/lib/utils";

export function ChainIntegrityBanner({ reference }: { reference: string }) {
  const { data, isPending, isError } = useChainVerify(reference);

  if (isPending) {
    return (
      <div className="flex items-center gap-2 rounded-lg border border-border bg-muted/60 px-4 py-3 text-[13px] text-muted-foreground">
        <Loader2 className="h-3.5 w-3.5 animate-spin" />
        Verifying audit chain…
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div className="flex items-center gap-2 rounded-lg border border-border bg-muted/60 px-4 py-3 text-[13px] text-muted-foreground">
        <ShieldAlert className="h-3.5 w-3.5" />
        Could not verify the audit chain.
      </div>
    );
  }

  return (
    <div
      className={cn(
        "flex items-center gap-2 rounded-lg border px-4 py-3 text-[13px] font-medium",
        data.valid
          ? "border-emerald-200 bg-emerald-50 text-emerald-600"
          : "border-rose-200 bg-rose-50 text-rose-600"
      )}
    >
      {data.valid ? <ShieldCheck className="h-3.5 w-3.5 shrink-0" /> : <ShieldAlert className="h-3.5 w-3.5 shrink-0" />}
      {data.valid ? (
        <span>
          Audit chain verified — <span className="tabular-nums">{data.events_checked}</span> event
          {data.events_checked === 1 ? "" : "s"}, unbroken
        </span>
      ) : (
        <span>
          Audit chain diverged at sequence{" "}
          <span className="tabular-nums">{data.first_divergence_seq}</span> — do not trust events after this point
        </span>
      )}
    </div>
  );
}
