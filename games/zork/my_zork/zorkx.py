#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os, sys, io, time, json, math, tempfile, threading, queue, hashlib
import tkinter as tk
from tkinter import Canvas
from PIL import Image, ImageTk
import numpy as np
import sounddevice as sd
import soundfile as sf
from scipy.io.wavfile import write as wav_write

# ================== CONFIG ==================
GAME_RESOLUTION = (512, 342)      # Macintosh CRT
STYLE = "pixel art, 1-bit vibe, retro macintosh, simple shapes, high contrast"
MODEL_CHAT = "gpt-4o-mini"
MODEL_WHISPER = "whisper-1"
MODEL_TTS = "tts-1"
VOICE_TTS = "onyx"
MODEL_IMG = "gpt-image-1"         # DALL·E / Images API

REC_SAMPLE_RATE = 16000
REC_CHANNELS = 1
REC_SECONDS = 4.0                  # voice window length
LISTEN_COOLDOWN_S = 0.6            # after TTS before listening again

ASSET_ROOT = os.path.abspath("./assets")
ROOM_DIR = os.path.join(ASSET_ROOT, "rooms")
ITEM_DIR = os.path.join(ASSET_ROOT, "items")
os.makedirs(ROOM_DIR, exist_ok=True)
os.makedirs(ITEM_DIR, exist_ok=True)

OPENAI_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_KEY:
    print("ERROR: Set OPENAI_API_KEY in your environment.", file=sys.stderr)

try:
    from openai import OpenAI
    oai = OpenAI(api_key=OPENAI_KEY)
except Exception as e:
    print("OpenAI client error:", e, file=sys.stderr)
    oai = None

# ================== CRT UI ==================
class CRTWindow:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Macintosh Voice Adventure")
        self.root.geometry(f"{GAME_RESOLUTION[0]}x{GAME_RESOLUTION[1]}")
        self.root.configure(bg="black")
        self.root.resizable(False, False)

        self.canvas = Canvas(self.root, width=GAME_RESOLUTION[0], height=GAME_RESOLUTION[1],
                             bg="black", highlightthickness=0)
        self.canvas.pack()

        self.current_image = None
        self._tk_refs = []  # prevent GC
        self.text_lines = []
        self.root.bind("<Escape>", lambda e: self.root.quit())

    def clear(self):
        self.canvas.delete("all")
        self._tk_refs.clear()

    def draw_room_image(self, pil_image):
        if pil_image is None: return
        pil = pil_image.resize(GAME_RESOLUTION, Image.NEAREST)
        self.current_image = ImageTk.PhotoImage(pil)
        self._tk_refs.append(self.current_image)
        self.canvas.create_image(0, 0, image=self.current_image, anchor="nw")

    def draw_text(self, text, color="#00FF00"):
        max_lines = 6
        self.text_lines.append(text)
        if len(self.text_lines) > max_lines:
            self.text_lines = self.text_lines[-max_lines:]

        # bottom black band
        txt_h = 80
        self.canvas.create_rectangle(0, GAME_RESOLUTION[1] - txt_h,
                                     GAME_RESOLUTION[0], GAME_RESOLUTION[1],
                                     fill="black", outline="")
        y = GAME_RESOLUTION[1] - txt_h + 6
        for line in self.text_lines:
            self.canvas.create_text(10, y, anchor="nw", text=line, fill=color, font=("Courier", 12))
            y += 12

    def draw_inventory(self, items):
        inv_h = 44
        # top bar
        self.canvas.create_rectangle(0, 0, GAME_RESOLUTION[0], inv_h, fill="black", outline="")
        x = 6
        for item in items:
            icon_path = os.path.join(ITEM_DIR, f"{safe_slug(item)}.png")
            if os.path.exists(icon_path):
                pil = Image.open(icon_path).resize((32, 32), Image.NEAREST)
                tk_img = ImageTk.PhotoImage(pil)
                self._tk_refs.append(tk_img)
                self.canvas.create_image(x, 6, image=tk_img, anchor="nw")
            self.canvas.create_text(x + 36, 12, anchor="nw", text=item, fill="#CCCCCC", font=("Courier", 10))
            x += 120

    def update(self):
        self.root.update_idletasks()
        self.root.update()

# ================== Helpers ==================
def safe_slug(s: str) -> str:
    return "".join(ch for ch in s.lower().strip().replace(" ", "_") if ch.isalnum() or ch in "._-")

