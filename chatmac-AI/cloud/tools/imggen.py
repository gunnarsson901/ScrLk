# ------------------ Image generation & caching ------------------
import os, io, base64, hashlib, time
from pathlib import Path
from PIL import Image
from openai import OpenAI

OPENAI_IMAGE_MODEL = "gpt-image-1"   # current image model
CRT_W, CRT_H = 512, 342              # your target

_client = None
def get_client():
    global _client
    if _client is None:
        _client = OpenAI()  # requires OPENAI_API_KEY in env
    return _client

def _prompt_key(prompt: str, style: str = "pixel-art") -> str:
    h = hashlib.sha1((prompt + "|" + style).encode("utf-8")).hexdigest()[:16]
    return h

def _letterbox_to_crt(im: Image.Image, w=CRT_W, h=CRT_H) -> Image.Image:
    """Resize to fit into 512x342 with CRT-friendly letterbox and center crop if needed."""
    # We’ll do cover (keep aspect, fill, then center-crop)
    src_w, src_h = im.size
    scale = max(w / src_w, h / src_h)
    new_w, new_h = int(src_w * scale), int(src_h * scale)
    im = im.resize((new_w, new_h), Image.NEAREST)  # pixel-art friendly
    # center crop
    left = (new_w - w) // 2
    top  = (new_h - h) // 2
    return im.crop((left, top, left + w, top + h))

def generate_image(prompt: str,
                   style: str = "pixel-art",
                   cache_dir: str = "assets/autogen",
                   retries: int = 2,
                   size: str = "512x512") -> str:
    """
    Returns path to a PNG for the prompt. Uses cache. Rescales to 512x342.
    """
    Path(cache_dir).mkdir(parents=True, exist_ok=True)
    key = _prompt_key(prompt, style)
    png_full = os.path.join(cache_dir, f"{key}.png")

    # cache hit?
    if os.path.isfile(png_full) and os.path.getsize(png_full) > 0:
        print(f"[images] cache hit: {png_full}")
        return png_full

    # ensure API key
    if not os.environ.get("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is not set; cannot generate images.")

    client = get_client()
    # prepend style guidance to stabilize look
    full_prompt = (
        f"{prompt}\n\nStyle: {style}. "
        "Monochrome/limited palette, coarse dithering, 8–16-bit home computer vibe. "
        "No text. Clear silhouettes. Centered composition."
    )

    last_err = None
    for attempt in range(1, retries + 2):
        try:
            print(f"[images] generate attempt {attempt}: {prompt!r}")
            resp = client.images.generate(
                model=OPENAI_IMAGE_MODEL,
                prompt=full_prompt,
                size=size,          # API wants square: 256x256, 512x512, 1024x1024
                quality="standard", # optional; remove if your SDK mismatches
                n=1
            )
            b64 = resp.data[0].b64_json
            raw = base64.b64decode(b64)

            # load, convert, rescale, save
            im = Image.open(io.BytesIO(raw)).convert("RGB")
            im = _letterbox_to_crt(im, CRT_W, CRT_H)
            im.save(png_full, "PNG", optimize=True)
            print(f"[images] wrote {png_full} ({im.size[0]}x{im.size[1]})")
            return png_full
        except Exception as e:
            last_err = e
            print(f"[images] error attempt {attempt}: {e}")
            time.sleep(0.8)

    raise RuntimeError(f"Image generation failed after retries: {last_err}")
