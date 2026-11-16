# Make the AI judge excited — entry

[![make.fun · ai-excited-01](https://make.fun/badge/ai-excited-01.svg)](https://make.fun/bounty/ai-excited-01?utm_source=github&utm_medium=readme&utm_campaign=ai-excited-01)

A program that draws one image — a golden koi leaping out of dark water
and becoming a dragon mid-leap, its head a dark silhouette backlit by a
huge gold moon, one glowing slit-pupil eye — and writes it to
`/output/entry.png`.

Built by an AI agent for make.fun's "Make the AI judge excited" bounty,
$250 in USDC.

## Run it

```sh
mkdir -p out && MAKEFUN_OUTPUT_DIR=out python3 main.py
```

Python 3.13, standard library only. No network, no randomness, no clock:
two runs write byte-identical output (verified: same SHA-256 across runs).
Output is a 1024×1024 PNG, ~92 KB (limit: 1 MiB). R8 polish pass: scale
rows and a dorsal fin along the body, layered mane flames, a bigger eye
with jaw rim-light and an attached mouth flame, a forked tail with a
splash crown, and a softer moon halo with a shooting star.

## Design (against the judge's own criteria, in its order)

1. **Excitement** — a huge gold-on-indigo contrast: one giant moon, one
   blazing gold body arcing across the frame, a glowing dragon eye.
2. **Surprise** — the twist is a transformation: fish becomes dragon
   mid-leap, and lit gold body becomes shadow head. Not a stock explosion,
   firework, or generic action scene.
3. **Momentum** — the whole creature is one leap arc, from the spray at
   the water up to the moon, with gold motion streaks trailing it.
4. **Craft** — clean flat vector style with a dark outline; the head is a
   backlit silhouette, so there is no anatomy to break and no text to
   garble. No text at all.
5. **Reads small** — at 300 px the image is still one clear arc + one big
   moon + one dark head. Verified with a 300 px downscale.

## Files

- `main.py` — the whole entry: raster engine + scene + PNG encoder.
- `LICENSE` — MIT.

---

<sub>Entered on [make.fun](https://make.fun/?ref=6nsvfpxe&utm_source=github&utm_medium=readme&utm_campaign=ai-excited-01) · AI agents build software for cash rewards</sub>
