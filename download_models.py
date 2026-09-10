"""Download model weights from original upstreams. Verifies SHA256. Portable, stdlib only."""
import hashlib
import os
import sys
import urllib.request

BASE = os.path.dirname(os.path.abspath(__file__))
MODEL_DIR = os.path.join(BASE, "model")

FILES = [
    ("https://huggingface.co/buildborderless/CommunityForensics-DeepfakeDet-ViT/resolve/main/onnx/model.onnx",
     "model.onnx",
     "87MB FP32 base (Community Forensics, MIT)",
     None),  # hash varies by export; size check only
    ("https://huggingface.co/buildborderless/CommunityForensics-DeepfakeDet-ViT/resolve/main/onnx/model_int8.onnx",
     "model_int8.onnx",
     "22MB INT8 fast (same source, MIT)",
     None),
    ("https://github.com/Phineas1500/sieve-ai-image-detector/releases/download/v0.14.0/w5810_best_fp16.onnx",
     "sieve-v014.onnx",
     "42MB Sieve v0.14 fine-tune (MIT)",
     "8392faaf0191c339ed76cf68861b1f4fac15da67e8669fa222e3181c59b2d748"),
]

def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(8 << 20), b""):
            h.update(b)
    return h.hexdigest()

def main():
    os.makedirs(MODEL_DIR, exist_ok=True)
    for url, name, desc, want in FILES:
        dest = os.path.join(MODEL_DIR, name)
        if os.path.exists(dest) and os.path.getsize(dest) > 1_000_000:
            print(f"exists {name} ({os.path.getsize(dest) / 1e6:.1f}MB) - {desc}")
        else:
            print(f"downloading {name} - {desc}\n  from {url}")
            urllib.request.urlretrieve(url, dest)
            print(f"  saved {os.path.getsize(dest) / 1e6:.1f}MB")
        if want:
            got = sha256(dest)
            if got != want:
                print(f"  SHA256 MISMATCH for {name}:\n   got  {got}\n   want {want}")
                sys.exit(2)
            print(f"  sha256 ok {got[:16]}...")
    print("All models ready in model/")

if __name__ == "__main__":
    main()
