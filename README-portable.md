# StillReal Portable (move this folder anywhere, no Python install)

Model: `buildborderless/CommunityForensics-DeepfakeDet-ViT` (Community Forensics, CVPR 2025, MIT)
- 2.7M images, 4803 generators: ProGAN/StyleGAN/BigGAN + SD 1.5/2.1/XL/3.5 + Flux + Midjourney + DALL-E + commercial
- Feb 2026 2.6M-sample benchmark winner: 75.0% mean, best of 16 methods / 23 variants
- Sieve v0.14 fine-tune of same base: 91.3% clean / 87.5% web / 86.2% hard, fixes GPT-Image-2 7% -> >90%

## Run (no install)
```
run.bat photo.jpg
run.bat .\photos\ --threshold 0.65
.\run.ps1 photo.jpg
```

## Gradio UI (no install)
```
ui.bat
.\ui.ps1
```
Opens http://127.0.0.1:7860 - Single image + Batch + Image URL tabs, threshold slider, model-crop preview, CSV export. Fully offline except URL-fetch tab.

Copy the whole folder to USB / another PC and run the same. Only needs Windows x64 + any GPU (DirectML/CUDA) or CPU.
Contents: `python-portable/` (Python 3.12 embed + onnxruntime + DirectML GPU + Pillow/numpy), `model/` (base 87MB FP32 + sieve 42MB + int8 22MB), `detect.py`, `run.bat`.

## Why this one
- Old + new: only model trained on thousands of generators, not one GAN.
- Portable: ONNX CPU/GPU via DirectML/CUDA, no CUDA toolkit install, no admin.
- Honest: outputs P(AI). 0.35-0.65 = borderline. No SynthID pixel decode (Google proprietary) - use Gemini app / SynthID portal + C2PA for that.
