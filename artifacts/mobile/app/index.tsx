import { useAnalyzeVisual } from "@workspace/api-client-react";
import React, { useState } from "react";
import { Alert } from "react-native";

import { HomeScreen } from "@/components/HomeScreen";
import { LoadingOverlay } from "@/components/LoadingOverlay";
import { ReelsPlayer } from "@/components/ReelsPlayer";
import {
  captureFromCamera,
  CameraPermissionError,
  pickFromLibrary,
  VideoThumbnailError,
  type PickedMedia,
} from "@/lib/media";
import type { AnalyzeResponse } from "@workspace/api-client-react";

export default function Index() {
  const [media, setMedia] = useState<PickedMedia | null>(null);
  const [results, setResults] = useState<AnalyzeResponse | null>(null);
  const analyze = useAnalyzeVisual();

  const handlePick = async (
    picker: () => Promise<PickedMedia | null>,
  ): Promise<void> => {
    if (analyze.isPending) return;
    try {
      const picked = await picker();
      if (!picked) return;
      setMedia(picked);
      setResults(null);
      analyze.mutate(
        { data: { imageDataUrl: picked.dataUrl } },
        {
          onSuccess: (data) => setResults(data),
          onError: () => {
            setMedia(null);
            Alert.alert(
              "Errore",
              "Non sono riuscito ad analizzare il media. Riprova.",
            );
          },
        },
      );
    } catch (e) {
      if (e instanceof CameraPermissionError) {
        Alert.alert(
          "Permesso fotocamera",
          "Abilita la fotocamera nelle impostazioni per scattare una foto.",
        );
      } else if (e instanceof VideoThumbnailError) {
        Alert.alert(
          "Video non supportato",
          "Non riesco a leggere questo video su questo dispositivo. Prova con una foto.",
        );
      } else {
        Alert.alert("Errore", "Qualcosa è andato storto. Riprova.");
      }
    }
  };

  const reset = (): void => {
    setMedia(null);
    setResults(null);
    analyze.reset();
  };

  if (media && results) {
    return <ReelsPlayer media={media} results={results} onReset={reset} />;
  }

  if (media && !results) {
    return <LoadingOverlay media={media} />;
  }

  return (
    <HomeScreen
      onUseCamera={() => handlePick(captureFromCamera)}
      onUseLibrary={() => handlePick(pickFromLibrary)}
    />
  );
}
