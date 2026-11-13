import { ThemeId, WorkspaceSettings } from "../types/agent";

export interface ThemeTokens {
  bgCanvas: string;
  bgSurface: string;
  bgCard: string;
  bgMuted: string;
  textPrimary: string;
  textHeading: string;
  textMuted: string;
  accentPrimary: string;
  accentPrimaryFg: string;
  accentWarm: string;
  borderSubtle: string;
  borderStrong: string;
  ringActive: string;
}

export interface ThemeDefinition {
  id: ThemeId;
  label: string;
  swatchHex: string;
  swatchRingHex: string;
  light: ThemeTokens;
  dark: ThemeTokens;
}

export const THEME_DEFINITIONS: ThemeDefinition[] = [
  {
    id: ThemeId.Mono,
    label: "Mono",
    // Pure black / white / gray: no hue at all.
    swatchHex: "#8C8C8C",
    swatchRingHex: "#111111",
    light: {
      bgCanvas: "#EDEDED",
      bgSurface: "#FFFFFF",
      bgCard: "#E0E0E0",
      bgMuted: "#E8E8E8",
      textPrimary: "#1A1A1A",
      textHeading: "#000000",
      textMuted: "#6B6B6B",
      accentPrimary: "#111111",
      accentPrimaryFg: "#FFFFFF",
      accentWarm: "#7A7A7A",
      borderSubtle: "#D2D2D2",
      borderStrong: "#B5B5B5",
      ringActive: "#111111",
    },
    dark: {
      bgCanvas: "#0A0A0A",
      bgSurface: "#121212",
      bgCard: "#1C1C1C",
      bgMuted: "#161616",
      textPrimary: "#E6E6E6",
      textHeading: "#FFFFFF",
      textMuted: "#9A9A9A",
      accentPrimary: "#F2F2F2",
      accentPrimaryFg: "#0A0A0A",
      accentWarm: "#A8A8A8",
      borderSubtle: "#2A2A2A",
      borderStrong: "#3F3F3F",
      ringActive: "#F2F2F2",
    },
  },
  {
    id: ThemeId.Ink,
    label: "Ink",
    swatchHex: "#C7B5AD",
    swatchRingHex: "#2E2320",
    light: {
      bgCanvas: "#EAE3DF",
      bgSurface: "#F6F1EE",
      bgCard: "#DDD3CD",
      bgMuted: "#E4DCD7",
      textPrimary: "#29201D",
      textHeading: "#362A26",
      textMuted: "#786862",
      accentPrimary: "#302421",
      accentPrimaryFg: "#F6F1EE",
      accentWarm: "#947E75",
      borderSubtle: "#CFC3BC",
      borderStrong: "#BAAEA6",
      ringActive: "#2E2320",
    },
    dark: {
      bgCanvas: "#151312",
      bgSurface: "#1E1B1A",
      bgCard: "#282422",
      bgMuted: "#221F1D",
      textPrimary: "#E9E3DF",
      textHeading: "#F4F0ED",
      textMuted: "#998D87",
      accentPrimary: "#C7B5AD",
      accentPrimaryFg: "#151312",
      accentWarm: "#947E75",
      borderSubtle: "#302B29",
      borderStrong: "#453E3B",
      ringActive: "#C7B5AD",
    },
  },
  {
    id: ThemeId.Stone,
    label: "Stone",
    swatchHex: "#EAE0D3",
    swatchRingHex: "#591D19",
    light: {
      bgCanvas: "#EFE8DD",
      bgSurface: "#F9F5EE",
      bgCard: "#E4DBD0",
      bgMuted: "#EAE1D5",
      textPrimary: "#4A2B24",
      textHeading: "#5C2C23",
      textMuted: "#8C7566",
      accentPrimary: "#59201A",
      accentPrimaryFg: "#FBF7F2",
      accentWarm: "#C59B7B",
      borderSubtle: "#DFD4C6",
      borderStrong: "#CBBBA8",
      ringActive: "#591D19",
    },
    dark: {
      bgCanvas: "#1B1614",
      bgSurface: "#241E1B",
      bgCard: "#2E2622",
      bgMuted: "#28211E",
      textPrimary: "#EDE5DB",
      textHeading: "#F7F0E6",
      textMuted: "#A49082",
      accentPrimary: "#D4A582",
      accentPrimaryFg: "#1B1614",
      accentWarm: "#C59B7B",
      borderSubtle: "#362D28",
      borderStrong: "#4A3E37",
      ringActive: "#D4A582",
    },
  },
  {
    id: ThemeId.Moss,
    label: "Moss",
    swatchHex: "#C2BCA8",
    swatchRingHex: "#36442E",
    light: {
      bgCanvas: "#EAEAE1",
      bgSurface: "#F5F5EE",
      bgCard: "#DFE1D4",
      bgMuted: "#E5E6DA",
      textPrimary: "#2C3626",
      textHeading: "#37462F",
      textMuted: "#6E7865",
      accentPrimary: "#37462F",
      accentPrimaryFg: "#F6F7F2",
      accentWarm: "#8F9E7B",
      borderSubtle: "#D3D6C6",
      borderStrong: "#BCC1AC",
      ringActive: "#36442E",
    },
    dark: {
      bgCanvas: "#161A15",
      bgSurface: "#1E241C",
      bgCard: "#272F25",
      bgMuted: "#222920",
      textPrimary: "#E5EAE1",
      textHeading: "#F1F5ED",
      textMuted: "#929D8B",
      accentPrimary: "#A8B894",
      accentPrimaryFg: "#161A15",
      accentWarm: "#8F9E7B",
      borderSubtle: "#2F382C",
      borderStrong: "#414D3D",
      ringActive: "#A8B894",
    },
  },
  {
    id: ThemeId.Mist,
    label: "Mist",
    swatchHex: "#DACAC0",
    swatchRingHex: "#523B36",
    light: {
      bgCanvas: "#EFEAE6",
      bgSurface: "#FAF6F4",
      bgCard: "#E4DBD5",
      bgMuted: "#EAE2DC",
      textPrimary: "#3F302D",
      textHeading: "#543D38",
      textMuted: "#8A7670",
      accentPrimary: "#543D38",
      accentPrimaryFg: "#FAF6F4",
      accentWarm: "#B89E93",
      borderSubtle: "#DBD0C9",
      borderStrong: "#C6B8B0",
      ringActive: "#523B36",
    },
    dark: {
      bgCanvas: "#1A1716",
      bgSurface: "#231F1E",
      bgCard: "#2D2726",
      bgMuted: "#272221",
      textPrimary: "#ECE6E3",
      textHeading: "#F6F1EE",
      textMuted: "#A1928D",
      accentPrimary: "#CEB3A8",
      accentPrimaryFg: "#1A1716",
      accentWarm: "#B89E93",
      borderSubtle: "#362F2D",
      borderStrong: "#4A403E",
      ringActive: "#CEB3A8",
    },
  },
  {
    id: ThemeId.Clay,
    label: "Clay",
    swatchHex: "#D6B598",
    swatchRingHex: "#69311E",
    light: {
      bgCanvas: "#F1E5D8",
      bgSurface: "#FAF2E9",
      bgCard: "#E6D4C0",
      bgMuted: "#ECDDCC",
      textPrimary: "#4D281B",
      textHeading: "#69311E",
      textMuted: "#916E5B",
      accentPrimary: "#69311E",
      accentPrimaryFg: "#FAF2E9",
      accentWarm: "#C88F68",
      borderSubtle: "#DFC9B2",
      borderStrong: "#CCB094",
      ringActive: "#69311E",
    },
    dark: {
      bgCanvas: "#1D1612",
      bgSurface: "#271E19",
      bgCard: "#332720",
      bgMuted: "#2C221C",
      textPrimary: "#F0E5DA",
      textHeading: "#FAF0E6",
      textMuted: "#AC8E7B",
      accentPrimary: "#DBA17A",
      accentPrimaryFg: "#1D1612",
      accentWarm: "#C88F68",
      borderSubtle: "#3B2D25",
      borderStrong: "#523E33",
      ringActive: "#DBA17A",
    },
  },
  {
    id: ThemeId.Dusk,
    label: "Dusk",
    swatchHex: "#CDBAC3",
    swatchRingHex: "#4B2E3E",
    light: {
      bgCanvas: "#ECE5E9",
      bgSurface: "#F7F2F5",
      bgCard: "#DFD3DA",
      bgMuted: "#E6DCE2",
      textPrimary: "#382430",
      textHeading: "#4E3041",
      textMuted: "#826B78",
      accentPrimary: "#4E3041",
      accentPrimaryFg: "#F7F2F5",
      accentWarm: "#A88998",
      borderSubtle: "#D5C6CF",
      borderStrong: "#BFAEB8",
      ringActive: "#4B2E3E",
    },
    dark: {
      bgCanvas: "#191518",
      bgSurface: "#221C21",
      bgCard: "#2C242A",
      bgMuted: "#261F25",
      textPrimary: "#ECE4E9",
      textHeading: "#F6EFF3",
      textMuted: "#A08C98",
      accentPrimary: "#C6A6B7",
      accentPrimaryFg: "#191518",
      accentWarm: "#A88998",
      borderSubtle: "#362C33",
      borderStrong: "#4B3D47",
      ringActive: "#C6A6B7",
    },
  },
  {
    id: ThemeId.Sakura,
    label: "Sakura",
    swatchHex: "#E0C2B5",
    swatchRingHex: "#612B27",
    light: {
      bgCanvas: "#F3E7E1",
      bgSurface: "#FCF5F2",
      bgCard: "#E9D7CE",
      bgMuted: "#EFE0D8",
      textPrimary: "#4A2522",
      textHeading: "#632D29",
      textMuted: "#916E68",
      accentPrimary: "#632D29",
      accentPrimaryFg: "#FCF5F2",
      accentWarm: "#CC9786",
      borderSubtle: "#E1CBBF",
      borderStrong: "#CEB3A5",
      ringActive: "#612B27",
    },
    dark: {
      bgCanvas: "#1D1615",
      bgSurface: "#261D1C",
      bgCard: "#322624",
      bgMuted: "#2B211F",
      textPrimary: "#F2E6E2",
      textHeading: "#FBF1EE",
      textMuted: "#AD8C86",
      accentPrimary: "#E0AB9B",
      accentPrimaryFg: "#1D1615",
      accentWarm: "#CC9786",
      borderSubtle: "#3B2D2B",
      borderStrong: "#523E3B",
      ringActive: "#E0AB9B",
    },
  },

  {
    id: ThemeId.Emerald,
    label: "Emerald",
    swatchHex: "#183A2E",
    swatchRingHex: "#D4AF7A",
    light: {
      bgCanvas: "#F6F3EB",
      bgSurface: "#FCFAF4",
      bgCard: "#ECE5D6",
      bgMuted: "#F1EBE0",
      textPrimary: "#10251E",
      textHeading: "#0A1D17",
      textMuted: "#4B6B5E",
      accentPrimary: "#B88D54",
      accentPrimaryFg: "#FCFAF4",
      accentWarm: "#C99F65",
      borderSubtle: "#DCD4C2",
      borderStrong: "#C3B9A4",
      ringActive: "#1A4233",
    },
    dark: {
      bgCanvas: "#0A1612",
      bgSurface: "#10221B",
      bgCard: "#162B22",
      bgMuted: "#12241D",
      textPrimary: "#F3EFE6",
      textHeading: "#FBF8F1",
      textMuted: "#87A598",
      accentPrimary: "#D4AF7A",
      accentPrimaryFg: "#101814",
      accentWarm: "#D4AF7A",
      borderSubtle: "#1D382E",
      borderStrong: "#2C5243",
      ringActive: "#D4AF7A",
    },
  },
  {
    id: ThemeId.Ember,
    label: "Ember",
    swatchHex: "#F6F0E7",
    swatchRingHex: "#9E3223",
    light: {
      bgCanvas: "#F6F0E7",
      bgSurface: "#FAF6F0",
      bgCard: "#ECE4D6",
      bgMuted: "#E5DCCF",
      textPrimary: "#141D2B",
      textHeading: "#101824",
      textMuted: "#546479",
      accentPrimary: "#9E3223",
      accentPrimaryFg: "#FAF6F0",
      accentWarm: "#9E3223",
      borderSubtle: "#DCD2C4",
      borderStrong: "#C5B9A6",
      ringActive: "#9E3223",
    },
    dark: {
      bgCanvas: "#0E141E",
      bgSurface: "#151E2B",
      bgCard: "#1D2838",
      bgMuted: "#192332",
      textPrimary: "#EDE8DF",
      textHeading: "#F8F5EE",
      textMuted: "#8998AC",
      accentPrimary: "#D75F4B",
      accentPrimaryFg: "#0E141E",
      accentWarm: "#D75F4B",
      borderSubtle: "#243144",
      borderStrong: "#33455E",
      ringActive: "#D75F4B",
    },
  },
];

