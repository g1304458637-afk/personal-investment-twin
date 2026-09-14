import source from "@/generated/review-pack-demo.json";

import { adaptReviewPack } from "./reviewPack.ts";

/**
 * Vite-only binding of the account-level review pack demo artifact.
 *
 * src/generated/review-pack-demo.json is produced by the backend script
 * (regenerate it there when the demo universe changes) and describes the demo
 * universe, which may use its own subject/account ids. The fail-closed adapter
 * in reviewPack.ts validates it exactly like a runtime response.
 */
export const reviewPackDemo = adaptReviewPack(source);
