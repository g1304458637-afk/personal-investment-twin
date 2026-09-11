/** A presentation preference only; never stores an account, permission or data mode. */
export const WELCOME_PREFERENCE = "toujing.welcome.skip.v1";
export function welcomeStartupPath(storage: Pick<Storage, "getItem">): "/welcome" | "/investments" {
  try { return storage.getItem(WELCOME_PREFERENCE) === "true" ? "/investments" : "/welcome"; }
  catch { return "/welcome"; }
}
export function saveWelcomePreference(storage: Pick<Storage, "setItem">, skip: boolean): boolean {
  try { storage.setItem(WELCOME_PREFERENCE, String(skip)); return true; }
  catch { return false; }
}
