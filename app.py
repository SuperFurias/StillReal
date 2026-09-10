"""StillReal - portable Gradio UI for local AI image detection.
Model: buildborderless/CommunityForensics-DeepfakeDet-ViT (Community Forensics CVPR25, MIT)
Engine: model/model.onnx via onnxruntime CPU. No torch, no internet, no system Python.
Run: ui.bat  or  python-portable\\python.exe app.py
"""
import os
import io
import csv
import sys
import time
BASE = os.path.dirname(os.path.abspath(__file__))
if BASE not in sys.path:
    sys.path.insert(0, BASE)
import tempfile
import traceback
import numpy as np
from PIL import Image

import gradio as gr
import onnxruntime as ort
import requests
import forensic as FR

MODEL_BASE = os.path.join(BASE, "model", "model.onnx")
MODEL_SIEVE = os.path.join(BASE, "model", "sieve-v014.onnx")
MODEL_FAST = os.path.join(BASE, "model", "model_int8.onnx")
DEFAULT_MODEL = MODEL_SIEVE
TEST_DIR = os.path.join(BASE, "test_images")

MEAN_BASE = np.array([0.4815, 0.4578, 0.4082], dtype=np.float32)
STD_BASE = np.array([0.2686, 0.2613, 0.2758], dtype=np.float32)
MEAN_SIEVE = np.array([0.485, 0.456, 0.406], dtype=np.float32)
STD_SIEVE = np.array([0.229, 0.224, 0.225], dtype=np.float32)
BIAS_SIEVE = 0.2

_SESS_CACHE = {}

def pick_providers(engine="auto"):
    try:
        avail = ort.get_available_providers()
    except Exception:
        avail = ["CPUExecutionProvider"]
    if engine == "cpu":
        return ["CPUExecutionProvider"]
    # auto: GPU via DirectML (any DirectX 12 GPU) or CUDA when present, else CPU - portable, no CUDA install
    if "DmlExecutionProvider" in avail:
        return ["DmlExecutionProvider", "CPUExecutionProvider"]
    if "CUDAExecutionProvider" in avail:
        return ["CUDAExecutionProvider", "CPUExecutionProvider"]
    return ["CPUExecutionProvider"]

def get_session(model_path=DEFAULT_MODEL, engine="auto"):
    key = f"{model_path}|{engine}"
    if key not in _SESS_CACHE:
        if not os.path.exists(model_path):
            raise FileNotFoundError(f"Model not found: {model_path}")
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = max(1, (os.cpu_count() or 4) - 1)
        opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        _SESS_CACHE[key] = ort.InferenceSession(model_path, sess_options=opts, providers=pick_providers(engine))
    return _SESS_CACHE[key]

def preprocess_pil(pil_img, use_sieve=True):
    img = pil_img.convert("RGB")
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
    return arr, img

def sigmoid(x):
    return 1.0 / (1.0 + np.exp(-x))

