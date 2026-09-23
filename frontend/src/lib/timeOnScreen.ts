import { useEffect, useRef, type RefObject } from 'react';

/** Milliseconds an element has been at least half visible while the page is visible. Returns a
 * getter; the getter yields null where the browser cannot measure it (no IntersectionObserver), so
 * feedback never carries an invented reading time (B4's noise heuristic compares it to a floor). */
export function useTimeOnScreen(ref: RefObject<HTMLElement | null>): () => number | null {
  const total = useRef(0);
  const since = useRef<number | null>(null);
  const supported = typeof IntersectionObserver !== 'undefined';

  useEffect(() => {
    const el = ref.current;
    if (!supported || !el) return undefined;
    const stop = () => {
      if (since.current !== null) total.current += performance.now() - since.current;
      since.current = null;
    };
    const io = new IntersectionObserver((entries) => {
      const visible = entries.some((e) => e.isIntersecting && e.intersectionRatio >= 0.5);
      if (visible && since.current === null && document.visibilityState !== 'hidden') since.current = performance.now();
      if (!visible) stop();
    }, { threshold: [0, 0.5, 1] });
    io.observe(el);
    const onVisibility = () => { if (document.visibilityState === 'hidden') stop(); };
    document.addEventListener('visibilitychange', onVisibility);
    return () => { stop(); io.disconnect(); document.removeEventListener('visibilitychange', onVisibility); };
  }, [ref, supported]);

  return () => {
    if (!supported) return null;
    const running = since.current !== null ? performance.now() - since.current : 0;
    return Math.round(total.current + running);
  };
}
