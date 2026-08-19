"use client";

import { FormEvent, useState } from "react";
import { Plus } from "lucide-react";
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useHaalandStore } from "@/lib/store";
import { Tier } from "@/lib/types";

const EMPTY_FORM = {
  name: "",
  repoUrl: "",
  baseBranch: "main",
  tier: "Tier 2" as Tier,
  ownerTeam: "",
};

export function AddServiceDialog() {
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(EMPTY_FORM);
  const addService = useHaalandStore((s) => s.addService);

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!form.name.trim() || !form.repoUrl.trim() || !form.ownerTeam.trim()) return;
    addService(form);
    setForm(EMPTY_FORM);
    setOpen(false);
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger
        render={
          <Button size="sm">
            <Plus className="h-4 w-4" />
            Add Service
          </Button>
        }
      />
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Register a new service</DialogTitle>
          <DialogDescription>
            Connect a microservice for automated incident tracking.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="name">Service Name</Label>
            <Input
              id="name"
              placeholder="Billing Service"
              value={form.name}
              onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
              required
            />
          </div>

          <div className="flex flex-col gap-1.5">
            <Label htmlFor="repoUrl">GitHub Repository URL</Label>
            <Input
              id="repoUrl"
              placeholder="https://github.com/org/billing-service"
              value={form.repoUrl}
              onChange={(e) => setForm((f) => ({ ...f, repoUrl: e.target.value }))}
              required
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="baseBranch">Base Branch</Label>
              <Input
                id="baseBranch"
                placeholder="main"
                value={form.baseBranch}
                onChange={(e) =>
                  setForm((f) => ({ ...f, baseBranch: e.target.value }))
                }
              />
            </div>

            <div className="flex flex-col gap-1.5">
              <Label htmlFor="tier">Criticality Tier</Label>
              <Select
                value={form.tier}
                onValueChange={(value) =>
                  setForm((f) => ({ ...f, tier: value as Tier }))
                }
              >
                <SelectTrigger id="tier" className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="Tier 1">Tier 1 - Core</SelectItem>
                  <SelectItem value="Tier 2">Tier 2 - Standard</SelectItem>
                  <SelectItem value="Tier 3">Tier 3 - Internal</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          <div className="flex flex-col gap-1.5">
            <Label htmlFor="ownerTeam">Owner Team</Label>
            <Input
              id="ownerTeam"
              placeholder="Team Payments"
              value={form.ownerTeam}
              onChange={(e) =>
                setForm((f) => ({ ...f, ownerTeam: e.target.value }))
              }
              required
            />
          </div>

          <DialogFooter>
            <Button type="submit" className="w-full">
              Add Service
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
