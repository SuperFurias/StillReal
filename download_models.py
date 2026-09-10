"""Download model weights from original upstreams. Verifies SHA256. Portable, stdlib only."""
import hashlib
import os
import sys
import time
import urllib.request

BASE = os.path.dirname(os.path.abspath(__file__))
MODEL_DIR = os.path.join(BASE, "model")

# (url, name, description, want_sha256_or_None, min_ok_bytes)
FILES = [
    ("https://huggingface.co/buildborderless/CommunityForensics-DeepfakeDet-ViT/resolve/main/onnx/model.onnx",
     "model.onnx",
     "87MB FP32 base (Community Forensics, MIT)",
     None,  # hash varies by export; size check only
     80_000_000),
    ("https://huggingface.co/buildborderless/CommunityForensics-DeepfakeDet-ViT/resolve/main/onnx/model_int8.onnx",
     "model_int8.onnx",
     "22MB INT8 fast (same source, MIT)",
     None,
     20_000_000),
    ("https://github.com/Phineas1500/sieve-ai-image-detector/releases/download/v0.14.0/w5810_best_fp16.onnx",
     "sieve-v014.onnx",
     "42MB Sieve v0.14 fine-tune (MIT)",
     "8392faaf0191c339ed76cf68861b1f4fac15da67e8669fa222e3181c59b2d748",
     40_000_000),
]

RETRIES = 3
TIMEOUT = 120


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(8 << 20), b""):
            h.update(b)
    return h.hexdigest()


def looks_complete(path, min_ok, want):
    if not os.path.exists(path) or os.path.getsize(path) < min_ok:
        return False
    if want and sha256(path) != want:
        return False
    return True


def fetch(url, dest_tmp):
    req = urllib.request.Request(url, headers={"User-Agent": "stillreal-setup/1.0"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r, open(dest_tmp, "wb") as f:
        while True:
            chunk = r.read(4 << 20)
            if not chunk:
                break
            f.write(chunk)


def main():
    os.makedirs(MODEL_DIR, exist_ok=True)
    failures = []
    for url, name, desc, want, min_ok in FILES:
        dest = os.path.join(MODEL_DIR, name)
        if looks_complete(dest, min_ok, want):
            print(f"exists {name} ({os.path.getsize(dest) / 1e6:.1f}MB) - {desc}")
            if want:
                print(f"  sha256 ok {sha256(dest)[:16]}...")
            continue
        if os.path.exists(dest):
            print(f"incomplete {name} ({os.path.getsize(dest) / 1e6:.1f}MB < {min_ok / 1e6:.0f}MB) - re-downloading")
        else:
            print(f"downloading {name} - {desc}\n  from {url}")
        tmp = dest + ".part"
        ok = False
        for attempt in range(1, RETRIES + 1):
            try:
                if os.path.exists(tmp):
                    os.remove(tmp)
                fetch(url, tmp)
                if os.path.getsize(tmp) < min_ok:
                    raise IOError(f"downloaded file too small ({os.path.getsize(tmp)} bytes)")
                os.replace(tmp, dest)  # atomic on same volume
                print(f"  saved {os.path.getsize(dest) / 1e6:.1f}MB")
                ok = True
                break
            except Exception as e:
                print(f"  attempt {attempt}/{RETRIES} failed: {e}")
                try:
                    if os.path.exists(tmp):
                        os.remove(tmp)
                except OSError:
                    pass
                if attempt < RETRIES:
                    time.sleep(2 * attempt)
        if not ok:
            failures.append(name)
            continue
        if want:
            got = sha256(dest)
            if got != want:
                print(f"  SHA256 MISMATCH for {name}:\n   got  {got}\n   want {want}")
                failures.append(name + " (sha256)")
                continue
            print(f"  sha256 ok {got[:16]}...")
    if failures:
        print(f"FAILED downloads: {', '.join(failures)}")
        sys.exit(2)
    print("All models ready in model/")


if __name__ == "__main__":
    main()
