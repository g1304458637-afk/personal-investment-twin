/** Demo fixtures and live responses obey the same subject/account boundary. */
export function reviewPackBelongsToAccount(
  pack: { subjectId: string; accountId: string },
  subjectId: string,
  accountId: string,
): boolean {
  return pack.subjectId === subjectId && pack.accountId === accountId;
}
