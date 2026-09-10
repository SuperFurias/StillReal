"""Portable best-of-best local AI image detector.
Model: buildborderless/CommunityForensics-DeepfakeDet-ViT (CVPR 2025 Community Forensics)
  - Trained on 2.7M images from 4803 generators (old GANs + new diffusion + commercial)
  - Winner of Feb 2026 zero-shot benchmark: 75.0% mean / 82.1% median over 2.6M samples, 291 generators
  - MIT, fully local, no API, no upload
Engine: ONNX Runtime (CPU) + Pillow + numpy only. No torch, no transformers, no system Python.
Preprocess (must match exactly): shortest edge -> 440 PIL BICUBIC, center-crop 384, CLIP normalize.
Usage (portable, no install):
  run.bat photo.jpg
  run.bat ./photos/
  python-portable\\python.exe detect.py photo.jpg --threshold 0.5
"""
import os
import sys
import argparse
import numpy as np
from PIL import Image

try:
    import onnxruntime as ort
except ImportError:
    print("ERROR: onnxruntime missing in python-portable. Run: python-portable\\python.exe -m pip install onnxruntime")
    sys.exit(2)

BASE = os.path.dirname(os.path.abspath(__file__))
MODEL_BASE = os.path.join(BASE, "model", "model.onnx")
MODEL_SIEVE = os.path.join(BASE, "model", "sieve-v014.onnx")
DEFAULT_MODEL = MODEL_SIEVE

# Base: CLIP norm, no bias. Sieve v0.14 fine-tune: ImageNet norm, logit bias +0.2, thr 0.65.
MEAN_BASE = np.array([0.4815, 0.4578, 0.4082], dtype=np.float32)
STD_BASE = np.array([0.2686, 0.2613, 0.2758], dtype=np.float32)
MEAN_SIEVE = np.array([0.485, 0.456, 0.406], dtype=np.float32)
STD_SIEVE = np.array([0.229, 0.224, 0.225], dtype=np.float32)
BIAS_SIEVE = 0.2

def preprocess(path, use_sieve=True):
    img = Image.open(path).convert("RGB")
    MEAN = MEAN_SIEVE if use_sieve else MEAN_BASE
    STD = STD_SIEVE if use_sieve else STD_BASE
    w, h = img.size
    scale = 440.0 / min(w, h)
    nw, nh = int(round(w * scale)), int(round(h * scale))
    img = img.resize((nw, nh), Image.BICUBIC)
    left = (nw - 384) // 2
    top = (nh - 384) // 2
    img = img.crop((left, top, left + 384, top + 384))
    arr = np.array(img, dtype=np.float32) / 255.0
    arr = (arr - MEAN) / STD
    arr = np.transpose(arr, (2, 0, 1))[None, :, :, :].astype(np.float32)
    return arr

def sigmoid(x):
    return 1.0 / (1.0 + np.exp(-x))

def load_session(model_path):
    opts = ort.SessionOptions()
    opts.intra_op_num_threads = max(1, (os.cpu_count() or 4) - 1)
    return ort.InferenceSession(model_path, sess_options=opts, providers=["CPUExecutionProvider"])

_SESS_CACHE = {}

def get_sess(path):
    if path not in _SESS_CACHE:
        _SESS_CACHE[path] = load_session(path)
    return _SESS_CACHE[path]

def score_one(sess, path, use_sieve):
    x = preprocess(path, use_sieve)
    name = sess.get_inputs()[0].name
    logit = sess.run(None, {name: x})[0].ravel()[0]
    if use_sieve:
        logit = logit + BIAS_SIEVE
    p_ai = float(sigmoid(np.array(logit, dtype=np.float64)))
    return p_ai

def score_file(sess, path):
    # backward compat: single-model score (assumes matching norm by path name)
    use_sieve = "sieve" in os.path.basename(sess.get_inputs()[0].name + str(path)).lower() or "sieve" in str(path).lower() or True
    return score_one(sess, path, True)

def verdict(p, thr):
    if p >= thr:
        return "AI-GENERATED"
    return "REAL"

def main():
    ap = argparse.ArgumentParser(description="Portable Community-Forensics + Sieve AI image detector (local, free, MIT)")
    ap.add_argument("input", help="image file or directory")
    ap.add_argument("--model", default="ensemble", choices=["base", "sieve", "ensemble"],
                    help="base=CommunityForensics 4803 gens (CLIP norm), sieve=v0.14 modern fine-tune (ImageNet norm+bias), ensemble=avg (default, most robust)")
    ap.add_argument("--threshold", type=float, default=0.5)
    ap.add_argument("--extensions", default=".jpg,.jpeg,.png,.webp,.bmp,.tif,.tiff,.heic")
    args = ap.parse_args()

    need_base = args.model in ("base", "ensemble")
    need_sieve = args.model in ("sieve", "ensemble")
    sess_base = get_sess(MODEL_BASE) if need_base and os.path.exists(MODEL_BASE) else None
    sess_sieve = get_sess(MODEL_SIEVE) if need_sieve and os.path.exists(MODEL_SIEVE) else None
    if need_base and sess_base is None:
        print(f"ERROR: missing {MODEL_BASE}"); sys.exit(2)
    if need_sieve and sess_sieve is None:
        print(f"ERROR: missing {MODEL_SIEVE}"); sys.exit(2)

    exts = {e.strip().lower() for e in args.extensions.split(",")}
    files = []
    if os.path.isdir(args.input):
        for root, _, fns in os.walk(args.input):
            for fn in fns:
                if os.path.splitext(fn)[1].lower() in exts:
                    files.append(os.path.join(root, fn))
        files.sort()
    elif os.path.isfile(args.input):
        files = [args.input]
    else:
        print(f"ERROR: not found: {args.input}")
        sys.exit(2)

    if not files:
        print("No images found.")
        sys.exit(1)

    print(f"Model: {args.model} (base={MODEL_BASE if sess_base else 'missing'}, sieve={MODEL_SIEVE if sess_sieve else 'missing'})")
    print(f"Threshold: {args.threshold}  (base 0.5, sieve 0.65 operating point)")
    print(f"Files: {len(files)}\n")

    n_ai = 0
    for f in files:
        try:
            p_b = score_one(sess_base, f, False) if sess_base else None
            p_s = score_one(sess_sieve, f, True) if sess_sieve else None
            if args.model == "base":
                p = p_b
            elif args.model == "sieve":
                p = p_s
            else:
                vals = [v for v in (p_b, p_s) if v is not None]
                p = sum(vals) / len(vals)
            v = verdict(p, args.threshold)
            if v == "AI-GENERATED":
                n_ai += 1
            flag = ""
            if 0.35 <= p <= 0.65:
                flag = "  <-- borderline, treat as weak evidence"
            detail = ""
            if p_b is not None and p_s is not None:
                detail = f"  [base={p_b:.3f} sieve={p_s:.3f}]"
            elif p_b is not None:
                detail = f"  [base={p_b:.3f}]"
            elif p_s is not None:
                detail = f"  [sieve={p_s:.3f}]"
            print(f"{v:13s}  P(AI)={p:.4f}  P(real)={1-p:.4f}  {f}{detail}{flag}")
        except Exception as e:
            print(f"ERROR  {f}: {e}")
    print(f"\nDone: {n_ai}/{len(files)} flagged AI.")
    print("Note: no detector is universal. Flux Dev / Firefly v4 / MJ v7 / Imagen 4 defeat most detectors (18-30% acc). Compare thresholds, check C2PA + SynthID portal for Google/OpenAI images.")

if __name__ == "__main__":
    main()
