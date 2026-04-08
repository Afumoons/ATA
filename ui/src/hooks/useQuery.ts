import { useEffect, useState } from 'react';

export interface QueryState<T> {
  data: T | null;
  error: string | null;
  loading: boolean;
}

export function useQuery<T>(queryKey: string, fetcher: () => Promise<T>) {
  const [state, setState] = useState<QueryState<T>>({
    data: null,
    error: null,
    loading: true,
  });

  useEffect(() => {
    let mounted = true;
    setState({ data: null, error: null, loading: true });

    fetcher()
      .then((data) => {
        if (!mounted) return;
        setState({ data, error: null, loading: false });
      })
      .catch((error: unknown) => {
        if (!mounted) return;
        const message = error instanceof Error ? error.message : 'Unknown error';
        setState({ data: null, error: message, loading: false });
      });

    return () => {
      mounted = false;
    };
  }, [queryKey]);

  return state;
}
