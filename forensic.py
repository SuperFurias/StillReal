"""Portable forensic side-signals: C2PA provenance, SD invisible-watermark, classical frequency helpers.
No torch needed for scan except invisible-watermark dwtDct (CPU). All best-effort, never overriding ViT verdict.
Sources: danraveh-ai/c2pacheck (MIT), ShieldMnt/invisible-watermark (MIT),
  chuangchuangtan/NPR (CVPR24 upsampling artifacts), PatchCraft (texture-contrast), Synthbuster (spectral).
"""
import os
import re

C2PA_MARKERS = [b"jumb", b"c2pa", b"c2pa_manifest", b"ContentCredentials", b"c2pa_claim",
                b"stds.schema-org.CreativeWork", b"c2pa.actions"]
VENDOR_HINTS = {
    "OpenAI": [b"OpenAI", b"ChatGPT", b"DALL-E", b"DALLE", b"GPT-4o", b"GPT-4"],
    "Google": [b"Google", b"SynthID", b"Gemini", b"Imagen", b"DeepMind"],
    "Adobe": [b"Adobe", b"Firefly", b"c2pa-rs"],
    "Meta": [b"VideoSeal", b"watermark-anything", b"WAM-"],
    "Stability": [b"Stability", b"Stable Diffusion"],
    "Midjourney": [b"Midjourney"],
    "TikTok": [b"TikTok", b"ByteDance"],
}

def scan_bytes(path, max_mb=32):
    """Raw C2PA/JUMBF + vendor scan, dependency-free. Returns dict."""
    out = {"c2pa_present": False, "claim_generator": "", "vendors": [], "footprint_bytes": 0, "notes": ""}
    try:
        size = os.path.getsize(path)
        with open(path, "rb") as f:
            data = f.read(min(size, max_mb * 1024 * 1024))
        hits = [m for m in C2PA_MARKERS if m in data]
        out["c2pa_present"] = len(hits) > 0
        out["footprint_bytes"] = len(data) if out["c2pa_present"] else 0
        for vendor, keys in VENDOR_HINTS.items():
            if any(k in data for k in keys):
                out["vendors"].append(vendor)
        # claim generator string near c2pa_claim
        m = re.search(rb"[A-Za-z0-9 _\-/]{3,80}c2pa[ -_a-z0-9]{0,20}|c2pa.{0,120}?(Adobe|OpenAI|Google|Meta|Stability|Midjourney)[ -_A-Za-z0-9./]{0,60}", data)
        if m:
            try:
                out["claim_generator"] = m.group(0)[:120].decode("utf-8", "ignore")
            except Exception:
                pass
        # try official c2pacheck lib if installed (tiny, no torch)
        try:
            from c2pacheck import check_file  # type: ignore
            r = check_file(path)
            if isinstance(r, dict):
                out["c2pacheck"] = {k: r.get(k) for k in ("present", "claim_generator", "signature", "assertions") if k in r}
        except Exception:
            pass
        if out["c2pa_present"] and "Google" in out["vendors"]:
            out["notes"] = "C2PA signed Google present -> SynthID pixels implied (verify in Gemini app / SynthID portal, no local pixel decode)."
        elif out["c2pa_present"] and "OpenAI" in out["vendors"]:
            out["notes"] = "C2PA signed OpenAI present -> SynthID+C2PA per May 2026 adoption (verify at openai.com/verify)."
        elif out["c2pa_present"]:
            out["notes"] = "C2PA manifest present, vendor unclear - treat as provenance supporting AI or camera."
        else:
            out["notes"] = "No C2PA manifest found in first 32MB - common for screenshots, crops, and older generators."
    except Exception as e:
        out["notes"] = f"scan error: {e}"
    return out

def exif_summary(pil_img, path=""):
    info = {"size": "", "format": "", "exif_tags": 0, "software": "", "png_text": {}}
    try:
        w, h = pil_img.size
        info["size"] = f"{w}x{h}"
        info["format"] = getattr(pil_img, "format", "") or os.path.splitext(str(path))[1].upper().lstrip(".")
        ex = pil_img.getexif() if hasattr(pil_img, "getexif") else {}
        info["exif_tags"] = len(ex) if ex else 0
        for tag_id, val in (ex.items() if ex else []):
            try:
                from PIL.ExifTags import TAGS
                if TAGS.get(tag_id) == "Software":
                    info["software"] = str(val)[:120]
            except Exception:
                pass
        if isinstance(getattr(pil_img, "info", None), dict):
            for k, v in pil_img.info.items():
                if isinstance(v, str) and len(v) < 300:
                    info["png_text"][str(k)[:40]] = v[:200]
    except Exception as e:
        info["error"] = str(e)[:200]
    return info

