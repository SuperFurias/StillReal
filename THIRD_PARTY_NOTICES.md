# Third-party notices - all detection power comes from these open projects

Our glue code is MIT (LICENSE). Everything below keeps its upstream license.
Model weights and datasets are NOT committed here; `download_models.py` / `setup.bat`
fetch them from the original sources.

## Detection models (weights, downloaded at setup)
- Community Forensics ViT-S - paper CVPR 2025, repo `JeongsooP/Community-Forensics` (MIT),
  HF `buildborderless/CommunityForensics-DeepfakeDet-ViT` (MIT) - `model.onnx` 87MB FP32 + `model_int8.onnx` 22MB.
  Trained on 2.7M images / 4803 generators. Winner Feb 2026 2.6M-sample zero-shot benchmark (75.0% mean).
- Sieve v0.14 fine-tune - repo `Phineas1500/sieve-ai-image-detector` (MIT),
  release `v0.14.0/w5810_best_fp16.onnx` 42MB, SHA256 `8392faaf0191c339ed76cf68861b1f4fac15da67e8669fa222e3181c59b2d748`.
  Same ViT-S fine-tuned for GPT-Image-2 / MJ v7 / Nano Banana Pro / Flux.2 + web JPEG. 91.3% clean / 87.5% web.

## Watermark / provenance libs (pip, portable)
- `ShieldMnt/invisible-watermark` 0.2.0 (MIT) - SD-style dwtDct probe.
- `danraveh-ai/c2pacheck` (MIT, git) - C2PA Content Credentials inspect.
- Meta Watermark Anything (WAM), Stable Signature, VideoSeal/PixelSeal, AudioSeal - research refs, not bundled (torch/CUDA, non-portable).
- Adobe TrustMark (MIT) - research ref, not bundled.
- Google SynthID - proprietary image detector (no local decode). Text part `google-deepmind/synthid-text` (Apache-2.0) is key-only. Verify images in Gemini app / SynthID portal, OpenAI images at openai.com/verify.

## Classical ideas re-implemented numpy-only in forensic.py (no weights)
- NPR `chuangchuangtan/NPR-DeepfakeDetection` (CVPR 2024) - upsampling-residual energy.
- PatchCraft `PatchCraft` (texture rich/poor contrast) - patch-variance gap.
- Synthbuster / frequency spectral 1/f - FFT high-frequency ratio.
- StegaStamp `tancik/StegaStamp` (MIT), HiDDeN (MIT) - stego background refs.

## Benchmarks / codebases consulted (research only)
- `YZY-stack/Effort-AIGI-Detection` (ICML 2025 Oral, CC BY-NC 4.0 - non-commercial, NOT bundled).
- `scu-zjz/ForensicHub` (NeurIPS 2025), `DeepfakeBench`, `GenImage-Dataset/GenImage`,
  `WisconsinAIVision/UniversalFakeDetect`, `PeterWang512/CNNDetection`, `Yunncheng/OmniAID`,
  `mever-team/spai`, `lynote-ai/ai-image-detector`, OpenFake/SlopGuard/OpenSynthID surrogates (unvalidated, not bundled).

## Runtime (vendored by setup, not committed)
- CPython 3.12.10 embeddable - Python Software Foundation license.
- Gradio 5.44.1 (Apache-2.0), ONNX Runtime 1.29.0 + DirectML 1.24.4 (MIT),
  Pillow 11.3.0 (HPND), numpy 2.5.3 (BSD), opencv-headless 5.0.0 (Apache-2.0),
  PyWavelets 1.10.0 (MIT), pandas 2.3.3 (BSD), requests 2.34.2 (Apache-2.0),
  torch CPU 2.14.0 (BSD, pulled by invisible-watermark import).

## Test images (public domain, safe to commit - see test_images/SOURCES.md)
- `ai_anime_cc0.jpg` - Artbreeder 2018 anime portrait, CC0 1.0 + PD-algorithm via Wikimedia Commons.
- `ai_woman_sd15_pd.png` - Stable Diffusion v1.5 fictitious shopper, public domain (PD-algorithm, USCO no human authorship).
- `real_earth_pd.jpg` - NASA Suomi NPP VIIRS Blue Marble PIA18033 small, US public domain (PD-USGov).
