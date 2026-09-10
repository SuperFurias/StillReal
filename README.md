# StillReal

StillReal is a fully local, portable AI-image verifier for Windows. No system Python, no upload, no account.
Clone any folder name, run `setup.bat`, then `ui.bat`. Move the folder to USB and it keeps working.

![stack](https://img.shields.io/badge/local-ONNX_CPU/GPU-blue) ![license](https://img.shields.io/badge/glue-MIT-green)

## What it does (plain terms)
Upload an image, press **Verify image**, get **REAL / AI-GENERATED + % confident** in plain words.
Click **> Technical details** for the full signal dump (both models, C2PA, EXIF, watermark probe, frequency scores).
Batch tab handles folders with CSV export. Image URL tab fetches + verifies.

Under the hood: Community Forensics ViT-S ensemble (4803 generators, 2.7M images) + Sieve v0.14
modern fine-tune, TTA 10-crop vote, GPU (DirectML/CUDA) with CPU fallback, plus C2PA/SD-watermark/classical side signals.

## Quickstart (fresh clone)
```
git clone <your-repo-url> MyDetector
cd MyDetector
setup.bat        # or setup.ps1 — builds python-portable/, pip installs requirements-portable.txt, downloads model/*.onnx
ui.bat           # opens http://127.0.0.1:7860
run.bat photo.jpg --model ensemble --threshold 0.5
```
First setup downloads ~800MB (Python embed + torch CPU + onnx + 147MB weights). After that the folder is movable offline.

## Controls that matter
- Model: `ensemble` (most robust avg) / `sieve` (modern + anime) / `base` (old generators).
- Threshold: 0.50 default, 0.65 fewer false positives (Sieve operating point). 0.35-0.65 = borderline, weak evidence.
- TTA 10-crop: +2-4% robust, ~8s CPU / ~1s GPU. Off = instant single-crop.
- Engine: `auto` uses GPU (DirectML/CUDA) if present else CPU. Speed `fast` = 22MB INT8 single (~5-10x faster, slight accuracy drop).

## Honest limits (measured, 2026 studies)
- Anime/stylized + Flux Dev / Firefly v4 / MJ v7 / Imagen 4 defeat most detectors (18-30% acc). Treat mid scores as weak.
- **No local free tool decodes Google SynthID image pixels** (proprietary key + detector). C2PA-signed-Google + high P(AI) means SynthID likely;
  confirm in Gemini app / SynthID Detector portal. OpenAI images: openai.com/verify.
- Classical NPR/texture/HF scores here are experimental heuristics, not calibrated verdicts.

## Repo layout (what to commit)
```
app.py detect.py forensic.py download_models.py
requirements-portable.txt setup.bat setup.ps1 run.bat run.ps1 ui.bat ui.ps1
model/            # gitignored weights (downloaded by setup)
python-portable/  # gitignored runtime (built by setup)
test_images/      # tiny samples, see notices
README.md LICENSE THIRD_PARTY_NOTICES.md .gitignore
```
`model/*.onnx` and `python-portable/` are gitignored (GitHub 100MB/file limit, 1.3GB local). Never force-add them;
reviewers run `setup.bat` to reproduce.

## References & licenses
Glue code: MIT (LICENSE). All power from open upstreams - see THIRD_PARTY_NOTICES.md:
Community-Forensics (MIT) + buildborderless HF weights (MIT), Sieve v0.14 (MIT),
invisible-watermark (MIT), c2pacheck (MIT), NPR/PatchCraft/Synthbuster ideas,
Effort/ForensicHub/GenImage/UnivFD/CNNDetection/OmniAID/SPAI benchmarks,
Gradio/ONNX/Pillow/numpy/opencv (Apache/MIT/BSD/HPND), CPython embed (PSF).
