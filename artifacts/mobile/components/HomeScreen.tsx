import { Ionicons } from "@expo/vector-icons";
import { LinearGradient } from "expo-linear-gradient";
import { StatusBar } from "expo-status-bar";
import React from "react";
import {
  Platform,
  Pressable,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

interface Props {
  onUseCamera: () => void;
  onUseLibrary: () => void;
}

export function HomeScreen({ onUseCamera, onUseLibrary }: Props) {
  const insets = useSafeAreaInsets();
  const topInset = Platform.OS === "web" ? 67 : insets.top;
  const bottomInset = Platform.OS === "web" ? 34 : insets.bottom;

  return (
    <View style={styles.container}>
      <StatusBar style="light" />
      <LinearGradient
        colors={["#1a0b2e", "#2d0a3d", "#000000"]}
        start={{ x: 0, y: 0 }}
        end={{ x: 1, y: 1 }}
        style={StyleSheet.absoluteFill}
      />

      <View style={[styles.content, { paddingTop: topInset + 24 }]}>
        <View style={styles.hero}>
          <View style={styles.logoBadge}>
            <Ionicons name="eye" size={34} color="#ffffff" />
          </View>
          <Text style={styles.title}>Visual Lyrics</Text>
          <Text style={styles.subtitle}>
            Inquadra un momento. Trova le parole che lo cantano.
          </Text>
        </View>

        <View style={[styles.actions, { paddingBottom: bottomInset + 28 }]}>
          <Pressable
            testID="use-camera"
            onPress={onUseCamera}
            style={({ pressed }) => [
              styles.primaryButton,
              pressed && styles.pressed,
            ]}
          >
            <Ionicons name="camera" size={22} color="#000000" />
            <Text style={styles.primaryButtonText}>Scatta o registra</Text>
          </Pressable>

          <Pressable
            testID="use-library"
            onPress={onUseLibrary}
            style={({ pressed }) => [
              styles.secondaryButton,
              pressed && styles.pressed,
            ]}
          >
            <Ionicons name="images" size={22} color="#ffffff" />
            <Text style={styles.secondaryButtonText}>Dalla galleria</Text>
          </Pressable>
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#000000" },
  content: {
    flex: 1,
    justifyContent: "space-between",
    paddingHorizontal: 28,
  },
  hero: { flex: 1, justifyContent: "center", alignItems: "flex-start" },
  logoBadge: {
    width: 72,
    height: 72,
    borderRadius: 24,
    backgroundColor: "rgba(168,85,247,0.25)",
    borderWidth: 1,
    borderColor: "rgba(168,85,247,0.5)",
    alignItems: "center",
    justifyContent: "center",
    marginBottom: 24,
  },
  title: {
    fontFamily: "Inter_700Bold",
    fontSize: 44,
    color: "#ffffff",
    letterSpacing: -1,
  },
  subtitle: {
    fontFamily: "Inter_400Regular",
    fontSize: 17,
    lineHeight: 24,
    color: "rgba(255,255,255,0.65)",
    marginTop: 12,
    maxWidth: 320,
  },
  actions: { gap: 14 },
  primaryButton: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 10,
    backgroundColor: "#ffffff",
    paddingVertical: 18,
    borderRadius: 18,
  },
  primaryButtonText: {
    fontFamily: "Inter_600SemiBold",
    fontSize: 17,
    color: "#000000",
  },
  secondaryButton: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 10,
    backgroundColor: "rgba(255,255,255,0.1)",
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.18)",
    paddingVertical: 18,
    borderRadius: 18,
  },
  secondaryButtonText: {
    fontFamily: "Inter_600SemiBold",
    fontSize: 17,
    color: "#ffffff",
  },
  pressed: { opacity: 0.7 },
});
