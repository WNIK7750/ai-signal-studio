"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import { AppearanceProvider } from "@/components/appearance-provider";

export function Providers({ children }: { children: React.ReactNode }) {
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: { staleTime: 15_000, retry: 1 },
        },
      }),
  );
  return (
    <AppearanceProvider>
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    </AppearanceProvider>
  );
}