def hash_text(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()[:16]

# ================== Voice I/O ==================
class VoiceIO:
    def __init__(self):
        self.is_speaking = False
        self.last_talk_end = 0.0

    def record_wav(self, seconds=REC_SECONDS) -> str | None:
        # block recording if we just spoke (avoid TTS feedback)
        if time.time() - self.last_talk_end < LISTEN_COOLDOWN_S:
            time.sleep(max(0.0, LISTEN_COOLDOWN_S - (time.time() - self.last_talk_end)))

        try:
            frames = int(REC_SAMPLE_RATE * seconds)
            audio = sd.rec(frames, samplerate=REC_SAMPLE_RATE, channels=REC_CHANNELS, dtype="float32")
            sd.wait()
            # normalize gently
            peak = float(np.max(np.abs(audio))) if audio.size else 0.0
            if peak > 1e-6:
                audio = audio / max(1.0, peak)

            tmp = os.path.join(tempfile.gettempdir(), f"va_in_{int(time.time()*1000)}.wav")
            wav_write(tmp, REC_SAMPLE_RATE, (audio * 32767).astype(np.int16))
            return tmp
        except Exception as e:
            print("Record error:", e, file=sys.stderr)
            return None

    def transcribe(self, wav_path: str) -> str | None:
        if oai is None: return None
        try:
            with open(wav_path, "rb") as f:
                tr = oai.audio.transcriptions.create(model=MODEL_WHISPER, file=f)
            txt = (tr.text or "").strip()
            return txt or None
        except Exception as e:
            print("Whisper error:", e, file=sys.stderr)
            return None
        finally:
            try: os.remove(wav_path)
            except: pass

    def speak(self, text: str):
        if not text or oai is None: return
        def _run():
            self.is_speaking = True
            try:
                # Request WAV (note: response_format must be "wav")
                res = oai.audio.speech.create(model=MODEL_TTS, voice=VOICE_TTS,
                                              input=text, response_format="wav")
                # Get bytes
                try:
                    audio_bytes = res.read()
                except AttributeError:
                    audio_bytes = getattr(res, "content", None)
                    if audio_bytes is None:
                        audio_bytes = bytes(res)
                # Play
                with sf.SoundFile(io.BytesIO(audio_bytes)) as snd:
                    data = snd.read(dtype="float32")
                    sd.play(data, snd.samplerate)
                    sd.wait()
            except Exception as e:
                print("TTS error:", e, file=sys.stderr)
            finally:
                self.is_speaking = False
                self.last_talk_end = time.time()
        threading.Thread(target=_run, daemon=True).start()

# ================== Image Generation ==================
class ImageGen:
    def __init__(self):
        pass

    def prompt_room(self, scene_summary: str) -> str:
        return (
            f"Pixel-art scene, {STYLE}. Macintosh Classic resolution 512x342. "
            f"Wide single frame, no text. Scene: {scene_summary}."
        )

    def prompt_item(self, item_name: str) -> str:
        return (
            f"Pixel-art icon, {STYLE}. Transparent background. "
            f"Centered 32x32 sprite of '{item_name}'. No text."
        )

    def gen_room(self, key: str, scene_summary: str) -> Image.Image | None:
        """Generate or load cached room image."""
        fname = os.path.join(ROOM_DIR, f"{safe_slug(key)}.png")
        if os.path.exists(fname):
            try: return Image.open(fname)
            except: pass
        if oai is None: return None
        try:
            prompt = self.prompt_room(scene_summary)
            img = oai.images.generate(model=MODEL_IMG, prompt=prompt, size="512x512", quality="standard", n=1)
            b64 = img.data[0].b64_json
            raw = io.BytesIO()
            raw.write(base64_decode(b64))
            raw.seek(0)
            pil = Image.open(raw).convert("RGBA")
            # center-crop to 512x342 (letterbox)
            pil = crop_to_512x342(pil)
            pil.save(fname)
            return pil
        except Exception as e:
            print("Image gen (room) error:", e, file=sys.stderr)
            return None

    def gen_item_icon(self, item_name: str) -> str | None:
        """Generate or load cached 32x32 icon."""
        fname = os.path.join(ITEM_DIR, f"{safe_slug(item_name)}.png")
        if os.path.exists(fname):
            return fname
        if oai is None: return None
        try:
            prompt = self.prompt_item(item_name)
            img = oai.images.generate(model=MODEL_IMG, prompt=prompt, size="256x256", quality="standard", n=1)
            b64 = img.data[0].b64_json
            raw = io.BytesIO()
            raw.write(base64_decode(b64))
            raw.seek(0)
            pil = Image.open(raw).convert("RGBA")
            pil = pil.resize((32, 32), Image.NEAREST)
            pil.save(fname)
            return fname
        except Exception as e:
            print("Image gen (item) error:", e, file=sys.stderr)
            return None

def crop_to_512x342(pil: Image.Image) -> Image.Image:
    # keep center, fit height then crop width
    target_w, target_h = 512, 342
    w, h = pil.size
    # scale by height
    scale = target_h / h
    new_w = int(w * scale)
    pil2 = pil.resize((new_w, target_h), Image.NEAREST)
    # crop center to width
    if new_w >= target_w:
        x0 = (new_w - target_w) // 2
        return pil2.crop((x0, 0, x0 + target_w, target_h))
    # if too narrow, pad
    out = Image.new("RGBA", (target_w, target_h), (0, 0, 0, 255))
    x0 = (target_w - new_w) // 2
    out.paste(pil2, (x0, 0))
    return out

def base64_decode(b64: str) -> bytes:
    import base64
    return base64.b64decode(b64.encode("utf-8"))

# ================== Game Engine (GPT DM) ==================
GAME_SYSTEM = (
    "You are the game master for a voice-controlled, visual, Zork-like adventure. "
    "Keep responses VERY short. Output strict JSON with keys:\n"
    "scene: one-sentence cinematic description of the current room.\n"
    "say: one short line the narrator should speak.\n"
    "items: array of item names visible or carried (strings).\n"
    "inventory: array of held item names (strings).\n"
    "room_key: a short stable string id for this room (e.g., 'white_house_exterior').\n"
    "notes: a 1-line debug summary of state change.\n"
    "Rules: Never break JSON. Prefer English unless the user speaks clearly Swedish.\n"
    "Limit scene to 18 words max. Limit say to 12 words max."
)

START_PROMPT = (
    "Start the game at the iconic White House exterior. "
    "No spoilers. No puzzles solved. Wait for player commands."
)

def parse_json_safe(s: str) -> dict:
    try:
        return json.loads(s)
    except Exception:
        # try to extract JSON block
        i = s.find("{"); j = s.rfind("}")
        if i >= 0 and j >= 0 and j > i:
            try: return json.loads(s[i:j+1])
            except: pass
    return {}

class GameEngine:
    def __init__(self):
        self.history = []
        self.state = {
            "room_key": "white_house_exterior",
            "inventory": []
        }

    def first_turn(self) -> dict:
        return self._ask_gpt(START_PROMPT)

    def turn(self, user_utterance: str) -> dict:
        prefix = "Player said (voice): "
        return self._ask_gpt(prefix + user_utterance)

    def _ask_gpt(self, user_msg: str) -> dict:
        if oai is None: return {}
        messages = [{"role": "system", "content": GAME_SYSTEM}]
        for m in self.history[-6:]:
            messages.append(m)
        messages.append({"role": "user", "content": user_msg})

        try:
            resp = oai.chat.completions.create(
                model=MODEL_CHAT,
                messages=messages,
                temperature=0.6,
                max_tokens=220
            )
            text = (resp.choices[0].message.content or "").strip()
            data = parse_json_safe(text)
            # update state
            if "room_key" in data: self.state["room_key"] = data["room_key"]
            if "inventory" in data: self.state["inventory"] = data["inventory"]
            # keep compact history
            self.history.append({"role": "assistant", "content": text})
            return data
        except Exception as e:
            print("GPT error:", e, file=sys.stderr)
            return {}

# ================== Main Loop ==================
class App:
    def __init__(self):
        self.ui = CRTWindow()
        self.voice = VoiceIO()
        self.img = ImageGen()
        self.game = GameEngine()
        self.running = True
        self.input_q = queue.Queue()

        # kick off first scene
        self.bootstrap()

        # background listener
        threading.Thread(target=self.listen_loop, daemon=True).start()

    def bootstrap(self):
        self.ui.clear()
        self.ui.draw_text("Booting…")
        data = self.game.first_turn()
        self.render_scene(data, speak=True)

    def render_scene(self, data: dict, speak: bool = False):
        if not data: return
        scene = data.get("scene", "A quiet place.")
        say = data.get("say", "Hello.")
        items = data.get("items", [])
        inv = data.get("inventory", [])
        room_key = data.get("room_key", self.game.state.get("room_key", "room"))

        # ensure icons exist
        for it in set(items + inv):
            self.img.gen_item_icon(it)

        # get room image
        pil = self.img.gen_room(room_key, scene) or Image.new("RGBA", GAME_RESOLUTION, (0,0,0,255))

        # draw
        self.ui.clear()
        self.ui.draw_room_image(pil)
        self.ui.draw_inventory(inv)
        self.ui.draw_text(scene)
        self.ui.draw_text("> (speak a command)…", color="#A0FFA0")
        self.ui.update()

        if speak:
            self.voice.speak(say)

    def listen_loop(self):
        while self.running:
            try:
                # don't record if speaking
                if self.voice.is_speaking:
                    time.sleep(0.05)
                    continue

                wav = self.voice.record_wav(REC_SECONDS)
                if not wav:
                    time.sleep(0.2)
                    continue

                txt = self.voice.transcribe(wav)
                if not txt:
                    # show soft hint, but avoid spam
                    self.ui.draw_text("…(no speech detected)")
                    self.ui.update()
                    continue

                # show command
                self.ui.draw_text(f"You: {txt}", color="#8cd9ff")
                self.ui.update()

                # ask game
                data = self.game.turn(txt)
                self.render_scene(data, speak=True)

            except Exception as e:
                print("Listen loop error:", e, file=sys.stderr)
                time.sleep(0.3)

    def run(self):
        while self.running:
            try:
                self.ui.update()
            except tk.TclError:
                self.running = False
                break

# ================ ENTRYPOINT =================
if __name__ == "__main__":
    print("Macintosh Voice Adventure — 512x342, pixel-art, voice I/O.")
    if oai is None:
        print("OpenAI client not available. Set OPENAI_API_KEY.", file=sys.stderr)
    app = App()
    app.run()
