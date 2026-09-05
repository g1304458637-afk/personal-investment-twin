import type { RuntimeAccount } from "./runtimeService";

/** Ignore both stale successes and stale failures of an account-list read. */
export async function readCurrentAccounts(
  load: () => Promise<{ accounts: RuntimeAccount[] }>,
  isCurrent: () => boolean,
): Promise<{ accounts: RuntimeAccount[] } | null> {
  try {
    const result = await load();
    return isCurrent() ? result : null;
  } catch (error) {
    if (!isCurrent()) return null;
    throw error;
  }
}
