// Camera + on-device face detection shared by the kiosk and enrolment pages.
//
// Detection runs in the browser (MediaPipe BlazeFace, served locally - no
// internet needed), so the device decides *when* a usable face is in view and
// only then sends one compressed image to the backend. If MediaPipe cannot
// load (very old browser), we fall back to asking the server every 300 ms.

const MP = "/static/vendor/mediapipe";

export async function startCamera(video) {
  const stream = await navigator.mediaDevices.getUserMedia({
    audio: false,
    video: { facingMode: "user", width: { ideal: 1280 }, height: { ideal: 720 } },
  });
  video.srcObject = stream;
  video.setAttribute("playsinline", "");
  video.muted = true;
  await video.play();
  return stream;
}

export async function createDetector() {
  try {
    const { FilesetResolver, FaceDetector } = await import(`${MP}/vision_bundle.mjs`);
    const fileset = await FilesetResolver.forVisionTasks(`${MP}/wasm`);
    const make = (delegate) =>
      FaceDetector.createFromOptions(fileset, {
        baseOptions: { modelAssetPath: `${MP}/blaze_face_short_range.tflite`, delegate },
        runningMode: "VIDEO",
        minDetectionConfidence: 0.6,
      });
    let det;
    try { det = await make("GPU"); } catch { det = await make("CPU"); }
    return {
      kind: "on-device",
      detect(video) {
        const r = det.detectForVideo(video, performance.now());
        return r.detections.map((d) => ({ ...d.boundingBox, score: d.categories?.[0]?.score ?? 0 }));
      },
    };
  } catch (err) {
    console.warn("MediaPipe unavailable, using server-side detection", err);
    return serverDetector();
  }
}

function serverDetector() {
  let last = [];
  let busy = false;
  let lastT = 0;
  return {
    kind: "server",
    detect(video) {
      const now = performance.now();
      if (!busy && now - lastT > 300) {
        busy = true;
        lastT = now;
        const img = capture(video, 320, 0.6);
        fetch("/api/detect", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ image: img }) })
          .then((r) => r.json())
          .then((faces) => {
            const W = video.videoWidth, H = video.videoHeight;
            last = faces.map((f) => ({ originX: f.Left * W, originY: f.Top * H, width: f.Width * W, height: f.Height * H, score: f.Confidence / 100 }));
          })
          .catch(() => {})
          .finally(() => { busy = false; });
      }
      return last;
    },
  };
}

// Grab the current frame as a base64 JPEG, longest side <= maxSide.
export function capture(video, maxSide = 640, quality = 0.88) {
  const w = video.videoWidth, h = video.videoHeight;
  const s = Math.min(1, maxSide / Math.max(w, h));
  const c = document.createElement("canvas");
  c.width = Math.round(w * s);
  c.height = Math.round(h * s);
  c.getContext("2d").drawImage(video, 0, 0, c.width, c.height);
  return c.toDataURL("image/jpeg", quality);
}

// Is the face big, centred and steady enough to capture?
export class Framing {
  constructor({ minWidth = 0.22, stableMs = 450 } = {}) {
    this.minWidth = minWidth;
    this.stableMs = stableMs;
    this.prev = null;
    this.since = 0;
  }
  assess(faces, video) {
    const W = video.videoWidth, H = video.videoHeight;
    if (!W) return { ok: false, msg: "Starting camera..." };
    if (faces.length === 0) { this.prev = null; return { ok: false, msg: "Look at the camera", none: true }; }
    if (faces.length > 1) { this.prev = null; return { ok: false, msg: "One person at a time, please" }; }
    const f = faces[0];
    const cx = (f.originX + f.width / 2) / W, cy = (f.originY + f.height / 2) / H;
    const rel = f.width / Math.min(W, H);
    if (rel < this.minWidth) { this.prev = null; return { ok: false, msg: "Move closer" }; }
    if (rel > 0.85) { this.prev = null; return { ok: false, msg: "Move back a little" }; }
    if (Math.abs(cx - 0.5) > 0.2 || Math.abs(cy - 0.5) > 0.25) { this.prev = null; return { ok: false, msg: "Centre your face in the oval" }; }
    const now = performance.now();
    if (this.prev) {
      const move = Math.hypot(cx - this.prev.cx, cy - this.prev.cy) + Math.abs(rel - this.prev.rel);
      if (move > 0.05) this.since = now;
    } else {
      this.since = now;
    }
    this.prev = { cx, cy, rel };
    if (now - this.since < this.stableMs) return { ok: false, msg: "Hold still...", steady: true };
    return { ok: true, msg: "Capturing" };
  }
  reset() { this.prev = null; }
}

