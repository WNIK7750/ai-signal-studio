"use client";

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useSyncExternalStore,
} from "react";
import {
  applyAppearance,
  DEFAULT_APPEARANCE,
  readAppearance,
  writeAppearancePatch,
  type AppearanceSettings,
} from "@/lib/appearance";

type AppearanceContextValue = {
  appearance: AppearanceSettings;
  updateAppearance(patch: Partial<AppearanceSettings>): void;
};

const AppearanceContext = createContext<AppearanceContextValue | null>(null);
const listeners = new Set<() => void>();
let currentAppearance: AppearanceSettings | undefined;

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function getClientSnapshot() {
  if (!currentAppearance) {
    currentAppearance = readAppearance(window.localStorage).value;
  }
  return currentAppearance;
}

function getServerSnapshot() {
  return DEFAULT_APPEARANCE;
}

export function AppearanceProvider({
  children,
}: {
  children: React.ReactNode;
}) {
  const appearance = useSyncExternalStore(
    subscribe,
    getClientSnapshot,
    getServerSnapshot,
  );

  const updateAppearance = useCallback(
    (patch: Partial<AppearanceSettings>) => {
      const next = { ...getClientSnapshot(), ...patch };
      currentAppearance = next;
      applyAppearance(document.documentElement, next);
      writeAppearancePatch(window.localStorage, patch);
      listeners.forEach((listener) => listener());
    },
    [],
  );

  const contextValue = useMemo(
    () => ({ appearance, updateAppearance }),
    [appearance, updateAppearance],
  );

  return (
    <AppearanceContext.Provider value={contextValue}>
      {children}
    </AppearanceContext.Provider>
  );
}

export function useAppearance() {
  const value = useContext(AppearanceContext);
  if (!value) {
    throw new Error("useAppearance must be used inside AppearanceProvider");
  }
  return value;
}
