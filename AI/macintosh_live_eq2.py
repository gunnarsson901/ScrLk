#!/usr/bin/env python3
import os, time, math, random, tempfile, subprocess, threading, traceback, sys
import tkinter as tk
from tkinter import Canvas
import speech_recognition as sr
from openai import OpenAI

# ------------- CONFIG -------------
MIC_DEVICE_INDEX = 1          # your Sandberg mic index
LANG = "sv-SE"                # speech recognition language
LLM_MODEL = "gpt-4o-mini"
TTS_MODEL = "gpt-4o-mini-tts"
TTS_VOICE = "alloy"           # try: alloy, verse, etc.
INTRO = ("Hej. Jag heter Macintosh. Jag jobbar för E Q två. "
         "Jag finns här med dig och lyssnar. Hur mår du just nu?")
SYSTEM_PROMPT = (
    "Du är Macintosh, en empatisk stöddator för EQ2. "
    "Svara kort, varmt och naturligt på svenska, 1–2 meningar."
)

# ------------- OPENAI + STT -------------
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
rec = sr.Recognizer()
rec.energy_threshold = 300
rec.dynamic_energy_threshold = True

def debug(msg): print(msg, flush=True)

def listen_once(timeout=5, phrase_limit=8):
    try:
        with sr.Microphone(device_index=MIC_DEVICE_INDEX) as source:
            rec.adjust_for_ambient_noise(source, duration=0.2)
            debug("[MIC] Lyssnar...")
            audio = rec.listen(source, timeout=timeout, phrase_time_limit=phrase_limit)
        debug("[STT] tolkar...")
        text = rec.recognize_google(audio, language=LANG)
        debug(f"[STT] Du sa: {text}")
        return text
    except sr.WaitTimeoutError:
        return None
    except sr.UnknownValueError:
        return None
    except Exception as e:
        debug(f"[STT FEL] {e}")
        return None

def ask_gpt(user_text):
    try:
        r = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role":"system", "content": SYSTEM_PROMPT},
                {"role":"user", "content": user_text}
            ],
            temperature=0.7, max_tokens=120
        )
        ans = r.choices[0].message.content.strip()
        debug(f"[GPT] {ans}")
        return ans
    except Exception as e:
        debug(f"[GPT FEL] {e}")
        traceback.print_exc()
        return "Jag hade lite svårt att tänka nyss. Kan du säga det igen?"

