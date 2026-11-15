import { useEffect, useRef, useState } from "react";

/** Keeps a closing element on screen for its exit animation: returns the value to render (the last non-empty one while
 *  closing) and whether it is closing. `empty` is the "closed" value (false for a boolean, "none" for a panel name). */
export function usePresence<T>(value: T, empty: T, ms = 220): { shown: T; closing: boolean } {
  const [shown, setShown] = useState<T>(value);
  const [closing, setClosing] = useState(false);
  const timer = useRef<number | undefined>(undefined);
  useEffect(() => {
    window.clearTimeout(timer.current);
    if (value !== empty) {
      setShown(value);
      setClosing(false);
    } else if (shown !== empty) {
      setClosing(true);
      timer.current = window.setTimeout(() => {
        setShown(empty);
        setClosing(false);
      }, ms);
    }
    return () => window.clearTimeout(timer.current);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value]);
  return { shown, closing };
}