export const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// Variance of the Laplacian over the face region: higher = sharper.
export function faceSharpness(video, box) {
  const s = 96;
  const c = document.createElement("canvas");
  c.width = s;
  c.height = s;
  const g = c.getContext("2d", { willReadFrequently: true });
  g.drawImage(video, box.originX, box.originY, box.width, box.height, 0, 0, s, s);
  const px = g.getImageData(0, 0, s, s).data;
  const lum = new Float32Array(s * s);
  for (let i = 0; i < s * s; i++) lum[i] = 0.299 * px[4 * i] + 0.587 * px[4 * i + 1] + 0.114 * px[4 * i + 2];
  let sum = 0, sq = 0, n = 0;
  for (let y = 1; y < s - 1; y++) {
    for (let x = 1; x < s - 1; x++) {
      const i = y * s + x;
      const l = 4 * lum[i] - lum[i - 1] - lum[i + 1] - lum[i - s] - lum[i + s];
      sum += l; sq += l * l; n++;
    }
  }
  const mean = sum / n;
  return sq / n - mean * mean;
}

// Mean brightness (0-255) of the inner face and of the rest of the frame.
export function faceLighting(video, box) {
  const W = 96, H = Math.max(1, Math.round(96 * video.videoHeight / video.videoWidth));
  const c = document.createElement("canvas");
  c.width = W;
  c.height = H;
  const g = c.getContext("2d", { willReadFrequently: true });
  g.drawImage(video, 0, 0, W, H);
  const px = g.getImageData(0, 0, W, H).data;
  const sx = W / video.videoWidth, sy = H / video.videoHeight;
  const bx0 = box.originX * sx, by0 = box.originY * sy, bx1 = (box.originX + box.width) * sx, by1 = (box.originY + box.height) * sy;
  const fx0 = bx0 + (bx1 - bx0) / 4, fx1 = bx1 - (bx1 - bx0) / 4, fy0 = by0 + (by1 - by0) / 4, fy1 = by1 - (by1 - by0) / 4;
  let fs = 0, fn = 0, bs = 0, bn = 0;
  for (let y = 0; y < H; y++) {
    for (let x = 0; x < W; x++) {
      const i = 4 * (y * W + x);
      const l = 0.299 * px[i] + 0.587 * px[i + 1] + 0.114 * px[i + 2];
      if (x >= fx0 && x < fx1 && y >= fy0 && y < fy1) { fs += l; fn++; }
      else if (x < bx0 || x >= bx1 || y < by0 || y >= by1) { bs += l; bn++; }
    }
  }
  return { face: fn ? fs / fn : 0, background: bn ? bs / bn : 0 };
}

// Gentle pre-check: only clear problems. (Genuine users have passed with a
// face brightness as low as ~25, so darkness alone is not a reason to block.)
export function lightingProblem(l) {
  if (l.face < 35 || l.background < 25) return "Too dark - turn on a light or face a window";
  if (l.background - l.face > 70 && l.background > 130) return "Bright light behind you - turn to face the light";
  return null;
}

// Take a short burst and keep the sharpest single-face frame. Motion blur is
// a common reason for a genuine selfie to look "flat" to anti-spoofing.
export async function bestOfBurst(video, detector, { frames = 3, gapMs = 90, maxSide = 640, quality = 0.88 } = {}) {
  let best = null;
  for (let i = 0; i < frames; i++) {
    if (i) await sleep(gapMs);
    const faces = detector.detect(video);
    if (faces.length !== 1) continue;
    const score = faceSharpness(video, faces[0]);
    if (!best || score > best.score) best = { score, image: capture(video, maxSide, quality) };
  }
  return best ? best.image : capture(video, maxSide, quality);
}
