export const INSPECTOR_TYPES = ["evidence"] as const;
export type InspectorType = (typeof INSPECTOR_TYPES)[number];

export interface InspectorUrlState {
  readonly type: InspectorType;
  readonly targetId: string;
}

const SAFE_SEMANTIC_ID = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,159}$/;

export function isSafeInspectorTargetId(value: string): boolean {
  return SAFE_SEMANTIC_ID.test(value);
}

export function parseInspectorState(search: string): InspectorUrlState | null {
  const params = new URLSearchParams(search);
  const type = params.get("inspect");
  const targetId = params.get("id");
  if (type !== "evidence" || targetId === null || !isSafeInspectorTargetId(targetId)) return null;
  return { type, targetId };
}

export function withInspectorState(search: string, state: InspectorUrlState): string {
  if (!isSafeInspectorTargetId(state.targetId) || !INSPECTOR_TYPES.includes(state.type)) {
    throw new Error("Inspector state is not allowlisted.");
  }
  const params = new URLSearchParams(search);
  params.set("inspect", state.type);
  params.set("id", state.targetId);
  const encoded = params.toString();
  return encoded ? `?${encoded}` : "";
}

export function withoutInspectorState(search: string): string {
  const params = new URLSearchParams(search);
  params.delete("inspect");
  params.delete("id");
  const encoded = params.toString();
  return encoded ? `?${encoded}` : "";
}