def crops_tta(pil_img):
    """5-crop + hflip on the 440-resized image, 384 boxes. Portable, numpy/PIL only."""
    img = pil_img.convert("RGB")
    w, h = img.size
    scale = 440.0 / min(w, h)
    nw, nh = int(round(w * scale)), int(round(h * scale))
    big = img.resize((nw, nh), Image.BICUBIC)
    boxes = [
        (0, 0), (nw - 384, 0), (0, nh - 384), (nw - 384, nh - 384),
        ((nw - 384) // 2, (nh - 384) // 2),
    ]
    outs = []
    for l, t in boxes:
        c = big.crop((l, t, l + 384, t + 384))
        outs.append(c)
        outs.append(c.transpose(Image.FLIP_LEFT_RIGHT))
    return outs

def arr_for(pil_crop, use_sieve):
    MEAN = MEAN_SIEVE if use_sieve else MEAN_BASE
    STD = STD_SIEVE if use_sieve else STD_BASE
    arr = np.array(pil_crop, dtype=np.float32) / 255.0
    arr = (arr - MEAN) / STD
    return np.transpose(arr, (2, 0, 1))[None, :, :, :].astype(np.float32)

def score_logits(sess, crops, use_sieve):
    name = sess.get_inputs()[0].name
    logits = []
    for c in crops:
        x = arr_for(c, use_sieve)
        logits.append(float(sess.run(None, {name: x})[0].ravel()[0]))
    return logits

def noise_views(pil_img):
    """Residual + FFT spectrum helper, inspired by SynthID-Bypass visualization (amplify low-level noise).
    Detection aid only - does not decode any watermark."""
    g = np.array(pil_img.convert("RGB"), dtype=np.float32)
    # fast box-blur denoise via PIL, residual = orig - blurred
    blur = np.array(pil_img.convert("RGB").resize((max(1, pil_img.width // 2), max(1, pil_img.height // 2)), Image.BILINEAR).resize(pil_img.size, Image.BILINEAR), dtype=np.float32)
    res = g - blur
    res_n = (res - res.min()) / max(1e-6, (res.max() - res.min()))
    res_img = Image.fromarray((res_n * 255).astype(np.uint8))
    gray = np.array(pil_img.convert("L"), dtype=np.float32)
    F = np.fft.fftshift(np.fft.fft2(gray))
    mag = np.log1p(np.abs(F))
    mag = (mag - mag.min()) / max(1e-6, (mag.max() - mag.min()))
    spec = Image.fromarray((mag * 255).astype(np.uint8)).resize((384, 384))
    return res_img, spec

def meta_text(pil_img, path="<upload>"):
    try:
        ex = pil_img.getexif() if hasattr(pil_img, "getexif") else {}
        ex_n = len(ex) if ex else 0
    except Exception:
        ex_n = 0
    w, h = pil_img.size
    return f"file: {os.path.basename(str(path))} | {w}x{h} | EXIF tags: {ex_n} | Note: C2PA/SynthID pixel decode needs Google/OpenAI verifier; this tool is artifact P(AI) only."

def score_pil(pil_img, threshold=0.5, model_choice="ensemble", use_tta=True, engine="auto", speed="quality"):
    # speed=fast: INT8 base single-crop, no TTA, ~5-10x faster, slight accuracy drop
    if speed == "fast":
        if not os.path.exists(MODEL_FAST):
            raise FileNotFoundError(f"Fast model missing: {MODEL_FAST}")
        sess = get_session(MODEL_FAST, engine)
        x, crop = preprocess_pil(pil_img, False)
        logit = float(sess.run(None, {sess.get_inputs()[0].name: x})[0].ravel()[0])
        p_ai = float(sigmoid(np.array(logit, dtype=np.float64)))
        p_real = 1.0 - p_ai
        label = "AI-GENERATED" if p_ai >= threshold else "REAL"
        return p_ai, p_real, label, (0.35 <= p_ai <= 0.65), crop, p_ai, None
    want_base = model_choice in ("base", "ensemble")
    want_sieve = model_choice in ("sieve", "ensemble")
    p_b = p_s = None
    crop = None
    if want_base and os.path.exists(MODEL_BASE):
        sess = get_session(MODEL_BASE, engine)
        if use_tta:
            logits = score_logits(sess, crops_tta(pil_img), False)
            logit = float(np.mean(logits))
        else:
            x, _c = preprocess_pil(pil_img, False)
            logit = float(sess.run(None, {sess.get_inputs()[0].name: x})[0].ravel()[0])
        p_b = float(sigmoid(np.array(logit, dtype=np.float64)))
        _, crop = preprocess_pil(pil_img, False)
    if want_sieve and os.path.exists(MODEL_SIEVE):
        sess = get_session(MODEL_SIEVE, engine)
        if use_tta:
            logits = score_logits(sess, crops_tta(pil_img), True)
            logit = float(np.mean(logits)) + BIAS_SIEVE
        else:
            x, _c = preprocess_pil(pil_img, True)
            logit = float(sess.run(None, {sess.get_inputs()[0].name: x})[0].ravel()[0]) + BIAS_SIEVE
        p_s = float(sigmoid(np.array(logit, dtype=np.float64)))
        _, crop = preprocess_pil(pil_img, True)
    vals = [v for v in (p_b, p_s) if v is not None]
    if not vals:
        raise FileNotFoundError("No models found in model/")
    p_ai = sum(vals) / len(vals) if model_choice == "ensemble" else vals[0]
    if model_choice == "base":
        p_ai = p_b
    elif model_choice == "sieve":
        p_ai = p_s
    p_real = 1.0 - p_ai
    label = "AI-GENERATED" if p_ai >= threshold else "REAL"
    borderline = 0.35 <= p_ai <= 0.65
    return p_ai, p_real, label, borderline, crop, p_b, p_s

def badge_html(label, p_ai, borderline):
    is_ai = label == "AI-GENERATED"
    color = "#ff6b6b" if is_ai else "#51cf66"
    bg = "rgba(255,107,107,0.10)" if is_ai else "rgba(81,207,102,0.10)"
    border = "rgba(255,107,107,0.45)" if is_ai else "rgba(81,207,102,0.45)"
    pill = "AI-GENERATED" if is_ai else "REAL"
    extra = "<div style='margin-top:10px;font-size:13px;color:#ffd43b'>Borderline 0.35-0.65: weak evidence. Try other model + check source / C2PA.</div>" if borderline else ""
    pct = max(2.0, p_ai * 100.0)
    bar = f"""<div style='background:rgba(255,255,255,0.10);border-radius:999px;height:10px;margin-top:12px;overflow:hidden'>
      <div style='width:{pct:.1f}%;background:{color};height:10px;border-radius:999px'></div></div>
      <div style='display:flex;justify-content:space-between;font-size:13px;color:#adb5bd;margin-top:8px'>
        <span>P(AI) <b style='color:#fff'>{p_ai:.4f}</b></span><span>P(real) <b style='color:#fff'>{1-p_ai:.4f}</b></span></div>"""
    return f"""<div style='border:1px solid {border};background:{bg};border-radius:16px;padding:20px'>
      <div style='display:inline-block;font-size:12px;letter-spacing:1.5px;font-weight:800;color:{color};border:1px solid {border};border-radius:999px;padding:4px 12px;margin-bottom:10px'>{pill}</div>
      <div style='font-size:34px;font-weight:800;color:#fff;line-height:1'>{pill}</div>{bar}{extra}</div>"""

def plain_sentence(label, p_ai, borderline, c2pa, sd):
    conf = int(round((p_ai if label == "AI-GENERATED" else 1 - p_ai) * 100))
    if label == "AI-GENERATED":
        s = f"This looks <b>AI-generated</b> ({conf}% confident)."
    else:
        s = f"This looks like a <b>real photo</b> ({conf}% confident)."
    if borderline:
        s += " Result is <b>borderline</b> - treat as weak evidence."
    if c2pa.get("c2pa_present"):
        s += f" File carries a C2PA manifest {c2pa.get('vendors') or ''}."
    else:
        s += " No C2PA manifest found."
    if sd.get("decodable"):
        s += " SD-style invisible watermark readable."
    return s

def details_block(scores, c2pa, exif, sd, freq):
    import html as _h
    lines = [
        f"> Verdict  : {scores['verdict']}  P(AI)={scores['P(AI)']}  P(real)={scores['P(real)']}  thr={scores['threshold']}",
        f"> Models   : {scores['model']}  base={scores['P_base']}  sieve={scores['P_sieve']}  tta={scores['tta']}  engine={scores['engine']}  speed={scores['speed']}  {scores['ms']}ms",
        f"> C2PA     : present={c2pa['c2pa_present']} vendors={c2pa['vendors'] or '-'} gen={c2pa.get('claim_generator','')[:80]}",
        f"> C2PA note: {c2pa['notes']}",
        f"> EXIF     : {exif.get('size')} {exif.get('format')} tags={exif.get('exif_tags')} software={exif.get('software','')[:60]}",
        f"> SD-wm    : checked={sd.get('checked')} decodable={sd.get('decodable')} {str(sd.get('bits',''))[:80]}",
        f"> Classical: NPR={freq.get('npr_energy')} gap={freq.get('texture_gap')} hf={freq.get('hf_ratio')} (experimental, not calibrated)",
    ]
    pre = "\n".join(_h.escape(l) for l in lines)
    return f"""<details style='margin-top:10px;border:1px solid #2a2f45;border-radius:10px;padding:10px 12px;background:#0b0f1f'>
    <summary style='cursor:pointer;color:#c4b5fd;font-size:13px'>&gt; Technical details (click to expand)</summary>
    <pre style='white-space:pre-wrap;font-size:12px;color:#a8b0c5;margin:8px 0 0 0'>{pre}</pre></details>"""

def single_fn(image, threshold, model_choice="ensemble", use_tta=True, engine="auto", speed="quality"):
    if image is None:
        return "<i>Upload an image then press Verify.</i>", {}, None, None, None, ""
    t0 = time.time()
    try:
        # accept filepath (new Upload) or PIL (URL/batch legacy)
        path = image if isinstance(image, str) else None
        pil = Image.open(path).convert("RGB") if path else image.convert("RGB")
        p_ai, p_real, label, borderline, crop, p_b, p_s = score_pil(pil, threshold, model_choice, use_tta, engine, speed)
        res_img, spec_img = noise_views(pil)
        try:
            c2pa = FR.scan_bytes(path) if path and os.path.exists(path) else {"c2pa_present": False, "claim_generator": "", "vendors": [], "footprint_bytes": 0, "notes": "URL/paste has no file bytes for C2PA - save file and use Upload for provenance."}
            exif = FR.exif_summary(pil, path or "<upload>")
            sd = FR.sd_watermark_probe(pil)
            freq = FR.classical_scores(pil)
        except Exception:
            c2pa = {"c2pa_present": False, "claim_generator": "", "vendors": [], "footprint_bytes": 0, "notes": ""}
            exif, sd, freq = {}, {}, {}
        dt = time.time() - t0
        prov = pick_providers(engine)[0]
        scores = {"P(AI)": round(p_ai, 6), "P(real)": round(p_real, 6), "P_base": None if p_b is None else round(p_b, 6), "P_sieve": None if p_s is None else round(p_s, 6), "threshold": threshold, "model": model_choice, "tta": use_tta, "engine": prov, "speed": speed, "verdict": label, "ms": round(dt*1000, 1)}
        html = badge_html(label, p_ai, borderline)
        html += f"<div style='font-size:15px;color:#e9ecef;margin-top:10px'>{plain_sentence(label, p_ai, borderline, c2pa, sd)}</div>"
        html += details_block(scores, c2pa, exif, sd, freq)
        meta = meta_text(pil, path or "<upload>")
        return html, scores, crop, res_img, spec_img, meta
    except Exception as e:
        traceback.print_exc()
        return f"<b style='color:red'>Error: {e}</b>", {}, None, None, None, ""

def batch_fn(files, threshold, model_choice="ensemble", use_tta=True, engine="auto", speed="quality"):
    if not files:
        return "Upload one or more images.", None, None
    rows = []
    gallery = []
    for f in files:
        name = os.path.basename(getattr(f, "name", str(f)) if not isinstance(f, str) else f)
        path = f.name if hasattr(f, "name") else f
        try:
            pil = Image.open(path).convert("RGB")
            p_ai, p_real, label, borderline, _c, p_b, p_s = score_pil(pil, threshold, model_choice, use_tta, engine, speed)
            flag = "borderline" if borderline else ""
            rows.append([name, label, f"{p_ai:.4f}", f"{p_real:.4f}", "" if p_b is None else f"{p_b:.3f}", "" if p_s is None else f"{p_s:.3f}", flag])
            gallery.append((pil, f"{label} {p_ai:.2f}"))
        except Exception as e:
            rows.append([name, "ERROR", "", "", "", "", str(e)[:120]])
    import pandas as pd
    df = pd.DataFrame(rows, columns=["file", "verdict", "P(AI)", "P(real)", "P_base", "P_sieve", "note"])
    n_ai = sum(1 for r in rows if r[1] == "AI-GENERATED")
    summary = f"### {n_ai}/{len(rows)} flagged AI @ threshold {threshold} model {model_choice}\nSort by P(AI) to triage. Download CSV for records."
    # CSV for download
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".csv", mode="w", newline="", encoding="utf-8")
    w = csv.writer(tmp)
    w.writerow(["file", "verdict", "P(AI)", "P(real)", "P_base", "P_sieve", "note"])
    w.writerows(rows)
    tmp.close()
    return summary, df, tmp.name

def url_fn(url, threshold, model_choice="ensemble", use_tta=True, engine="auto", speed="quality"):
    if not url or not url.strip():
        return "<i>Paste an http(s) image URL.</i>", {}, None, None, None, ""
    try:
        r = requests.get(url.strip(), timeout=30, headers={"User-Agent": "stillreal/1.0"})
        r.raise_for_status()
        pil = Image.open(io.BytesIO(r.content)).convert("RGB")
        return single_fn(pil, threshold, model_choice, use_tta, engine, speed)
    except Exception as e:
        return f"<b style='color:red'>Download failed: {e}</b>", {}, None, None, None, ""

def examples_list():
    if not os.path.isdir(TEST_DIR):
        return []
    exts = (".png", ".jpg", ".jpeg", ".webp", ".bmp")
    fs = [os.path.join(TEST_DIR, f) for f in sorted(os.listdir(TEST_DIR)) if f.lower().endswith(exts)][:8]
    return [[f] for f in fs] if fs else []

def forensic_fn(file_obj):
    """Provenance + classical forensics tab. Button-only, no auto-run."""
    if file_obj is None:
        return {}, {}, {}, "Upload a file then press Check provenance."
    path = file_obj.name if hasattr(file_obj, "name") else str(file_obj)
    try:
        pil = Image.open(path).convert("RGB")
    except Exception as e:
        return {}, {}, {}, f"Open failed: {e}"
    c2pa = FR.scan_bytes(path)
    exif = FR.exif_summary(pil, path)
    sd = FR.sd_watermark_probe(pil)
    freq = FR.classical_scores(pil)
    summary = f"C2PA={'PRESENT' if c2pa['c2pa_present'] else 'absent'} vendors={c2pa['vendors'] or '-'} | SD-wm={'yes' if sd.get('decodable') else 'no'} | NPR={freq.get('npr_energy')} gap={freq.get('texture_gap')} hf={freq.get('hf_ratio')} | {c2pa['notes']}"
    return (c2pa, exif, {"sd_watermark": sd, "classical_experimental": freq}, summary)

CSS = """
html, body {background:#000 !important; margin:0 !important; padding:0 !important;}
.gradio-container {max-width: none !important; width: 100% !important; margin: 0 !important; padding: 0 32px 40px 32px !important; background:#000 !important; color:#fff !important;}
footer {display:none !important;}
#topbar {display:flex;justify-content:space-between;align-items:center;padding:18px 0 6px 0;max-width:1400px;margin:0 auto;width:100%;}
#brand {font-weight:800;font-size:18px;letter-spacing:0.2px;}
#brand span.dot {color:#8b5cf6;}
#pills {display:flex;gap:8px;}
.pill {font-size:12px;border:1px solid #2a2f45;border-radius:999px;padding:6px 12px;color:#c4b5fd;background:#12172a;}
#hero {text-align:center;padding:20px 20px 6px 20px;max-width:1400px;margin:0 auto;width:100%;}
#hero h1 {font-size:clamp(30px,3.6vw,52px);line-height:1.02;font-weight:800;letter-spacing:-1px;margin:0;color:#fff;}
#hero p {color:#cbd5e1;font-size:15px;margin-top:10px;}
#controls {background:#0b0f1f;border:1px solid #1e2542;border-radius:16px;padding:12px 16px;margin:14px auto;max-width:1400px;width:100%;}
#upload-card {background:#141c33 !important;border:1px solid #263056 !important;border-radius:20px !important;padding:10px !important;max-width:1400px;margin:0 auto;width:100%;}
.image-container, #upload-card .image-container {height:auto !important;min-height:200px !important;max-height:52vh !important;}
.image-container img, .image-frame img {object-fit:contain !important;width:100% !important;height:auto !important;max-height:48vh !important;}
.mini img {max-height:170px !important;}
.mini .image-container {min-height:150px !important;max-height:190px !important;}
.tabs, .tab-nav, .tabpanel {max-width:1400px !important;margin:0 auto !important;width:100% !important;}
.info-grid {display:grid;grid-template-columns:1fr 1fr 1fr;gap:16px;margin:26px auto 0 auto;max-width:1400px;width:100%;}
.info-card {background:#000;border:1px solid #232842;border-radius:16px;padding:22px;}
.info-card h3 {margin:12px 0 10px 0;font-size:19px;}
.info-card p {color:#a8b0c5;font-size:14.5px;line-height:1.55;}
.info-icon {width:36px;height:36px;border-radius:10px;background:#151b33;display:flex;align-items:center;justify-content:center;font-size:19px;}
@media (max-width: 900px){ #hero h1{font-size:38px;} .info-grid{grid-template-columns:1fr;} }
.tabs {background:transparent !important;}
button.lg {border-radius:12px !important;height:48px !important;font-size:16px !important;font-weight:700 !important;}
"""

with gr.Blocks(title="StillReal - Verify AI-generated images", css=CSS, theme=gr.themes.Base(primary_hue="violet", neutral_hue="slate")) as demo:
    gr.HTML("""<div id='topbar'><div id='brand'><span class='dot'>◉</span> StillReal</div>
    <div id='pills'><span class='pill'>Local • No upload</span><span class='pill'>MIT • ONNX CPU</span><span class='pill'>ensemble / sieve / base</span></div></div>""")
    gr.HTML("""<div id='hero'><h1>Verify AI-generated<br/>images</h1>
    <p>Upload an image to check for signals it was generated with AI tools.<br/>Fully local Community Forensics + Sieve v0.14. Files never leave this machine.</p></div>""")

    with gr.Group(elem_id="controls"):
        with gr.Row():
            model_sel = gr.Dropdown(["ensemble", "sieve", "base"], value="ensemble", label="Model — ensemble = most robust, sieve = modern / anime, base = old generators")
            thr = gr.Slider(0.1, 0.9, value=0.5, step=0.01, label="Threshold P(AI) → AI-GENERATED — 0.50 default, 0.65 fewer false positives")
            tta = gr.Checkbox(value=True, label="TTA 10-crop vote (slower, +2-4% robust)")
        with gr.Row():
            engine_sel = gr.Dropdown(["auto", "cpu"], value="auto", label="Engine — auto = GPU (DirectML/CUDA) if present else CPU")
            speed_sel = gr.Dropdown(["quality", "fast"], value="quality", label="Speed — quality FP32 ensemble, fast INT8 single (5-10x faster)")

    with gr.Tabs():
        with gr.Tab("Upload"):
            with gr.Row():
                with gr.Column(scale=7):
                    with gr.Group(elem_id="upload-card"):
                        inp = gr.Image(type="filepath", label="Upload — PNG JPG WEBP BMP TIF (preview instant, runs only on Verify)", sources=["upload", "clipboard"], height=None)
                    btn = gr.Button("Verify image", variant="primary", elem_classes=["lg"])
                with gr.Column(scale=5):
                    out_html = gr.HTML(label="Verdict")
                    out_json = gr.JSON(label="Signals")
                    meta_out = gr.Textbox(label="File note", interactive=False, lines=2)
            gr.HTML("<div style='text-align:center;color:#8b93b0;font-size:12px;margin:6px 0'>Files stay local. Supported: PNG, JPG, WEBP, BMP, TIF.</div>")
            with gr.Row(elem_classes=["mini"]):
                crop_out = gr.Image(label="Model crop", interactive=False, height=None)
                res_out = gr.Image(label="Residual", interactive=False, height=None)
                spec_out = gr.Image(label="Spectrum", interactive=False, height=None)
            btn.click(single_fn, [inp, thr, model_sel, tta, engine_sel, speed_sel], [out_html, out_json, crop_out, res_out, spec_out, meta_out])

        with gr.Tab("Batch"):
            files = gr.File(file_count="multiple", file_types=["image"], label="Upload files — multiple images, CSV export")
            b_btn = gr.Button("Verify batch", variant="primary", elem_classes=["lg"])
            b_md = gr.Markdown()
            b_df = gr.Dataframe(headers=["file", "verdict", "P(AI)", "P(real)", "P_base", "P_sieve", "note"], interactive=False, wrap=True)
            b_csv = gr.File(label="Download CSV")
            b_btn.click(batch_fn, [files, thr, model_sel, tta, engine_sel, speed_sel], [b_md, b_df, b_csv])

        with gr.Tab("Image URL"):
            url = gr.Textbox(label="Image URL", placeholder="https://.../photo.jpg")
            u_btn = gr.Button("Fetch + Verify", variant="primary", elem_classes=["lg"])
            u_html = gr.HTML()
            u_json = gr.JSON()
            with gr.Row():
                u_crop = gr.Image(interactive=False, label="Model crop", height=None)
                u_res = gr.Image(interactive=False, label="Residual", height=None)
                u_spec = gr.Image(interactive=False, label="Spectrum", height=None)
            u_meta = gr.Textbox(interactive=False, label="Note")
            u_btn.click(url_fn, [url, thr, model_sel, tta, engine_sel, speed_sel], [u_html, u_json, u_crop, u_res, u_spec, u_meta])

    gr.HTML("""<div class='info-grid'>
      <div class='info-card'><div class='info-icon'>◎</div><h3>What does this tool do?</h3>
      <p><b>StillReal</b> gives a plain verdict - <b>REAL / AI-GENERATED + % confident</b> - from two local ViT models (Community Forensics + Sieve v0.14, TTA vote, GPU DirectML or CPU). Same screen adds provenance: C2PA manifest scan, EXIF/software, SD watermark probe, noise residual + FFT views. Details hide under <b>&gt; Technical details</b>. No upload, no account, button-only.</p></div>
      <div class='info-card'><div class='info-icon'>⚒</div><h3>What content can it detect?</h3>
      <p>Old GANs (ProGAN, StyleGAN, BigGAN) + diffusion (SD 1.5 / XL / 3.5, Flux, Midjourney, DALL-E) + modern commercial via Sieve fine-tune. Speed <b>fast</b> = 22MB INT8 single (~5-10x faster); <b>quality</b> = FP32 ensemble. Anime and Flux/MJ v7/Imagen 4 remain hardest - 0.35-0.65 means weak evidence, try all three models.</p></div>
      <div class='info-card'><div class='info-icon'>⇪</div><h3>How do I use it?</h3>
      <p>Upload (left), pick model + threshold (0.50 default, 0.65 fewer false alarms) + engine <b>auto</b> for GPU if present, press <b>Verify image</b>. Read the sentence, expand details if needed. Batch tab does folders + CSV. For Google / OpenAI images also check Gemini Verify with SynthID + C2PA - no local tool decodes SynthID pixels.</p></div>
    </div>
    <div style='text-align:center;color:#5b637e;font-size:12px;margin:22px 0 10px 0'>StillReal • python-portable/ • model/model.onnx + sieve-v014.onnx • CLI: run.bat photo.jpg --model ensemble</div>""")

if __name__ == "__main__":
    for p in (MODEL_BASE, MODEL_SIEVE):
        try:
            get_session(p)
            print(f"loaded {p}")
        except Exception as e:
            print(f"model skip {p}: {e}")
    demo.launch(server_name="127.0.0.1", server_port=7860, inbrowser=True, show_error=True)