export function applyWorkspaceTheme(settings: WorkspaceSettings): void {
  const def =
    THEME_DEFINITIONS.find((t) => t.id === settings.theme) ||
    THEME_DEFINITIONS[0];
  const tokens = settings.darkMode ? def.dark : def.light;
  const root = document.documentElement;
  root.classList.toggle("dark", Boolean(settings.darkMode));
  root.style.setProperty("--bg-canvas", tokens.bgCanvas);
  root.style.setProperty("--bg-surface", tokens.bgSurface);
  root.style.setProperty("--bg-card", tokens.bgCard);
  root.style.setProperty("--bg-muted", tokens.bgMuted);
  root.style.setProperty("--text-primary", tokens.textPrimary);
  root.style.setProperty("--text-heading", tokens.textHeading);
  root.style.setProperty("--text-muted", tokens.textMuted);
  root.style.setProperty("--accent-primary", tokens.accentPrimary);
  root.style.setProperty("--accent-primary-fg", tokens.accentPrimaryFg);
  root.style.setProperty("--accent-warm", tokens.accentWarm);
  root.style.setProperty("--border-subtle", tokens.borderSubtle);
  root.style.setProperty("--border-strong", tokens.borderStrong);
  root.style.setProperty("--ring-active", tokens.ringActive);
  root.style.setProperty(
    "--heading-scale",
    String(settings.headingScale / 100)
  );
  root.style.setProperty("--body-scale", String(settings.bodyScale / 100));
}
