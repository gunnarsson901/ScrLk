#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# vox_zork.py — Zork-like mini IF with voice control + CRT UI
import os, sys, time, math, random, threading, tempfile
import tkinter as tk
from tkinter import Canvas, END

# ====== Optional audio/AI deps ======
AI_OK = False
try:
    from openai import OpenAI
    AI_OK = bool(os.getenv("OPENAI_API_KEY"))
except Exception:
    OpenAI = None
    AI_OK = False

USE_AUDIO = True
try:
    import numpy as np
    import sounddevice as sd
    import soundfile as sf
    from scipy.io.wavfile import write as wav_write
except Exception:
    USE_AUDIO = False

# ====== Images (Pillow) ======
PIL_OK = True
try:
    from PIL import Image, ImageTk
except Exception:
    PIL_OK = False

# ====== Models / voices ======
MODEL_WHISPER = "whisper-1"
MODEL_TTS     = "tts-1"
VOICE_TTS     = "onyx"

REC_SR        = 16000
REC_SEC       = 4.0
REC_CH        = 1

# ====== CRT palette ======
CRT_BG   = "#0e1a0e"
CRT_FG   = "#c8ffb0"
CRT_DIM  = "#1a2d1a"
CRT_GRID = "#143014"

LOGW, LOGH = 800, 520  # logical canvas (scaled to screen)

# ====== ASSETS ======
BASE_DIR   = os.path.dirname(__file__)
ASSETS_DIR = os.path.join(BASE_DIR, "assets")
LOC_DIR    = os.path.join(ASSETS_DIR, "locations")
ITEM_DIR   = os.path.join(ASSETS_DIR, "items")

# Room → filbas
ROOM_IMAGE = {
    "clearing": "forest_clearing",
    "path":     "shadow_path",
    "arch":     "stone_arch",
    "cellar":   "damp_celler",   # stavat så i din struktur
    "vault":    "hidden_vault",
}

# Item → filbas (alias för lamp → lantern)
ITEM_IMAGE = {
    "lamp": "lantern",
    "note": "note",
    "key":  "key",
    "gem":  "gem",
}

# Logisk bildyta för location
LOC_W, LOC_H = 512, 342
LOC_X, LOC_Y = 270, 50   # övre vänstra hörn i logiska koordinater

# Inventory-fält
INV_H      = 80          # logisk höjd
INV_Y      = LOGH - INV_H
INV_PAD    = 10
ICON_SIZE  = 56          # logisk ikonstorlek

# ====== Mini Zork-like world ======
WORLD = {
    "clearing": {
        "name": "Forest Clearing",
        "desc": "You are in a quiet forest clearing. A narrow path leads north. A mossy hatch lies half-buried here.",
        "exits": {"north": "path"},
        "items": ["lamp", "note"],
        "props": {"hatch": {"locked": True, "open": False}},
    },
    "path": {
        "name": "Shadowed Path",
        "desc": "Tall trees crowd in. The path bends east toward a crumbling stone arch.",
        "exits": {"south": "clearing", "east": "arch"},
        "items": [],
        "props": {},
    },
    "arch": {
        "name": "Stone Arch",
        "desc": "An ancient arch frames a stairway descending into darkness.",
        "exits": {"west": "path", "down": "cellar"},
        "items": [],
        "props": {},
    },
    "cellar": {
        "name": "Damp Cellar",
        "desc": "A low cellar with dripping walls. A rusty door stands to the north.",
        "exits": {"up": "arch", "north": "vault"},
        "items": ["key"],
        "props": {"door": {"locked": True, "open": False}},
    },
    "vault": {
        "name": "Hidden Vault",
        "desc": "A cramped vault stuffed with old crates. Something glitters in the dust.",
        "exits": {"south": "cellar"},
        "items": ["gem"],
        "props": {},
    },
}

