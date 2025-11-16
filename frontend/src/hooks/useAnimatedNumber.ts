import { useEffect, useRef, useState } from "react";

export interface AnimatedNumberOptions {
  duration?: number;
  easing?: (progress: number) => number;
}

const easeOutCubic = (t: number) => 1 - Math.pow(1 - t, 3);

const getNow = () =>
  typeof performance !== "undefined" ? performance.now() : Date.now();

const isFiniteNumber = (value?: number): value is number =>
  typeof value === "number" && Number.isFinite(value);

export const useAnimatedNumber = (
  value?: number,
  options?: AnimatedNumberOptions
) => {
  const { duration = 800, easing = easeOutCubic } = options ?? {};
  const frameRef = useRef<number>();
  const startTimeRef = useRef<number>(0);
  const startValueRef = useRef<number>(0);
  const targetRef = useRef<number>(0);
  const lastValueRef = useRef<number | undefined>(value);
  const [displayValue, setDisplayValue] = useState<number | undefined>(value);

  useEffect(() => {
    if (!isFiniteNumber(value)) {
      setDisplayValue(undefined);
      targetRef.current = 0;
      lastValueRef.current = undefined;
      return undefined;
    }

    const initialValue = isFiniteNumber(lastValueRef.current)
      ? (lastValueRef.current as number)
      : value;

    startTimeRef.current = getNow();
    startValueRef.current = initialValue;
    targetRef.current = value;

    const animate = () => {
      const elapsed = getNow() - startTimeRef.current;
      const progress = Math.min(elapsed / duration, 1);
      const eased = easing(progress);
      const nextValue =
        startValueRef.current +
        (targetRef.current - startValueRef.current) * eased;
      setDisplayValue(nextValue);

      if (progress < 1) {
        frameRef.current = requestAnimationFrame(animate);
      } else {
        lastValueRef.current = targetRef.current;
      }
    };

    frameRef.current = requestAnimationFrame(animate);

    return () => {
      if (frameRef.current) {
        cancelAnimationFrame(frameRef.current);
      }
    };
  }, [value, duration, easing]);

  return displayValue;
};

export default useAnimatedNumber;
