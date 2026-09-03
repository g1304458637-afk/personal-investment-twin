import { invoke, isTauri } from "@tauri-apps/api/core";

import {
  adaptPretradeImpact,
  type BackendPretradeImpact,
  type PretradeDemoView,
} from "./pretradeImpact.ts";

export type PretradeRuntime = "tauri_local" | "browser_offline_demo";

export interface PretradeCheckInput {
  subjectId: string;
  proposedTime: string;
  symbol: string;
  side: "BUY" | "SELL";
  quantity: number;
  executionPrice: number;
  fees: number;
}

interface PretradeBridgeRequest {
  request_id: string;
  action: "pretrade_check";
  payload: {
    subject_id: string;
    proposed_time: string;
    symbol: string;
    side: "BUY" | "SELL";
    quantity: number;
    execution_price: number;
    fees: number;
  };
}

interface PretradeBridgeResponse {
  request_id: string | null;
  ok: boolean;
  result: BackendPretradeImpact | null;
  error: { code: string; message: string } | null;
}

export interface PretradeCheckOutcome {
  requestId: string;
  runtime: PretradeRuntime;
  impact: PretradeDemoView;
}

export class PretradeServiceError extends Error {
  readonly code: string;
  readonly requestId: string;

  constructor(code: string, message: string, requestId: string) {
    super(message);
    this.name = "PretradeServiceError";
    this.code = code;
    this.requestId = requestId;
  }
}

type InvokePretrade = (
  command: string,
  args: { request: PretradeBridgeRequest },
) => Promise<PretradeBridgeResponse>;

interface ServiceOptions {
  runtime?: PretradeRuntime;
  requestId?: string;
  invokePretrade?: InvokePretrade;
  offlineDemo?: PretradeDemoView;
}

export function currentPretradeRuntime(): PretradeRuntime {
  return isTauri() ? "tauri_local" : "browser_offline_demo";
}

export function inputFromDemo(pretradeDemo: PretradeDemoView): PretradeCheckInput {
  return {
    subjectId: pretradeDemo.subjectId,
    proposedTime: pretradeDemo.proposedTime,
    symbol: pretradeDemo.symbol,
    side: pretradeDemo.side,
    quantity: pretradeDemo.quantity,
    executionPrice: pretradeDemo.executionPrice,
    fees: pretradeDemo.fees,
  };
}

export function createPretradeRequestId(): string {
  return globalThis.crypto?.randomUUID?.()
    ?? `pretrade-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function matchesOfflineDemo(input: PretradeCheckInput, offlineDemo: PretradeDemoView): boolean {
  const demo = inputFromDemo(offlineDemo);
  return input.subjectId === demo.subjectId
    && input.proposedTime === demo.proposedTime
    && input.symbol.trim().toUpperCase() === demo.symbol
    && input.side === demo.side
    && input.quantity === demo.quantity
    && input.executionPrice === demo.executionPrice
    && input.fees === demo.fees;
}

function finiteInput(input: PretradeCheckInput): void {
  for (const [name, value] of [
    ["quantity", input.quantity],
    ["execution price", input.executionPrice],
    ["fees", input.fees],
  ] as const) {
    if (!Number.isFinite(value)) {
      throw new Error(`${name} must be a finite number`);
    }
  }
}

export async function checkPretrade(
  input: PretradeCheckInput,
  options: ServiceOptions = {},
): Promise<PretradeCheckOutcome> {
  const id = options.requestId ?? createPretradeRequestId();
  const runtime = options.runtime ?? currentPretradeRuntime();
  try {
    finiteInput(input);
  } catch (error) {
    throw new PretradeServiceError(
      "invalid_input",
      error instanceof Error ? error.message : "invalid numeric input",
      id,
    );
  }

  if (runtime === "browser_offline_demo") {
    if (!options.offlineDemo || !matchesOfflineDemo(input, options.offlineDemo)) {
      throw new PretradeServiceError(
        "offline_demo_only",
        "Browser mode cannot run local Python. The generated offline demo is available only for its registered input.",
        id,
      );
    }
    return { requestId: id, runtime, impact: options.offlineDemo };
  }

  const request: PretradeBridgeRequest = {
    request_id: id,
    action: "pretrade_check",
    payload: {
      subject_id: input.subjectId,
      proposed_time: input.proposedTime,
      symbol: input.symbol.trim().toUpperCase(),
      side: input.side,
      quantity: input.quantity,
      execution_price: input.executionPrice,
      fees: input.fees,
    },
  };
  const call = options.invokePretrade ?? invoke<PretradeBridgeResponse>;
  let response: PretradeBridgeResponse;
  try {
    response = await call("run_pretrade_check", { request });
  } catch (error) {
    throw new PretradeServiceError(
      "tauri_invoke_failed",
      error instanceof Error ? error.message : String(error),
      id,
    );
  }
  if (response.request_id !== id) {
    throw new PretradeServiceError(
      "request_id_mismatch",
      "The local bridge returned a mismatched request ID.",
      id,
    );
  }
  if (!response.ok || !response.result) {
    throw new PretradeServiceError(
      response.error?.code ?? "bridge_error",
      response.error?.message ?? "The local pre-trade bridge returned no result.",
      id,
    );
  }
  return {
    requestId: id,
    runtime,
    impact: adaptPretradeImpact(response.result),
  };
}

export type PretradeRequestState =
  | { phase: "idle"; activeRequestId: null; outcome: null; error: null; stale: boolean }
  | { phase: "loading"; activeRequestId: string; outcome: null; error: null; stale: boolean }
  | { phase: "success"; activeRequestId: string; outcome: PretradeCheckOutcome; error: null; stale: false }
  | { phase: "error"; activeRequestId: string; outcome: null; error: PretradeServiceError; stale: false };

export type PretradeRequestAction =
  | { type: "input_changed" }
  | { type: "started"; requestId: string }
  | { type: "succeeded"; requestId: string; outcome: PretradeCheckOutcome }
  | { type: "failed"; requestId: string; error: PretradeServiceError };

export const emptyPretradeRequestState: PretradeRequestState = {
  phase: "idle",
  activeRequestId: null,
  outcome: null,
  error: null,
  stale: false,
};

export function pretradeRequestReducer(
  state: PretradeRequestState,
  action: PretradeRequestAction,
): PretradeRequestState {
  if (action.type === "input_changed") {
    return {
      phase: "idle",
      activeRequestId: null,
      outcome: null,
      error: null,
      stale: state.phase !== "idle" || state.stale,
    };
  }
  if (action.type === "started") {
    return {
      phase: "loading",
      activeRequestId: action.requestId,
      outcome: null,
      error: null,
      stale: state.stale,
    };
  }
  if (state.activeRequestId !== action.requestId) return state;
  if (action.type === "succeeded") {
    return {
      phase: "success",
      activeRequestId: action.requestId,
      outcome: action.outcome,
      error: null,
      stale: false,
    };
  }
  return {
    phase: "error",
    activeRequestId: action.requestId,
    outcome: null,
    error: action.error,
    stale: false,
  };
}
