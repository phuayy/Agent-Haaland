import { apiGet, apiPost } from "./client";
import type { Service, ServiceCreate, ServiceIncidentSummary } from "./types";

export const listServices = () => apiGet<Service[]>("/api/services");

export const getService = (id: string) => apiGet<Service>(`/api/services/${encodeURIComponent(id)}`);

export const createService = (body: ServiceCreate) => apiPost<Service>("/api/services", body);

export const listServiceIncidents = (id: string) =>
  apiGet<ServiceIncidentSummary[]>(`/api/services/${encodeURIComponent(id)}/incidents`);
