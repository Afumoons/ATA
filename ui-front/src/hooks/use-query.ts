"use client";

import { useCallback, useEffect, useRef, useState } from "react";

interface UseQueryOptions {
  enabled?: boolean;
  refetchIntervalMs?: number;
}

type QueryStatus = "idle" | "loading" | "success" | "refreshing" | "error";

export function useQuery<T>(
  key: string,
  queryFn: () => Promise<T>,
  options: UseQueryOptions = {},
) {
  const { enabled = true, refetchIntervalMs } = options;
  const queryFnRef = useRef(queryFn);
  const hasDataRef = useRef(false);
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [status, setStatus] = useState<QueryStatus>(enabled ? "loading" : "idle");
  const [lastSuccessAt, setLastSuccessAt] = useState<number | null>(null);
  const [lastAttemptAt, setLastAttemptAt] = useState<number | null>(null);

  useEffect(() => {
    queryFnRef.current = queryFn;
  }, [queryFn]);

  useEffect(() => {
    hasDataRef.current = data !== null;
  }, [data]);

  const run = useCallback(async () => {
    if (!enabled) return;

    setLastAttemptAt(Date.now());
    setError(null);
    setStatus(hasDataRef.current ? "refreshing" : "loading");

    try {
      const result = await queryFnRef.current();
      setData(result);
      setLastSuccessAt(Date.now());
      setStatus("success");
    } catch (nextError) {
      setError(nextError);
      setStatus("error");
    }
  }, [enabled]);

  useEffect(() => {
    if (!enabled) return;

    const timeout = window.setTimeout(() => {
      void run();
    }, 0);

    return () => {
      window.clearTimeout(timeout);
    };
  }, [enabled, key, run]);

  useEffect(() => {
    if (!enabled || !refetchIntervalMs) return;

    const interval = window.setInterval(() => {
      void run();
    }, refetchIntervalMs);

    return () => {
      window.clearInterval(interval);
    };
  }, [enabled, refetchIntervalMs, run]);

  return {
    data,
    error,
    status,
    loading: status === "loading",
    refreshing: status === "refreshing",
    hasData: data !== null,
    lastSuccessAt,
    lastAttemptAt,
    refresh: run,
  };
}
