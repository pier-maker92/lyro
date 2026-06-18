import { Ionicons } from "@expo/vector-icons";

export const MOODS = ["love", "adventure", "funny", "chill", "party"] as const;

export type Mood = (typeof MOODS)[number];

type IconName = keyof typeof Ionicons.glyphMap;

export interface MoodMeta {
  label: string;
  color: string;
  icon: IconName;
}

export const MOOD_META: Record<Mood, MoodMeta> = {
  love: { label: "Amore", color: "#FF4D6D", icon: "heart" },
  adventure: { label: "Avventura", color: "#22D3EE", icon: "compass" },
  funny: { label: "Divertente", color: "#FACC15", icon: "happy" },
  chill: { label: "Relax", color: "#34D399", icon: "leaf" },
  party: { label: "Festa", color: "#A855F7", icon: "sparkles" },
};
