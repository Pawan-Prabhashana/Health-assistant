// Typed bindings for the health and config endpoints. The shapes mirror the
// backend Pydantic models in `sahana_api.schemas.health`.

import { apiGet } from './client';

export interface LivenessResponse {
  status: 'alive';
}

export interface Check {
  name: string;
  ok: boolean;
  detail: string | null;
}

export interface ReadinessResponse {
  ready: boolean;
  checks: Check[];
}

export interface ConfigResponse {
  app_name: string;
  app_env: string;
  version: string;
  log_level: string;
  features: Record<string, boolean>;
}

export function getLiveness(signal?: AbortSignal): Promise<LivenessResponse> {
  return apiGet<LivenessResponse>('/health/live', signal);
}

export function getReadiness(signal?: AbortSignal): Promise<ReadinessResponse> {
  return apiGet<ReadinessResponse>('/health/ready', signal);
}

export function getConfig(signal?: AbortSignal): Promise<ConfigResponse> {
  return apiGet<ConfigResponse>('/config', signal);
}
