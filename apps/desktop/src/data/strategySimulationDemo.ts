import source from "@/generated/strategy-simulation-demo.json";

import { adaptStrategySimulation } from "./strategySimulation.ts";

/** Vite-only binding of the generated artifact; the adapter itself stays node-testable. */
export const strategySimulation = adaptStrategySimulation(source);
