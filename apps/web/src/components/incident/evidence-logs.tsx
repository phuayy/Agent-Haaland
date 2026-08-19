import { Terminal } from "lucide-react";

function colorizeLine(line: string, key: number) {
  let className = "text-zinc-300";
  if (line.startsWith("CRITICAL")) className = "text-red-400";
  else if (line.startsWith("ERROR")) className = "text-red-400/90";
  else if (line.startsWith("WARNING")) className = "text-amber-400";
  else if (/Error|Exception/.test(line)) className = "text-red-400";
  else if (line.trim().startsWith("File ")) className = "text-sky-400";

  return (
    <div key={key} className={className}>
      {line || " "}
    </div>
  );
}

export function EvidenceLogs({ logs }: { logs: string }) {
  return (
    <div className="flex h-full flex-col overflow-hidden rounded-lg border border-border bg-black/40">
      <div className="flex items-center gap-2 border-b border-border bg-secondary/30 px-3 py-2">
        <Terminal className="h-3.5 w-3.5 text-muted-foreground" />
        <span className="text-xs font-medium text-muted-foreground">
          traceback.log
        </span>
        <div className="ml-auto flex gap-1.5">
          <span className="h-2.5 w-2.5 rounded-full bg-red-500/70" />
          <span className="h-2.5 w-2.5 rounded-full bg-amber-500/70" />
          <span className="h-2.5 w-2.5 rounded-full bg-emerald-500/70" />
        </div>
      </div>
      <div className="flex-1 overflow-auto p-4 font-mono text-[12px] leading-relaxed whitespace-pre">
        {logs.split("\n").map((line, i) => colorizeLine(line, i))}
      </div>
    </div>
  );
}
