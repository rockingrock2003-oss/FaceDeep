# Liveness and recognition pilot: test plan

Goal: measure how often spoof attacks get through and how often genuine users
are wrongly rejected, using 3–5 participants and ordinary office equipment.

## Setup

1. Start the demo: `python scripts/run_demo.py --debug-probes`
   (`--debug-probes` keeps every captured frame so failures can be inspected;
   delete `data/demo/debug-probes/` afterwards, it contains face images).
2. Open the kiosk in **pilot mode** on the real device: `https://<laptop-ip>:8443/?pilot=1`
3. Enrol every participant at `/enroll` with **3 photos**, normal office light.
   Use their employee ID (e.g. `EMP-1001`) — type the same ID in the kiosk's
   *Participant* box during the test.
4. Before **each** attempt, set the *label* dropdown (what the attempt is) and
   the *Participant* box (whose face is being presented or targeted).

## What to collect

Run everything in **Secure** mode (the default). If time allows, repeat the
attacks in **Fast** mode to show why Secure is the default.

| Label | How to make it | Attempts per participant |
|---|---|---|
| `genuine` | The participant checks in normally. Vary it: bright light, dim light, back to a window, glasses on/off, cap/hijab, close and far | 15 |
| `stranger` | Someone **not** enrolled tries to check in (type their name as participant) | 10 in total |
| `print-flat` | Colour print of the participant's face, A4, held flat in front of the camera | 5 |
| `print-curved` | Same print, bent around a hand or bottle so it looks 3D | 5 |
| `print-eyes-cut` | Print with the eyes cut out; the attacker looks through the holes and blinks | 5 |
| `paper-mask` | Life-size print cut to the face outline, worn over the attacker's face | 5 |
| `phone-photo` | Participant's photo on a phone at full brightness | 5 |
| `tablet-photo` | Photo on a tablet or laptop screen (closer to life size) | 5 |
| `video-replay` | Pre-recorded selfie video of the participant (blinking, moving) played on a phone or tablet | 5 |
| `social-photo` | A photo taken from WhatsApp / LinkedIn / Facebook, shown on a screen | 5 |

With 4 participants that is about 60 genuine, 10 stranger and 160 attack
attempts — roughly half a day.

**Attack properly.** The point is to find weaknesses: hold the print or screen
steady, fill the oval, hide the screen edges, avoid glare, match the room
lighting, try different distances. A test that only uses easy attacks proves
little.

**Source photos.** Take attack photos with a phone in good light (best case for
the attacker), plus at least one lower-quality social-media photo.

## Score it

```
python -m eval.pilot_report --since "2026-10-20 09:00"
```

The report gives, per attack type and mode, how many attacks were accepted
(APCER) and how many genuine users were rejected as spoofs (BPCER), each with a
95% upper bound. Writes `reports/pilot_report.md`.

How to read the bound: zero accepted attacks out of 20 only shows the true
rate is probably **below 14%**; out of 100 it is below 3%. More attempts per
attack type give a stronger claim.

## Suggested pass marks (agree before testing)

| Measure | Target |
|---|---|
| Attacks accepted, any type (Secure mode) | 0 observed; under 5% at the 95% bound overall |
| Genuine users rejected as spoofs | under 3% |
| Wrong person checked in | 0 |
| Strangers let in | 0 |

## Not covered by this plan

3D silicone or resin masks, deepfake video, and injected camera streams
(virtual camera software). These need specialist equipment or skills; they are
the reason certified liveness exists.
