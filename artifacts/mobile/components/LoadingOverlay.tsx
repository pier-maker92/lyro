import { Image } from "expo-image";
import { LinearGradient } from "expo-linear-gradient";
import { StatusBar } from "expo-status-bar";
import React from "react";
import { ActivityIndicator, StyleSheet, Text, View } from "react-native";

import type { PickedMedia } from "@/lib/media";

interface Props {
  media: PickedMedia | null;
}

export function LoadingOverlay({ media }: Props) {
  return (
    <View style={styles.container}>
      <StatusBar style="light" />
      {media?.type === "image" ? (
        <Image
          source={{ uri: media.uri }}
          style={StyleSheet.absoluteFill}
          contentFit="cover"
          blurRadius={30}
        />
      ) : null}
      <LinearGradient
        colors={["rgba(0,0,0,0.6)", "rgba(0,0,0,0.85)"]}
        style={StyleSheet.absoluteFill}
      />
      <View style={styles.center}>
        <ActivityIndicator size="large" color="#ffffff" />
        <Text style={styles.text}>
          Analizzando la scena e cercando i testi perfetti...
        </Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#000000" },
  center: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: 40,
    gap: 20,
  },
  text: {
    fontFamily: "Inter_500Medium",
    fontSize: 16,
    lineHeight: 23,
    color: "rgba(255,255,255,0.9)",
    textAlign: "center",
  },
});
