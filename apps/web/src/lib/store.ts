import { create } from "zustand";
import { persist } from "zustand/middleware";
import { initialServices } from "./mock-data";
import { Service, Tier } from "./types";

interface HaalandStore {
  services: Service[];
  addService: (input: {
    name: string;
    repoUrl: string;
    baseBranch: string;
    tier: Tier;
    ownerTeam: string;
  }) => void;
  recordTriggeredIncident: (serviceId: string, reference: string) => void;
}

export const useHaalandStore = create<HaalandStore>()(
  persist(
    (set) => ({
      services: initialServices,

      addService: (input) =>
        set((state) => ({
          services: [
            ...state.services,
            {
              id: `svc-${input.name.toLowerCase().replace(/[^a-z0-9]+/g, "-")}-${Date.now().toString(36)}`,
              name: input.name,
              repoUrl: input.repoUrl,
              baseBranch: input.baseBranch || "main",
              ownerTeam: input.ownerTeam,
              tier: input.tier,
              incidentReferences: [],
            },
          ],
        })),

      recordTriggeredIncident: (serviceId, reference) =>
        set((state) => ({
          services: state.services.map((s) =>
            s.id === serviceId
              ? { ...s, incidentReferences: [reference, ...s.incidentReferences] }
              : s
          ),
        })),
    }),
    { name: "haaland-services" }
  )
);
