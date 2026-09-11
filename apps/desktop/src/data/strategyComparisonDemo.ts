import source from "@/generated/strategy-comparison-demo.json";

import { adaptStrategyComparison } from "./strategyComparison.ts";

/** Vite-only binding of the generated comparison artifact. */
export const strategyComparison = adaptStrategyComparison(source);
