// Route-local, explicit and non-persistent. Never changes account/data scope.
export const OPTICAL_REVIEW = "optical-v1";

export function isOpticalReview(search: URLSearchParams): boolean {
  return search.get("visual") === OPTICAL_REVIEW;
}

export function opticalReviewSearch(search: URLSearchParams, enabled: boolean): URLSearchParams {
  const next = new URLSearchParams(search);
  if (enabled) next.set("visual", OPTICAL_REVIEW);
  else next.delete("visual");
  return next;
}
