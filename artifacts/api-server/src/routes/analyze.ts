import { Router, type IRouter } from "express";

const router: IRouter = Router();

const ENGINE_URL = process.env.LYRICS_ENGINE_URL ?? "http://127.0.0.1:8000";

router.post("/analyze", async (req, res) => {
  const imageDataUrl = req.body?.imageDataUrl;
  if (typeof imageDataUrl !== "string" || !imageDataUrl.startsWith("data:")) {
    res.status(400).json({ error: "imageDataUrl must be a data URL" });
    return;
  }

  try {
    const upstream = await fetch(`${ENGINE_URL}/analyze`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ imageDataUrl }),
    });

    const text = await upstream.text();
    res
      .status(upstream.status)
      .type(upstream.headers.get("content-type") ?? "application/json")
      .send(text);
  } catch (err) {
    req.log.error({ err }, "lyrics engine request failed");
    res.status(502).json({ error: "Lyrics engine is unavailable" });
  }
});

export default router;
