# MiniFASNetV2 Ensemble Model Download

## Required Models (Ensemble Method)

For maximum reliability, download both models:

```bash
mkdir -p models

# MiniFASNetV1SE (tighter crop, scale=4.0)
wget https://github.com/minivision-ai/Silent-Face-Anti-Spoofing/raw/master/resources/anti_spoof_models/MiniFASNetV1SE.onnx -O models/MiniFASNetV1SE.onnx

# MiniFASNetV2 (wider crop, scale=2.7)
wget https://github.com/minivision-ai/Silent-Face-Anti-Spoofing/raw/master/resources/anti_spoof_models/MiniFASNetV2.onnx -O models/MiniFASNetV2.onnx
```

Or download manually from:
https://github.com/minivision-ai/Silent-Face-Anti-Spoofing

## Model Details

| Model | Crop Scale | Input Size | Purpose |
|---|---|---|---|
| MiniFASNetV1SE | 4.0 (tight) | 128x128 | Detects close-up spoofs |
| MiniFASNetV2 | 2.7 (wide) | 128x128 | Detects distant spoofs |

## How Ensemble Works

```
Face Image
    ↓
V1SE (tight crop) → Live/Spoof probability
    ↓
V2 (wide crop) → Live/Spoof probability
    ↓
Average probabilities
    ↓
Final decision
```

## Why Ensemble?

| Attack Type | V1SE | V2 | Ensemble |
|---|---|---|---|
| Printed photo (close) | ✅ Catches | ❌ May miss | ✅ Catches |
| Printed photo (far) | ❌ May miss | ✅ Catches | ✅ Catches |
| Screen replay | ✅ Catches | ✅ Catches | ✅ Catches |
| 3D mask | ⚠️ Partial | ⚠️ Partial | ✅ Better |

## Minimum Setup

At minimum, download `MiniFASNetV2.onnx` for basic protection.

## Recommended Setup

Download both for ensemble protection against all standard spoof patterns.
