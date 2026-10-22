import source from "@/generated/showcase-review-pack-demo.json";

import { adaptReviewPack } from "./reviewPack.ts";

/**
 * Vite-only binding of the account-level review pack demo artifact.
 *
 * src/generated/showcase-review-pack-demo.json is generated from the same
 * fictional account inputs as showcase-demo.json. The older independent
 * review-pack-demo.json remains a research fixture. The fail-closed adapter
 * in reviewPack.ts validates this pack like a runtime response.
 */
export const reviewPackDemo = adaptReviewPack(source);