DIRS = {
    "n":"north","s":"south","e":"east","w":"west","u":"up","d":"down",
    "north":"north","south":"south","east":"east","west":"west","up":"up","down":"down",
    "go":"go","move":"go","walk":"go",
    "take":"take","get":"take","pick":"take","grab":"take",
    "drop":"drop","leave":"drop",
    "open":"open","unlock":"unlock","use":"use","read":"read","look":"look","examine":"look","inv":"inventory","i":"inventory","inventory":"inventory",
    "light":"light","lamp":"lamp","quit":"quit",
}

# ====== Game Engine ======
class Game:
    def __init__(self):
        self.room = "clearing"
        self.inv = []
        self.lamp_on = False
        self.running = True
        self.messages = []

    def look(self):
        r = WORLD[self.room]
        text = f"{r['name']}\n{r['desc']}"
        if r["items"]:
            text += "\nYou see: " + ", ".join(r["items"]) + "."
        exits = ", ".join(r["exits"].keys())
        if exits:
            text += f"\nExits: {exits}."
        return text

    def add_msg(self, s):
        self.messages.append(s)
        return s

    def move(self, direction):
        r = WORLD[self.room]
        if direction in r["exits"]:
            dest = r["exits"][direction]
            if self.room == "cellar" and direction == "north":
                door = WORLD["cellar"]["props"]["door"]
                if door["locked"]:
                    return self.add_msg("The rusty door is locked.")
                if not door["open"]:
                    return self.add_msg("The rusty door is closed.")
            self.room = dest
            if self.room == "cellar" and not self.lamp_on:
                return self.add_msg("It's very dark. Your lamp would help. " + self.look())
            return self.add_msg(self.look())
        else:
            return self.add_msg("You can't go that way.")

    def take(self, item):
        r = WORLD[self.room]
        if item in r["items"]:
            self.inv.append(item)
            r["items"].remove(item)
            return self.add_msg(f"Taken {item}.")
        return self.add_msg("You don't see that here.")

    def drop(self, item):
        if item in self.inv:
            self.inv.remove(item)
            WORLD[self.room]["items"].append(item)
            return self.add_msg(f"Dropped {item}.")
        return self.add_msg("You're not carrying that.")

    def open(self, what):
        r = WORLD[self.room]
        if what in ("hatch","mossy hatch") and self.room == "clearing":
            hatch = r["props"].get("hatch")
            if not hatch: return self.add_msg("There is no hatch.")
            if hatch["locked"]: return self.add_msg("The hatch won't budge. It seems locked.")
            if hatch["open"]:   return self.add_msg("It's already open.")
            hatch["open"] = True
            r["exits"]["down"] = "cellar"
            return self.add_msg("You pull the hatch open. A dark shaft descends.")
        if what in ("door","rusty door") and self.room == "cellar":
            door = r["props"].get("door")
            if not door: return self.add_msg("There is no door.")
            if door["locked"]: return self.add_msg("The door is locked.")
            if door["open"]:   return self.add_msg("It's already open.")
            door["open"] = True
            return self.add_msg("The rusty door creaks open.")
        return self.add_msg("It won't open.")

    def unlock(self, what):
        if "key" not in self.inv:
            return self.add_msg("You don't have a key.")
        if what in ("hatch","mossy hatch") and self.room == "clearing":
            hatch = WORLD["clearing"]["props"]["hatch"]
            if not hatch["locked"]: return self.add_msg("It's already unlocked.")
            hatch["locked"] = False
            return self.add_msg("You unlock the hatch.")
        if what in ("door","rusty door") and self.room == "cellar":
            door = WORLD["cellar"]["props"]["door"]
            if not door["locked"]: return self.add_msg("It's already unlocked.")
            door["locked"] = False
            return self.add_msg("You unlock the door.")
        return self.add_msg("That doesn't seem to need unlocking.")

    def use(self, what):
        if what == "lamp":
            return self.light()
        return self.add_msg("How do you want to use that?")

    def read(self, what):
        if what == "note" and self.room == "clearing" and "note" in WORLD["clearing"]["items"]:
            return self.add_msg("The note says: 'LIGHT HELPS BELOW. THE KEY IS IN THE DAMP.'")
        if what == "note" and "note" in self.inv:
            return self.add_msg("The note says: 'LIGHT HELPS BELOW. THE KEY IS IN THE DAMP.'")
        return self.add_msg("There's nothing to read.")

    def light(self):
        if "lamp" in self.inv:
            self.lamp_on = True
            return self.add_msg("You switch on the brass lamp. The gloom retreats.")
        return self.add_msg("You don't have a lamp.")

    def inventory(self):
        if not self.inv: return self.add_msg("You are empty-handed.")
        return self.add_msg("You carry: " + ", ".join(self.inv) + ".")

    def parse(self, raw):
        s = raw.strip().lower()
        if not s: return ""
        if s in ("quit","exit"): self.running = False; return "Goodbye."
        if s in ("look","l"):    return self.look()
        if s in ("inventory","i","inv"): return self.inventory()

        toks = [DIRS.get(t, t) for t in s.split()]
        if not toks: return "?"

        if toks[0] in ("north","south","east","west","up","down"):
            return self.move(toks[0])
        if toks[0] == "go" and len(toks) >= 2:
            return self.move(toks[1])
        if toks[0] == "take" and len(toks) >= 2:
            return self.take(toks[-1])
        if toks[0] == "drop" and len(toks) >= 2:
            return self.drop(toks[-1])
        if toks[0] == "open" and len(toks) >= 2:
            return self.open(" ".join(toks[1:]))
        if toks[0] == "unlock" and len(toks) >= 2:
            return self.unlock(" ".join(toks[1:]))
        if toks[0] == "use" and len(toks) >= 2:
            return self.use(toks[-1])
        if toks[0] == "read" and len(toks) >= 2:
            return self.read(toks[-1])
        if toks[0] == "light":
            return self.light()
        return self.add_msg("I don't understand that.")

