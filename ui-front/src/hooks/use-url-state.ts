"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

type UrlStateShape = Record<string, string>;

type SetUrlStateAction<T extends UrlStateShape> = Partial<T> | ((previous: T) => Partial<T> | T);

function readUrlState<T extends UrlStateShape>(searchParams: URLSearchParams | ReadonlyURLSearchParamsLike, defaults: T): T {
  const nextState = { ...defaults };
  for (const key of Object.keys(defaults) as Array<keyof T>) {
    const value = searchParams.get(String(key));
    if (value != null) {
      nextState[key] = value as T[keyof T];
    }
  }
  return nextState;
}

function stateSignature<T extends UrlStateShape>(state: T) {
  return Object.entries(state)
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([key, value]) => `${key}=${value}`)
    .join("&");
}

type ReadonlyURLSearchParamsLike = {
  get(name: string): string | null;
  toString(): string;
};

export function useUrlState<T extends UrlStateShape>(defaults: T) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const initialStateRef = useRef<T | null>(null);

  if (!initialStateRef.current) {
    initialStateRef.current = readUrlState(searchParams, defaults);
  }

  const [state, setState] = useState<T>(initialStateRef.current);
  const urlState = useMemo(() => readUrlState(searchParams, defaults), [defaults, searchParams]);
  const localSignature = useMemo(() => stateSignature(state), [state]);
  const urlSignature = useMemo(() => stateSignature(urlState), [urlState]);

  useEffect(() => {
    if (localSignature === urlSignature) return;
    setState((previous) => {
      if (stateSignature(previous) === urlSignature) return previous;
      return urlState;
    });
  }, [localSignature, urlSignature, urlState]);

  useEffect(() => {
    if (localSignature === urlSignature) return;
    const nextParams = new URLSearchParams(searchParams.toString());

    for (const key of Object.keys(defaults) as Array<keyof T>) {
      const value = state[key];
      const defaultValue = defaults[key];
      if (!value || value === defaultValue) {
        nextParams.delete(String(key));
      } else {
        nextParams.set(String(key), value);
      }
    }

    const nextQuery = nextParams.toString();
    router.replace(nextQuery ? `${pathname}?${nextQuery}` : pathname, { scroll: false });
  }, [defaults, localSignature, pathname, router, searchParams, state, urlSignature]);

  const updateState = useCallback((action: SetUrlStateAction<T>) => {
    setState((previous) => {
      const patch = typeof action === "function" ? action(previous) : action;
      return { ...previous, ...patch };
    });
  }, []);

  const resetState = useCallback(() => {
    setState(defaults);
  }, [defaults]);

  return { state, setState: updateState, resetState };
}
