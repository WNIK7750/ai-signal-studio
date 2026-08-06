import { clampToken, themePresets, type ThemeId } from "./themes";

export type AppearanceSettings = {
  theme: ThemeId;
  radius: number;
  density: number;
  fontSize: number;
};

export type AppearanceKey = keyof AppearanceSettings;

export type AppearanceStorage = {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
};

export type AppearanceTarget = {
  dataset: { theme?: string };
  style: { setProperty(name: string, value: string): void };
};

export const DEFAULT_APPEARANCE: AppearanceSettings = {
  theme: "signal-light",
  radius: 10,
  density: 12,
  fontSize: 15,
};

const STORAGE_KEYS: Record<AppearanceKey, string> = {
  theme: "ai-signal-theme",
  radius: "ai-signal-radius",
  density: "ai-signal-density",
  fontSize: "ai-signal-font-size",
};

const TOKEN_LIMITS: Record<
  Exclude<AppearanceKey, "theme">,
  readonly [number, number]
> = {
  radius: [4, 20],
  density: [8, 20],
  fontSize: [13, 18],
};

const themeIds = new Set<ThemeId>(themePresets.map((preset) => preset.id));

export function readAppearance(storage: AppearanceStorage): {
  value: AppearanceSettings;
  correctedKeys: AppearanceKey[];
} {
  try {
    const correctedKeys: AppearanceKey[] = [];
    const storedTheme = storage.getItem(STORAGE_KEYS.theme);
    const theme =
      storedTheme === null
        ? DEFAULT_APPEARANCE.theme
        : themeIds.has(storedTheme as ThemeId)
          ? (storedTheme as ThemeId)
          : markCorrection(
              correctedKeys,
              "theme",
              DEFAULT_APPEARANCE.theme,
            );

    const radius = readNumberToken(
      storage.getItem(STORAGE_KEYS.radius),
      "radius",
      correctedKeys,
    );
    const density = readNumberToken(
      storage.getItem(STORAGE_KEYS.density),
      "density",
      correctedKeys,
    );
    const fontSize = readNumberToken(
      storage.getItem(STORAGE_KEYS.fontSize),
      "fontSize",
      correctedKeys,
    );

    return {
      value: { theme, radius, density, fontSize },
      correctedKeys,
    };
  } catch {
    return { value: DEFAULT_APPEARANCE, correctedKeys: [] };
  }
}

export function writeAppearancePatch(
  storage: AppearanceStorage,
  patch: Partial<AppearanceSettings>,
) {
  for (const key of Object.keys(STORAGE_KEYS) as AppearanceKey[]) {
    const value = patch[key];
    if (value === undefined) {
      continue;
    }
    try {
      storage.setItem(STORAGE_KEYS[key], String(value));
    } catch {
      // Browsers may disable or reject local storage. The in-memory UI still works.
    }
  }
}

export function applyAppearance(
  target: AppearanceTarget,
  appearance: AppearanceSettings,
) {
  target.dataset.theme = appearance.theme;
  target.style.setProperty("--radius", `${appearance.radius}px`);
  target.style.setProperty("--density", `${appearance.density}px`);
  target.style.setProperty("--base-font-size", `${appearance.fontSize}px`);
}

export const APPEARANCE_BOOTSTRAP_SCRIPT = createAppearanceBootstrapScript();

function readNumberToken(
  raw: string | null,
  key: Exclude<AppearanceKey, "theme">,
  correctedKeys: AppearanceKey[],
) {
  const fallback = DEFAULT_APPEARANCE[key];
  if (raw === null) {
    return fallback;
  }

  const parsed = raw.trim() === "" ? Number.NaN : Number(raw);
  if (!Number.isFinite(parsed)) {
    return markCorrection(correctedKeys, key, fallback);
  }

  const [min, max] = TOKEN_LIMITS[key];
  const normalized = clampToken(parsed, min, max);
  if (normalized !== parsed) {
    correctedKeys.push(key);
  }
  return normalized;
}

function markCorrection<Key extends AppearanceKey>(
  correctedKeys: AppearanceKey[],
  key: Key,
  fallback: AppearanceSettings[Key],
) {
  correctedKeys.push(key);
  return fallback;
}

function createAppearanceBootstrapScript() {
  const defaults = JSON.stringify(DEFAULT_APPEARANCE);
  const keys = JSON.stringify(STORAGE_KEYS);
  const limits = JSON.stringify(TOKEN_LIMITS);
  const themes = JSON.stringify([...themeIds]);

  return `(function(){try{
var d=${defaults},k=${keys},l=${limits},t=${themes},s=window.localStorage;
var rawTheme=s.getItem(k.theme),theme=rawTheme===null?d.theme:rawTheme;
if(t.indexOf(theme)===-1){theme=d.theme;s.setItem(k.theme,theme);}
function numberToken(name){
  var raw=s.getItem(k[name]),fallback=d[name];
  if(raw===null)return fallback;
  var parsed=raw.trim()===""?NaN:Number(raw);
  if(!Number.isFinite(parsed)){s.setItem(k[name],String(fallback));return fallback;}
  var value=Math.min(l[name][1],Math.max(l[name][0],parsed));
  if(value!==parsed)s.setItem(k[name],String(value));
  return value;
}
var radius=numberToken("radius"),density=numberToken("density"),fontSize=numberToken("fontSize");
var root=document.documentElement;
root.dataset.theme=theme;
root.style.setProperty("--radius",radius+"px");
root.style.setProperty("--density",density+"px");
root.style.setProperty("--base-font-size",fontSize+"px");
}catch(e){}})();`;
}
