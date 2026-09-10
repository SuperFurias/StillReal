# StillReal

StillReal is a fully local AI-image verifier for Windows. No system Python to install, no uploads, no account.

Upload a photo, press **Verify image**, and get a plain **REAL / AI-GENERATED** verdict with a confidence score. Everything runs on your own PC.

![stack](https://img.shields.io/badge/local-ONNX_CPU/GPU-blue) ![license](https://img.shields.io/badge/glue-MIT-green)

## Features

- **Single-image check** — verdict in plain words plus a confidence bar.
- **Technical details** — both model scores, C2PA provenance, EXIF data, invisible-watermark probe, and frequency analysis, hidden under one expandable section.
- **Batch mode** — verify many images at once with CSV export for records.
- **Image URL mode** — fetch an image from a link and verify it.
- **Command line** — scriptable single-file and folder scanning.
- **GPU when available** — uses DirectML/CUDA automatically, falls back to CPU.
- **Portable** — after setup, copy the whole folder to a USB stick and it keeps working on another PC.

Under the hood: Community Forensics ViT-S ensemble (4803 generators, 2.7M images) + Sieve v0.14
modern fine-tune, TTA 10-crop vote, plus C2PA/SD-watermark/classical side signals.

## Requirements

- Windows 10/11, 64-bit.
- About **2 GB free disk** (setup downloads the Python runtime, ML libraries, and ~150 MB of model weights; the finished folder is ~1.4 GB).
- Internet connection **for setup only**. After that, everything works offline (except the Image URL tab, which obviously needs the network to fetch the link).
- A GPU is optional. Any DirectX 12 / CUDA GPU speeds things up; otherwise the CPU is used.
- Git is optional. Setup uses it for one small extra package and simply skips that step with a warning if git is missing.

## Quickstart

Clone the repository (you can name the folder anything):

```
git clone https://github.com/SuperFurias/StillReal.git MyDetector
```

Enter the folder:

```
cd MyDetector
```

Run setup (downloads the portable Python runtime, installs libraries, downloads model weights):

```
setup.bat
```

Or with PowerShell (if double-clicking a `.ps1` is blocked, run `powershell -ExecutionPolicy Bypass -File setup.ps1`):

```
setup.ps1
```

Setup is safe to re-run: it repairs an interrupted install instead of starting over.

Launch the web UI (opens `http://127.0.0.1:7860` in your browser):

```
ui.bat
```

Or skip the UI and check one image from the command line:

```
run.bat photo.jpg --model ensemble --threshold 0.5
```

## Using the app

### Upload tab

1. Drop in a PNG, JPG, WEBP, BMP, or TIF (or paste from clipboard).
2. Pick a model and threshold (see below), press **Verify image**.
3. Read the verdict sentence. Expand **> Technical details** for the full signal dump, including the model crop, noise-residual, and spectrum views.

### Batch tab

Upload multiple images, press **Verify batch**, and download the results as CSV. The summary line tells you how many were flagged at your threshold.

### Image URL tab

Paste an `https://...` image link and press **Fetch + Verify**. Note: this downloads the file from the internet, so it is the one feature that is not fully offline.

### Command line

Check a single image:

```
run.bat photo.jpg
```

Check a whole folder:

```
run.bat .\photos\ --threshold 0.65
```

Use the modern fine-tuned model only:

```
run.bat photo.jpg --model sieve
```

PowerShell equivalents (`run.ps1`, `ui.ps1`) work the same way:

```
.\run.ps1 photo.jpg
```

```
.\ui.ps1
```

Try it first with the bundled samples:

```
run.bat test_images
```

## Understanding results

- **P(AI)** is the estimated probability the image was AI-generated. Above your threshold reads **AI-GENERATED**, below reads **REAL**.
- **Threshold** default is `0.50`. Use `0.65` for fewer false alarms (the Sieve operating point).
- Scores between **0.35–0.65 are borderline**: weak evidence. Try the other models and check the image source before concluding anything.
- **Model**: `ensemble` (average of both, most robust) / `sieve` (modern generators, anime) / `base` (older generators).
- **TTA 10-crop**: slower (~8s CPU / ~1s GPU) but 2–4% more robust. Turn off for an instant single-crop verdict.
- **Engine**: `auto` uses your GPU if one is available, else CPU.
- **Speed**: `quality` (full ensemble) / `fast` (22 MB INT8 model, ~5–10x faster, slight accuracy drop).

## Privacy

Your images never leave your machine. There is no upload, no account, no telemetry. The only network access is the Image URL tab fetching the link you paste.

## Troubleshooting

- **Setup failed?** Read the red error line, check your internet connection, and just run `setup.bat` again — it resumes and repairs.
- **Start completely over?** Delete the `python-portable\` folder and run `setup.bat` again.
- **"Optional requirements failed" warning?** You don't have git installed. Everything else works; only the extra C2PA library check is skipped.
- **`setup.ps1` won't run?** Windows script policy may block it. Run `powershell -ExecutionPolicy Bypass -File setup.ps1`.
- **Port 7860 already in use?** Close the other program using it, then run `ui.bat` again.
- **Windows SmartScreen warning?** These are plain local scripts. Choose "More info" → "Run anyway" if you trust the source you cloned from.
- **Models keep re-downloading?** A file below its expected size is treated as incomplete and fetched again — let that run finish once.

## Project structure

After setup, the folder contains:

- `app.py` — the Gradio web UI (`ui.bat` / `ui.ps1`).
- `detect.py` — the command-line detector (`run.bat` / `run.ps1`).
- `forensic.py` — provenance side signals (C2PA scan, EXIF, watermark probe, frequency scores).
- `download_models.py` — fetches model weights into `model/`.
- `setup.bat` / `setup.ps1` — one-time setup; builds `python-portable/` and downloads weights.
- `requirements-portable.txt` — core libraries; `requirements-optional.txt` — best-effort extras.
- `model/` — downloaded weights (not in git, recreated by setup).
- `python-portable/` — downloaded Python runtime + libraries (not in git, recreated by setup).
- `test_images/` — small sample images to try (see `test_images/SOURCES.md`).

## Honest limits (measured, 2026 studies)

- Anime/stylized + Flux Dev / Firefly v4 / MJ v7 / Imagen 4 defeat most detectors (18-30% acc). Treat mid scores as weak.
- **No local free tool decodes Google SynthID image pixels** (proprietary key + detector). C2PA-signed-Google + high P(AI) means SynthID likely;
  confirm in Gemini app / SynthID Detector portal. OpenAI images: openai.com/verify.
- Classical NPR/texture/HF scores here are experimental heuristics, not calibrated verdicts.

## References & licenses

Glue code: MIT (LICENSE). All power from open upstreams - see THIRD_PARTY_NOTICES.md:
Community-Forensics (MIT) + buildborderless HF weights (MIT), Sieve v0.14 (MIT),
invisible-watermark (MIT), c2pacheck (MIT), NPR/PatchCraft/Synthbuster ideas,
Effort/ForensicHub/GenImage/UnivFD/CNNDetection/OmniAID/SPAI benchmarks,
Gradio/ONNX/Pillow/numpy/opencv (Apache/MIT/BSD/HPND), CPython embed (PSF).