# ====== App (UI + Audio + AI) ======
class VoxZorkApp:
    def __init__(self):
        self.client = OpenAI() if AI_OK else None
        self.game = Game()
        self.is_speaking = False
        self.rec_lock = threading.Lock()

        # image caches
        self._img_cache = {}      # path -> PIL.Image
        self._tk_cache  = {}      # (path,w,h) -> ImageTk.PhotoImage
        self._sprite_refs = []    # keep references

        self.root = tk.Tk()
        self.root.title("Zork-like (Voice) – CRT")
        self.root.configure(bg=CRT_BG)
        self.root.attributes("-fullscreen", True)
        self.root.bind("<Escape>", lambda e: self.quit())
        self.root.bind("<Return>", lambda e: self.send_text())
        self.root.bind("<v>",      lambda e: self.push_to_talk())
        self.root.bind("<V>",      lambda e: self.push_to_talk())

        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        scale = min(sw/LOGW, (sh*0.92)/LOGH)
        self.scale = scale
        cw, ch = int(LOGW*scale), int(LOGH*scale)

        top = tk.Frame(self.root, bg=CRT_BG); top.pack(expand=True, fill="both")
        self.canvas = Canvas(top, width=cw, height=ch, bg=CRT_BG, highlightthickness=0)
        self.canvas.grid(row=0, column=0, padx=12, pady=12, sticky="nsew")

        right = tk.Frame(top, bg=CRT_BG)
        right.grid(row=0, column=1, sticky="ns", pady=12, padx=(0,12))
        top.columnconfigure(0, weight=1)
        top.rowconfigure(0, weight=1)

        self.log = tk.Text(right, width=44, height=28, bg=CRT_BG, fg=CRT_FG,
                           insertbackground=CRT_FG, bd=0, highlightthickness=1,
                           highlightbackground=CRT_DIM, wrap="word")
        self.log.pack(pady=(0,8))
        self.entry = tk.Entry(right, bg=CRT_BG, fg=CRT_FG, insertbackground=CRT_FG,
                              highlightthickness=1, highlightbackground=CRT_DIM)
        self.entry.pack(fill="x")
        self.entry.insert(0, "Type here… or press V to speak")

        btns = tk.Frame(right, bg=CRT_BG); btns.pack(pady=8, fill="x")
        tk.Button(btns, text="Look",   command=lambda: self.do_cmd("look")).pack(side="left", padx=2)
        tk.Button(btns, text="Inv",    command=lambda: self.do_cmd("inventory")).pack(side="left", padx=2)
        tk.Button(btns, text="Speak",  command=self.push_to_talk).pack(side="left", padx=2)

        self.status = tk.Label(right, text="Ready.", bg=CRT_BG, fg=CRT_FG)
        self.status.pack(anchor="w", pady=(8,0))

        self.draw_world()
        self.tell(self.game.look(), speak=True)

        self.root.after(100, self.redraw_loop)

    # ===== UI helpers =====
    def fx(self, x): return int(x*self.scale)
    def fy(self, y): return int(y*self.scale)

    def log_write(self, s):
        self.log.insert(END, s + "\n\n")
        self.log.see(END)

    def set_status(self, s):
        self.status.config(text=s)

    # ===== Image loading =====
    def _load_image(self, path):
        if not PIL_OK:
            return None
        if path in self._img_cache:
            return self._img_cache[path]
        try:
            img = Image.open(path).convert("RGBA")
            self._img_cache[path] = img
            return img
        except Exception:
            return None

    def _get_tk_image(self, path, w, h):
        key = (path, w, h)
        if key in self._tk_cache:
            return self._tk_cache[key]
        pil = self._load_image(path)
        if pil is None:
            return None
        try:
            resized = pil.resize((max(1,w), max(1,h)), Image.LANCZOS)
        except Exception:
            resized = pil
        tkimg = ImageTk.PhotoImage(resized)
        self._tk_cache[key] = tkimg
        return tkimg

    # ===== World drawing =====
    def draw_world(self):
        c = self.canvas
        c.delete("all")
        self._sprite_refs.clear()

        # platsbild
        self.draw_location_image()

        # CRT-scanlines
        for y in range(0, LOGH, 4):
            c.create_line(self.fx(0), self.fy(y), self.fx(LOGW), self.fy(y), fill=CRT_GRID)

        # ansikte
        self.draw_face()

        # inventory
        self.draw_inventory_bar()

        # rumsnamn
        rname = WORLD[self.game.room]["name"]
        c.create_text(self.fx(LOC_X + LOC_W//2), self.fy(LOC_Y - 20),
                      text=rname, fill=CRT_FG, font=("Courier", int(16*self.scale)))

    def draw_location_image(self):
        c = self.canvas
        box_w, box_h = LOC_W, LOC_H
        x0, y0 = LOC_X, LOC_Y

        # bakgrundsram
        lw = max(1, int(2*self.scale))
        c.create_rectangle(self.fx(x0-6), self.fy(y0-6),
                           self.fx(x0+box_w+6), self.fy(y0+box_h+6),
                           outline=CRT_DIM, width=lw)

        # filväg
        base = ROOM_IMAGE.get(self.game.room, None)
        path = os.path.join(LOC_DIR, f"{base}.png") if base else None

        if PIL_OK and path and os.path.exists(path):
            tkimg = self._get_tk_image(path, self.fx(box_w), self.fy(box_h))
            if tkimg:
                img_id = c.create_image(self.fx(x0), self.fy(y0), image=tkimg, anchor="nw")
                self._sprite_refs.append(tkimg)
                return

        # fallback
        c.create_rectangle(self.fx(x0), self.fy(y0),
                           self.fx(x0+box_w), self.fy(y0+box_h),
                           outline=CRT_FG, width=lw)
        c.create_text(self.fx(x0+box_w/2), self.fy(y0+box_h/2),
                      text="No image", fill=CRT_FG, font=("Courier", int(14*self.scale)))

    def draw_inventory_bar(self):
        c = self.canvas
        # bakgrund
        c.create_rectangle(self.fx(0), self.fy(INV_Y), self.fx(LOGW), self.fy(LOGH),
                           outline=CRT_DIM, fill=CRT_BG, width=1)

        # titel
        c.create_text(self.fx(12), self.fy(INV_Y + 16),
                      text="Inventory:", anchor="w",
                      fill=CRT_FG, font=("Courier", int(12*self.scale)))

        if not self.game.inv:
            c.create_text(self.fx(120), self.fy(INV_Y + 18),
                          text="(empty)", anchor="w",
                          fill=CRT_DIM, font=("Courier", int(12*self.scale)))
            return

        # ikoner
        x = 120
        for item in self.game.inv:
            base = ITEM_IMAGE.get(item, item)
            path = os.path.join(ITEM_DIR, f"{base}.png")
            size_px = self.fx(ICON_SIZE), self.fx(ICON_SIZE)  # kvadrat
            if PIL_OK and os.path.exists(path):
                tkimg = self._get_tk_image(path, *size_px)
                if tkimg:
                    c.create_image(self.fx(x), self.fy(INV_Y + 10), image=tkimg, anchor="nw")
                    self._sprite_refs.append(tkimg)
                else:
                    self._draw_icon_placeholder(x, INV_Y + 10, item)
            else:
                self._draw_icon_placeholder(x, INV_Y + 10, item)
            x += ICON_SIZE + INV_PAD

    def _draw_icon_placeholder(self, lx, ly, label):
        c = self.canvas
        lw = max(1, int(1*self.scale))
        c.create_rectangle(self.fx(lx), self.fy(ly),
                           self.fx(lx+ICON_SIZE), self.fy(ly+ICON_SIZE),
                           outline=CRT_FG, width=lw)
        c.create_text(self.fx(lx+ICON_SIZE/2), self.fy(ly+ICON_SIZE/2),
                      text=label[:4], fill=CRT_FG, font=("Courier", int(10*self.scale)))

    def draw_face(self):
        c = self.canvas
        box = (40, 60, 240, 160)
        x0,y0,x1,y1 = box
        lw = max(1, int(2*self.scale))
        c.create_rectangle(self.fx(x0), self.fy(y0), self.fx(x1), self.fy(y1),
                           outline=CRT_FG, width=lw)
        cx = (x0+x1)/2
        cy = (y0+y1)/2
        eye_dx = 28
        eye_h  = 14
        blink = (int(time.time()*2) % 6 == 0)
        if blink:
            c.create_line(self.fx(cx-eye_dx-6), self.fy(cy), self.fx(cx-eye_dx+6), self.fy(cy),
                          fill=CRT_FG, width=lw)
            c.create_line(self.fx(cx+eye_dx-6), self.fy(cy), self.fx(cx+eye_dx+6), self.fy(cy),
                          fill=CRT_FG, width=lw)
        else:
            c.create_rectangle(self.fx(cx-eye_dx-3), self.fy(cy-eye_h), self.fy(cy+eye_h),
                               self.fx(cx-eye_dx+3), outline=CRT_FG)  # safeguard if swapped
            c.create_rectangle(self.fx(cx+eye_dx-3), self.fy(cy-eye_h), self.fx(cx+eye_dx+3), self.fy(cy+eye_h),
                               outline=CRT_FG, fill=CRT_FG, width=1)
            # fix first rectangle args (tk requires x0,y0,x1,y1); re-draw properly:
            c.create_rectangle(self.fx(cx-eye_dx-3), self.fy(cy-eye_h), self.fx(cx-eye_dx+3), self.fy(cy+eye_h),
                               outline=CRT_FG, fill=CRT_FG, width=1)
        # nose ┘
        c.create_line(self.fx(cx), self.fy(cy-8), self.fx(cx), self.fy(cy+14), fill=CRT_FG, width=lw)
        c.create_line(self.fx(cx), self.fy(cy+14), self.fx(cx+10), self.fy(cy+14), fill=CRT_FG, width=lw)
        # smile
        c.create_line(self.fx(cx-24), self.fy(cy+26), self.fx(cx), self.fy(cy+34), fill=CRT_FG, width=lw)
        c.create_line(self.fx(cx), self.fy(cy+34), self.fx(cx+24), self.fy(cy+26), fill=CRT_FG, width=lw)

    def redraw_loop(self):
        self.draw_world()
        self.root.after(250, self.redraw_loop)

    # ===== TTS =====
    def speak(self, text):
        if not text or not AI_OK or not USE_AUDIO:
            return
        def _worker():
            self.is_speaking = True
            try:
                res = self.client.audio.speech.create(
                    model=MODEL_TTS, voice=VOICE_TTS, input=text, response_format="wav"
                )
                try:
                    audio_bytes = res.read()
                except AttributeError:
                    audio_bytes = getattr(res, "content", None)
                    if audio_bytes is None:
                        audio_bytes = bytes(res)
                tmp = os.path.join(tempfile.gettempdir(), f"tts_{int(time.time()*1000)}.wav")
                with open(tmp,"wb") as f: f.write(audio_bytes)
                data, sr = sf.read(tmp, dtype="float32", always_2d=False)
                sd.play(data, sr); sd.wait()
            except Exception:
                pass
            finally:
                self.is_speaking = False
        threading.Thread(target=_worker, daemon=True).start()

    # ===== STT =====
    def push_to_talk(self):
        if not USE_AUDIO or not AI_OK:
            self.set_status("Voice off (missing deps or API key).")
            return
        if self.is_speaking:
            self.set_status("Speaking… wait.")
            return
        if not hasattr(self, "rec_lock"):
            self.rec_lock = threading.Lock()
        if not self.rec_lock.acquire(blocking=False):
            return
        self.set_status("Listening… (~4s)")
        threading.Thread(target=self._record_and_transcribe, daemon=True).start()

    def _record_and_transcribe(self):
        try:
            frames = int(REC_SR * REC_SEC)
            audio = sd.rec(frames, samplerate=REC_SR, channels=REC_CH, dtype="float32")
            sd.wait()
            peak = float(np.max(np.abs(audio))) if audio.size else 0.0
            if peak > 0: audio = audio / max(1.0, peak)
            from scipy.io.wavfile import write as wav_write
            tmp_wav = os.path.join(tempfile.gettempdir(), f"stt_{int(time.time()*1000)}.wav")
            wav_write(tmp_wav, REC_SR, (audio * 32767).astype(np.int16))
            text = self._transcribe(tmp_wav)
            if text:
                self.entry.delete(0, END)
                self.entry.insert(0, text)
                self.send_text()
            else:
                self.set_status("…no speech detected.")
        except Exception:
            self.set_status("STT error.")
        finally:
            self.rec_lock.release()

    def _transcribe(self, path):
        try:
            with open(path, "rb") as f:
                tr = self.client.audio.transcriptions.create(model=MODEL_WHISPER, file=f)
            txt = (tr.text or "").strip()
            return txt
        except Exception:
            return None
        finally:
            try: os.remove(path)
            except Exception: pass

    # ===== Command flow =====
    def do_cmd(self, cmd):
        if not self.game.running:
            self.tell("The session has ended. Press ESC to quit.", speak=False)
            return
        self.tell(f"> {cmd}", speak=False)
        out = self.game.parse(cmd)
        # redraw direkt så platsbild och inventory uppdateras
        self.draw_world()
        self.tell(out, speak=True if out else False)

    def send_text(self):
        s = self.entry.get().strip()
        if not s: return
        self.entry.delete(0, END)
        self.do_cmd(s)

    def tell(self, text, speak=False):
        self.log_write(text)
        if speak and not self.is_speaking:
            self.speak(text)
        self.set_status("Ready. Press V to speak.")

    def quit(self):
        try: self.root.destroy()
        except Exception: pass
        sys.exit(0)

    def run(self):
        if not PIL_OK:
            self.log_write("Note: Pillow ej installerat. Installera: pip install pillow")
        self.root.mainloop()

if __name__ == "__main__":
    if not AI_OK:
        print("WARNING: OPENAI_API_KEY not set -> voice features limited to keyboard.")
    if not USE_AUDIO:
        print("WARNING: Missing audio deps. Install: pip install openai sounddevice soundfile numpy scipy")
    VoxZorkApp().run()
