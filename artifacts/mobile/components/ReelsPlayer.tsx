import { Ionicons } from "@expo/vector-icons";
import { Image } from "expo-image";
import * as Haptics from "expo-haptics";
import { LinearGradient } from "expo-linear-gradient";
import { StatusBar } from "expo-status-bar";
import React, {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import {
  Animated,
  Easing,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { Gesture, GestureDetector } from "react-native-gesture-handler";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { MOOD_META, MOODS } from "@/constants/moods";
import { VideoBackground } from "@/components/VideoBackground";
import type { PickedMedia } from "@/lib/media";
import type { AnalyzeResponse, LyricMatch } from "@workspace/api-client-react";

interface Props {
  media: PickedMedia;
  results: AnalyzeResponse;
  onReset: () => void;
}

function withAlpha(hex: string, alpha: number) {
  const h = hex.replace("#", "");
  const r = parseInt(h.slice(0, 2), 16);
  const g = parseInt(h.slice(2, 4), 16);
  const b = parseInt(h.slice(4, 6), 16);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

function EdgeGlow({ color }: { color: string }) {
  const clear = withAlpha(color, 0);
  const pulse = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    pulse.setValue(0);
    const anim = Animated.sequence([
      Animated.timing(pulse, {
        toValue: 1,
        duration: 170,
        easing: Easing.out(Easing.quad),
        useNativeDriver: true,
      }),
      Animated.delay(250),
      Animated.timing(pulse, {
        toValue: 0,
        duration: 480,
        easing: Easing.in(Easing.quad),
        useNativeDriver: true,
      }),
    ]);
    anim.start();
    return () => anim.stop();
  }, [color, pulse]);

  return (
    <Animated.View
      style={[StyleSheet.absoluteFill, { opacity: pulse }]}
      pointerEvents="none"
    >
      <LinearGradient
        colors={[withAlpha(color, 0.38), clear]}
        start={{ x: 0, y: 0 }}
        end={{ x: 1, y: 0 }}
        style={[styles.glow, { top: 0, bottom: 0, left: 0, width: 14 }]}
      />
      <LinearGradient
        colors={[clear, withAlpha(color, 0.38)]}
        start={{ x: 0, y: 0 }}
        end={{ x: 1, y: 0 }}
        style={[styles.glow, { top: 0, bottom: 0, right: 0, width: 14 }]}
      />
      <LinearGradient
        colors={[withAlpha(color, 0.38), clear]}
        start={{ x: 0, y: 0 }}
        end={{ x: 0, y: 1 }}
        style={[styles.glow, { top: 0, left: 0, right: 0, height: 14 }]}
      />
      <LinearGradient
        colors={[clear, withAlpha(color, 0.38)]}
        start={{ x: 0, y: 0 }}
        end={{ x: 0, y: 1 }}
        style={[styles.glow, { bottom: 0, left: 0, right: 0, height: 14 }]}
      />
    </Animated.View>
  );
}

function LyricBlock({
  match,
  animKey,
  color,
}: {
  match: LyricMatch;
  animKey: string;
  color: string;
}) {
  const lines = useMemo(
    () =>
      match.lyric
        .split("/")
        .map((line) => line.trim())
        .filter(Boolean)
        .map((line) => line.split(/\s+/).filter(Boolean)),
    [match.lyric],
  );

  const lineOffsets = useMemo(() => {
    const offsets: number[] = [];
    let acc = 0;
    for (const line of lines) {
      offsets.push(acc);
      acc += line.length;
    }
    return offsets;
  }, [lines]);

  const totalWords = useMemo(
    () => lines.reduce((n, line) => n + line.length, 0),
    [lines],
  );

  const wordAnims = useMemo(
    () => Array.from({ length: totalWords }, () => new Animated.Value(0)),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [animKey],
  );
  const trackAnim = useMemo(
    () => new Animated.Value(0),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [animKey],
  );

  useEffect(() => {
    const reveals = wordAnims.map((v, i) =>
      Animated.timing(v, {
        toValue: 1,
        duration: 440,
        delay: i * 65,
        easing: Easing.out(Easing.cubic),
        useNativeDriver: true,
      }),
    );
    const anim = Animated.parallel([
      ...reveals,
      Animated.timing(trackAnim, {
        toValue: 1,
        duration: 380,
        delay: totalWords * 65 + 140,
        easing: Easing.out(Easing.cubic),
        useNativeDriver: true,
      }),
    ]);
    anim.start();
    return () => anim.stop();
  }, [wordAnims, trackAnim, totalWords]);

  return (
    <View>
      {lines.map((lineWords, li) => (
        <View key={`${animKey}-line-${li}`} style={styles.lyricWrap}>
          {lineWords.map((w, wi) => {
            const v = wordAnims[lineOffsets[li] + wi];
            return (
              <Animated.Text
                key={`${animKey}-${li}-${wi}`}
                style={[
                  styles.lyric,
                  {
                    color,
                    opacity: v,
                    transform: [
                      {
                        translateY: v.interpolate({
                          inputRange: [0, 1],
                          outputRange: [24, 0],
                        }),
                      },
                      {
                        scale: v.interpolate({
                          inputRange: [0, 1],
                          outputRange: [0.88, 1],
                        }),
                      },
                    ],
                  },
                ]}
              >
                {w}
                {wi < lineWords.length - 1 ? " " : ""}
              </Animated.Text>
            );
          })}
        </View>
      ))}
      <Animated.View style={[styles.trackRow, { opacity: trackAnim }]}>
        <Ionicons
          name="musical-notes"
          size={15}
          color="rgba(255,255,255,0.85)"
        />
        <Text style={styles.trackText} numberOfLines={1}>
          {match.artist} — {match.track}
        </Text>
      </Animated.View>
    </View>
  );
}

export function ReelsPlayer({ media, results, onReset }: Props) {
  const insets = useSafeAreaInsets();
  const topInset = Platform.OS === "web" ? 67 : insets.top;
  const bottomInset = Platform.OS === "web" ? 34 : insets.bottom;

  const [moodIndex, setMoodIndex] = useState(0);
  const [matchIndex, setMatchIndex] = useState(0);

  const moodIndexRef = useRef(0);
  const matchIndexRef = useRef(0);

  const matchesByMood = useMemo(
    () => MOODS.map((mood) => results[mood] ?? []),
    [results],
  );

  const matchesByMoodRef = useRef(matchesByMood);
  matchesByMoodRef.current = matchesByMood;

  const changeMood = useCallback((dir: number) => {
    const next = (moodIndexRef.current + dir + MOODS.length) % MOODS.length;
    moodIndexRef.current = next;
    matchIndexRef.current = 0;
    setMoodIndex(next);
    setMatchIndex(0);
    if (Platform.OS !== "web") {
      Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    }
  }, []);

  const changeMatch = useCallback((dir: number) => {
    const list = matchesByMoodRef.current[moodIndexRef.current];
    if (!list || list.length === 0) return;
    const next = Math.min(
      Math.max(matchIndexRef.current + dir, 0),
      list.length - 1,
    );
    if (next === matchIndexRef.current) return;
    matchIndexRef.current = next;
    setMatchIndex(next);
    if (Platform.OS !== "web") {
      Haptics.selectionAsync();
    }
  }, []);

  const swipeGesture = useMemo(
    () =>
      Gesture.Pan()
        .runOnJS(true)
        .minDistance(14)
        .onEnd((e) => {
          const absX = Math.abs(e.translationX);
          const absY = Math.abs(e.translationY);
          const TH = 45;
          if (absX < TH && absY < TH) return;
          if (absX > absY) {
            changeMood(e.translationX < 0 ? 1 : -1);
          } else {
            changeMatch(e.translationY < 0 ? 1 : -1);
          }
        }),
    [changeMood, changeMatch],
  );

  const currentMood = MOODS[moodIndex];
  const meta = MOOD_META[currentMood];
  const currentList = matchesByMood[moodIndex];
  const currentMatch: LyricMatch | undefined = currentList[matchIndex];

  return (
    <GestureDetector gesture={swipeGesture}>
      <View style={styles.container}>
      <StatusBar style="light" />

      {media.type === "video" ? (
        <VideoBackground uri={media.uri} />
      ) : (
        <Image
          source={{ uri: media.uri }}
          style={StyleSheet.absoluteFill}
          contentFit="cover"
        />
      )}

      <LinearGradient
        colors={[
          "rgba(0,0,0,0.55)",
          "rgba(0,0,0,0.05)",
          "rgba(0,0,0,0.35)",
          "rgba(0,0,0,0.9)",
        ]}
        locations={[0, 0.32, 0.6, 1]}
        style={StyleSheet.absoluteFill}
        pointerEvents="none"
      />

      <EdgeGlow color={meta.color} />

      {/* Top bar */}
      <View style={[styles.topBar, { paddingTop: topInset + 10 }]}>
        <Pressable
          testID="reset"
          onPress={onReset}
          hitSlop={12}
          style={({ pressed }) => [styles.iconButton, pressed && styles.pressed]}
        >
          <Ionicons name="close" size={24} color="#ffffff" />
        </Pressable>

        <View style={[styles.moodBadge, { borderColor: meta.color }]}>
          <Ionicons name={meta.icon} size={16} color={meta.color} />
          <Text style={[styles.moodLabel, { color: meta.color }]}>
            {meta.label}
          </Text>
        </View>

        <View style={styles.iconButton} />
      </View>

      <View style={[styles.dotsRow, { top: topInset + 64 }]}>
        {MOODS.map((mood, i) => (
          <View
            key={mood}
            style={[
              styles.dot,
              {
                backgroundColor:
                  i === moodIndex ? meta.color : "rgba(255,255,255,0.3)",
                width: i === moodIndex ? 22 : 7,
              },
            ]}
          />
        ))}
      </View>

      {/* Bottom content */}
      <View style={[styles.bottom, { paddingBottom: bottomInset + 28 }]}>
        {currentMatch ? (
          <LyricBlock
            match={currentMatch}
            animKey={`${moodIndex}-${matchIndex}`}
            color={meta.color}
          />
        ) : (
          <View style={styles.emptyState}>
            <Ionicons
              name="search"
              size={26}
              color="rgba(255,255,255,0.6)"
            />
            <Text style={styles.emptyText}>
              Nessun testo per questo mood. Scorri per cambiare.
            </Text>
          </View>
        )}

        <View style={styles.footer}>
          <View style={styles.hint}>
            <Ionicons
              name="swap-horizontal"
              size={16}
              color="rgba(255,255,255,0.55)"
            />
            <Text style={styles.hintText}>Mood</Text>
          </View>
          <View style={styles.hint}>
            <Ionicons
              name="swap-vertical"
              size={16}
              color="rgba(255,255,255,0.55)"
            />
            <Text style={styles.hintText}>Testi</Text>
          </View>
        </View>
      </View>
      </View>
    </GestureDetector>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#000000" },
  topBar: {
    position: "absolute",
    top: 0,
    left: 0,
    right: 0,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: 16,
  },
  iconButton: {
    width: 40,
    height: 40,
    borderRadius: 20,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "rgba(0,0,0,0.3)",
  },
  pressed: { opacity: 0.6 },
  moodBadge: {
    flexDirection: "row",
    alignItems: "center",
    gap: 7,
    paddingHorizontal: 16,
    paddingVertical: 8,
    borderRadius: 999,
    borderWidth: 1.5,
    backgroundColor: "rgba(0,0,0,0.45)",
  },
  moodLabel: {
    fontFamily: "Inter_600SemiBold",
    fontSize: 14,
    letterSpacing: 0.3,
  },
  dotsRow: {
    position: "absolute",
    left: 0,
    right: 0,
    flexDirection: "row",
    justifyContent: "center",
    alignItems: "center",
    gap: 6,
  },
  dot: { height: 7, borderRadius: 4 },
  bottom: {
    position: "absolute",
    left: 0,
    right: 0,
    bottom: 0,
    paddingHorizontal: 24,
  },
  glow: { position: "absolute" },
  lyricWrap: {
    flexDirection: "row",
    flexWrap: "wrap",
    alignItems: "flex-end",
  },
  lyric: {
    fontFamily: "Inter_700Bold",
    fontSize: 27,
    lineHeight: 36,
    color: "#ffffff",
    textShadowColor: "rgba(0,0,0,0.85)",
    textShadowOffset: { width: 0, height: 1 },
    textShadowRadius: 12,
  },
  trackRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    marginTop: 14,
  },
  trackText: {
    fontFamily: "Inter_500Medium",
    fontSize: 15,
    color: "rgba(255,255,255,0.85)",
    flexShrink: 1,
  },
  emptyState: { alignItems: "flex-start", gap: 10, paddingVertical: 8 },
  emptyText: {
    fontFamily: "Inter_500Medium",
    fontSize: 16,
    color: "rgba(255,255,255,0.6)",
  },
  footer: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    marginTop: 24,
  },
  hint: { flexDirection: "row", alignItems: "center", gap: 5 },
  hintText: {
    fontFamily: "Inter_500Medium",
    fontSize: 13,
    color: "rgba(255,255,255,0.55)",
  },
});
