import { normalizeWheelDeltaPixels } from "./dailyTimeNavigation.ts";

/** Forward an ordinary vertical wheel to the enclosing scrollable page, not a chart zoom. */
export function forwardChartPageScroll(
  container: HTMLElement,
  event: Pick<WheelEvent, "deltaY" | "deltaMode" | "cancelable" | "preventDefault">,
  overflowY = (element: HTMLElement) => getComputedStyle(element).overflowY,
): boolean {
  let scroller = container.parentElement;
  while (scroller) {
    const movable = event.deltaY < 0 ? scroller.scrollTop > 0 : scroller.scrollTop + scroller.clientHeight < scroller.scrollHeight;
    if (movable && /auto|scroll/.test(overflowY(scroller))) {
      if (!event.cancelable) return false;
      event.preventDefault();
      scroller.scrollBy({ top: normalizeWheelDeltaPixels(event.deltaY, event.deltaMode), behavior: "instant" });
      return true;
    }
    scroller = scroller.parentElement;
  }
  return false;
}