def play_mp3(path):
    try:
        subprocess.run(["mpg123","-q",path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:
        debug(f"[PLAY FEL] {e}")

def speak(text):
    # Try OpenAI TTS -> mp3 -> play; else fall back to espeak
    debug(f"[TTS] {text}")
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
        mp3_path = tmp.name
    try:
        speech = client.audio.speech.create(model=TTS_MODEL, voice=TTS_VOICE, input=text)
        # support different client payload shapes
        if hasattr(speech, "read"):
            audio_bytes = speech.read()
        elif hasattr(speech, "content"):
            audio_bytes = speech.content
        else:
            audio_bytes = bytes(speech)
        with open(mp3_path, "wb") as f:
            f.write(audio_bytes)
        play_mp3(mp3_path)
    except Exception as e:
        debug(f"[TTS FEL] {e}")
        subprocess.run(["espeak","-v","sv","-s","160",text],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

# ------------- TK: MAC FACE -------------
class MacFace:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Macintosh EQ2")
        self.root.attributes("-fullscreen", True)
        self.root.configure(bg="#111")
        self.root.bind("<Escape>", lambda e: self.quit())

        self.w = self.root.winfo_screenwidth()
        self.h = self.root.winfo_screenheight()

        self.canvas = Canvas(self.root, width=self.w, height=self.h, bg="#111", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)

        # animation state
        self.eye_offset_x = 0
        self.eye_offset_y = 0
        self.head_tilt = 0
        self.mouth_open = 0.0
        self.target_mouth = 0.0
        self.is_speaking = False
        self.is_listening = False
        self.is_smiling = 0.0     # 0..1
        self.blink_progress = 0.0 # 0..1 (1 = eyes closed)
        self.wink_left = False
        self.next_blink_t = time.time() + random.uniform(2.0, 6.0)
        self.next_wink_t  = time.time() + random.uniform(8.0, 16.0)

        # mouse look
        self.root.bind("<Motion>", self.track_mouse)

        self._run = True
        self.animate()

    def quit(self):
        self._run = False
        try: self.root.destroy()
        except: pass
        sys.exit(0)

    def track_mouse(self, ev):
        cx, cy = self.w/2, self.h*0.42
        dx = (ev.x - cx)/self.w
        dy = (ev.y - cy)/self.h
        self.eye_offset_x = max(-12, min(12, dx*500))
        self.eye_offset_y = max(-8,  min(8,  dy*300))
        self.head_tilt    = max(-4,  min(4,  dx*20))

    def draw(self):
        self.canvas.delete("all")
        scale = min(self.w/1000, self.h/700) * 1.35  # bigger
        base_x, base_y = self.w/2, self.h/2
        tilt = self.head_tilt * scale
        w, h = 170*scale, 250*scale

        # shadow
        self.canvas.create_polygon(
            [base_x - w, base_y + h*0.65,
             base_x + w, base_y + h*0.65,
             base_x + w*0.85, base_y + h*0.8,
             base_x - w*0.85, base_y + h*0.8],
            fill="#0a0a0a", outline="", smooth=True)

        # body
        front="#e8dcc8"; side="#cdbb9b"; line="#8b7355"
        back = [base_x - w*0.75 + tilt, base_y - h,
                base_x + w*0.75 + tilt, base_y - h,
                base_x + w + tilt,      base_y + h*0.45,
                base_x - w + tilt,      base_y + h*0.45]
        self.canvas.create_polygon(back, fill=side, outline=line, width=int(2*scale))

        self.canvas.create_rectangle(base_x-w, base_y-h, base_x+w, base_y+h*0.45,
                                     fill=front, outline=line, width=int(3*scale))

        # bezel
        screen_w = w*0.68
        screen_h = screen_w*(342/512)
        self.canvas.create_rectangle(base_x-screen_w, base_y-h*0.78,
                                     base_x+screen_w, base_y-h*0.78+screen_h,
                                     fill="#111", outline="#000", width=int(3*scale))

        # inner screen tint: green when listening, warm when idle, teal when speaking
        tint = "#ccffcc" if self.is_listening else ("#ffd9b3" if not self.is_speaking else "#b3ffec")
        self.canvas.create_rectangle(base_x-screen_w*0.88, base_y-h*0.71,
                                     base_x+screen_w*0.88, base_y-h*0.78+screen_h*0.88,
                                     fill=tint, outline="#666", width=int(2*scale))

        # face (eyes/mouth)
        eye_y = base_y - h*0.48
        eye_size = max(10, int(14*scale))
        left_x  = base_x - screen_w*0.36 + self.eye_offset_x*scale
        right_x = base_x + screen_w*0.36 + self.eye_offset_x*scale
        eofy    = self.eye_offset_y*scale

        # blink/wink scales
        blink = self.blink_progress
        def eye_rect(cx, cy, wink=False):
            if blink > 0.0 or wink:
                # draw a slit (line) when closed
                self.canvas.create_line(cx - eye_size, cy+eofy,
                                        cx + eye_size, cy+eofy,
                                        fill="#000", width=int(3*scale))
            else:
                self.canvas.create_oval(cx-eye_size, cy+eofy-eye_size,
                                        cx+eye_size, cy+eofy+eye_size,
                                        fill="#000", outline="")

        # left eye (wink_left overrides)
        eye_rect(left_x, eye_y, wink=self.wink_left)
        # right eye winks only when wink_left is False
        eye_rect(right_x, eye_y, wink=False if self.wink_left else False)

        # mouth (smile curve + open)
        mouth_y = base_y - h*0.26
        mouth_w = screen_w*0.48
        mouth_h = 26*scale + self.mouth_open*22*scale
        # smile factor arcs higher when smiling
        smile = self.is_smiling
        arc_extent = -180 + smile*30  # -180(flat) to -150(smiley)
        self.canvas.create_arc(base_x - mouth_w, mouth_y,
                               base_x + mouth_w, mouth_y + mouth_h,
                               start=0, extent=arc_extent,
                               style="arc", outline="#000", width=int(4*scale))

        # base
        self.canvas.create_rectangle(base_x - w*0.85, base_y + h*0.45,
                                     base_x + w*0.85, base_y + h*0.56,
                                     fill=side, outline=line, width=int(2*scale))

    def animate(self):
        # mouth easing
        if abs(self.mouth_open - self.target_mouth) > 0.01:
            self.mouth_open += (self.target_mouth - self.mouth_open) * 0.3
        self.target_mouth = (0.5 + 0.5*math.sin(time.time()*9)) if self.is_speaking else 0.0

        # idle smile relax
        if not self.is_speaking and not self.is_listening:
            self.is_smiling = max(0.0, self.is_smiling - 0.02)

        # blinks
        now = time.time()
        if now >= self.next_blink_t and self.blink_progress <= 0.0:
            self.blink_progress = 1.0
            self.next_blink_t = now + random.uniform(3.0, 7.0)
        if self.blink_progress > 0.0:
            self.blink_progress -= 0.15
            if self.blink_progress < 0: self.blink_progress = 0.0

        # random wink (left eye)
        if now >= self.next_wink_t and not self.is_speaking and not self.is_listening:
            self.wink_left = True
            self.root.after(160, lambda: setattr(self, "wink_left", False))
            self.next_wink_t = now + random.uniform(8.0, 16.0)

        self.draw()
        if self._run:
            self.root.after(50, self.animate)

# ------------- ORCHESTRATION -------------
class App:
    def __init__(self):
        self.face = MacFace()
        # start conversation in background
        threading.Thread(target=self.convo_loop, daemon=True).start()
        # intro speak (animate mouth while speaking)
        threading.Thread(target=self.say_with_anim, args=(INTRO, True), daemon=True).start()

    def say_with_anim(self, text, smile=False):
        self.face.is_listening = False
        self.face.is_speaking = True
        if smile: self.face.is_smiling = 1.0
        speak(text)
        self.face.is_speaking = False
        if smile: self.face.is_smiling = 0.5

    def convo_loop(self):
        while True:
            # 1) listen
            self.face.is_listening = True
            user_text = listen_once(timeout=6, phrase_limit=8)
            self.face.is_listening = False

            if not user_text:
                continue

            # 2) think
            self.face.is_smiling = 0.3
            reply = ask_gpt(user_text)

            # 3) speak with mouth anim
            self.say_with_anim(reply, smile=True)

            # small gap so it doesn't self-hear
            time.sleep(0.8)

    def run(self):
        self.face.root.mainloop()

if __name__ == "__main__":
    App().run()