def sd_watermark_probe(pil_img):
    """Best-effort SD dwtDct decode probe. Returns dict with raw bits if decodable.
    Needs opencv + imwatermark (installed portable). Length unknown, so try common 32-bit."""
    out = {"checked": False, "decodable": False, "bits": "", "note": ""}
    try:
        import numpy as np
        import cv2
        from imwatermark import WatermarkDecoder
        import PIL.Image as PImage
        rgb = np.array(pil_img.convert("RGB"))
        bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
        out["checked"] = True
        for length in (32, 48, 64):
            try:
                dec = WatermarkDecoder("bytes", length // 8)
                raw = dec.decode(bgr, "dwtDct")
                if raw:
                    txt = raw.decode("utf-8", "ignore").replace("\x00", "").strip()
                    if len(txt) >= 2 and any(c.isalnum() for c in txt):
                        out["decodable"] = True
                        out["bits"] = f"len={length}: {txt[:120]}"
                        out["note"] = "dwtDct decoded bytes (SD-style watermark readable). Supports AI-origin, not proof of absence if empty."
                        return out
            except Exception:
                continue
        out["note"] = "No dwtDct payload decoded at 32/48/64-bit (normal for non-SD images, crops, or resized)."
    except Exception as e:
        out["note"] = f"watermark lib unavailable: {str(e)[:120]}"
    return out

def classical_scores(pil_img):
    """NPR-lite + texture-contrast + FFT high-freq, numpy/PIL only. Experimental 0-1, higher = more AI-like.
    Inspired by NPR (upsampling residual), PatchCraft (rich/poor texture), Synthbuster (spectral). Not calibrated."""
    import numpy as np
    s = {"npr_energy": 0.0, "texture_gap": 0.0, "hf_ratio": 0.0}
    try:
        img = pil_img.convert("RGB")
        small = img.resize((max(1, img.width // 2), max(1, img.height // 2)), Image.BILINEAR) if False else None
    except Exception:
        pass
    try:
        import numpy as np
        from PIL import Image as PImage
        g = np.array(pil_img.convert("L"), dtype=np.float32)
        h, w = g.shape
        # NPR-lite: down 2x then up, residual energy
        dw = np.array(pil_img.convert("L").resize((max(1, w // 2), max(1, h // 2)), PImage.BILINEAR).resize((w, h), PImage.BILINEAR), dtype=np.float32)
        npr = np.mean(np.abs(g - dw)) / 255.0
        s["npr_energy"] = round(float(min(1.0, npr * 4.0)), 4)
        # texture gap: split 32px patches by variance, compare residual energy rich vs poor
        import math
        res = g - dw
        vals_r, vals_p = [], []
        step = 32
        vars_ = []
        for y in range(0, h - step + 1, step):
            for x in range(0, w - step + 1, step):
                p = g[y:y + step, x:x + step]
                vars_.append((float(np.var(p)), (x, y)))
        if len(vars_) >= 8:
            vars_.sort(key=lambda t: t[0])
            q = max(2, len(vars_) // 4)
            poor = vars_[:q]
            rich = vars_[-q:]
            def ebox(lst):
                e = []
                for _, (x, y) in lst:
                    e.append(float(np.mean(np.abs(res[y:y + step, x:x + step]))))
                return float(np.mean(e)) if e else 0.0
            er, ep = ebox(rich), ebox(poor)
            gap = abs(er - ep) / max(1e-6, (er + ep) / 2.0)
            s["texture_gap"] = round(float(min(1.0, gap)), 4)
        # FFT high-frequency ratio
        F = np.abs(np.fft.fftshift(np.fft.fft2(g - np.mean(g))))
        cy, cx = h // 2, w // 2
        r = min(h, w) // 4
        yy, xx = np.ogrid[:h, :w]
        mask_hf = (yy - cy) ** 2 + (xx - cx) ** 2 > r * r
        hf = float(np.sum(F[mask_hf])) / max(1e-9, float(np.sum(F)))
        s["hf_ratio"] = round(hf, 4)
    except Exception:
        pass
    return s

from PIL import Image
