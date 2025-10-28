import os
import math
import time
import threading
import subprocess
import sys
import random
import tkinter as tk
from tkinter import Canvas

import speech_recognition as sr
from openai import OpenAI


#####################################
# CONFIG
#####################################

# Which ALSA device to listen to.
# From your list:
#   0 USB PnP Sound Device: Audio (hw:0,0)
#   1 Sandberg 126-40: USB Audio (hw:1,0)   <-- this one worked
MIC_DEVICE_INDEX = 1

# Language code for STT
# 'sv-SE' to understand Swedish, 'en-US' for English
STT_LANG = 'sv-SE'

# What language to speak with espeak
TTS_VOICE = 'sv'   # try 'sv' for Swedish, 'en' for English
TTS_WPM = '160'

# Persona / system identity
SYSTEM_PERSONA = (
    "Du är Macintosh, en emotionell stöddator från EQ2 Support. "
    "Du är lugn, snäll, omtänksam och trygg. "
    "Du hjälper användaren att må bra, svarar enkelt och varmt, "
    "och du låter som en personlig vän, inte en robot. "
    "Prata kort och mjukt."
)

#####################################
# HELPERS
#####################################

def speak_tts_async(text, after_done=None):
    """
    Say `text` using espeak (or 'say' on macOS fallback).
    Non-blocking.
    after_done: optional fn() to call on mainthread after speaking
    """
    def _worker():
        # Try espeak (Linux / Pi)
        try:
            subprocess.run(
                ['espeak', '-v', TTS_VOICE, '-s', TTS_WPM, text],
                stderr=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL
            )
        except FileNotFoundError:
            # Try 'say' (macOS)
            try:
                subprocess.run(
                    ['say', text],
                    stderr=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL
                )
            except Exception:
                pass
        finally:
            if after_done:
                after_done()

    threading.Thread(target=_worker, daemon=True).start()


#####################################
# MAIN CLASS
#####################################

class EQ2MacintoshAI:
    def __init__(self):
        print("[BOOT] EQ2MacintoshAI init start")

        # --- state ---
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.shutting_down = False
        self.is_listening_loop_running = False
        self.is_speaking = False

        # emotion / face state
        self.mood = "boot"        # boot -> listening -> thinking -> speaking -> happy/neutral
        self.last_blink_time = time.time()
        self.blink_active = False
        self.wink_active = False
        self.blink_duration = 0.12   # seconds eyes closed
        self.wink_duration = 0.18
        self.expression_smile = 0.0   # 0.0 neutral mouth, 1.0 big smile
        self.mouth_open_amount = 0.0  # talking animation
        self.target_mouth_open = 0.0

        # conversation memory we'll send to OpenAI
        self.chat_history = [
            {"role": "system", "content": SYSTEM_PERSONA}
        ]

        # speech recognizer
        self.recognizer = sr.Recognizer()
        # more tolerant to quiet rooms
        self.recognizer.dynamic_energy_threshold = True
        # you can tune this if it mis-detects silence
        self.recognizer.pause_threshold = 0.6

        # --- tkinter setup ---
        self.root = tk.Tk()
        self.root.title("EQ2 Support Macintosh")
        # fullscreen retro terminal vibe
        self.root.attributes('-fullscreen', True)
        self.root.configure(bg='#1a1a1a')

        # ESC quits
        self.root.bind('<Escape>', lambda e: self.quit_app())
        # Mouse move affects eye direction
        self.root.bind('<Motion>', self.track_mouse)

        # screen size
        self.screen_w = self.root.winfo_screenwidth()
        self.screen_h = self.root.winfo_screenheight()

        # eye tracking
        self.mouse_x = self.screen_w // 2
        self.mouse_y = self.screen_h // 2
        self.eye_offset_x = 0
        self.eye_offset_y = 0
        self.head_tilt = 0

        # layout
        main_frame = tk.Frame(self.root, bg='#1a1a1a')
        main_frame.pack(expand=True, fill='both')

        canvas_h = int(self.screen_h * 0.7)
        canvas_w = self.screen_w
        self.canvas = Canvas(
            main_frame,
            width=canvas_w,
            height=canvas_h,
            bg='#1a1a1a',
            highlightthickness=0
        )
        self.canvas.pack()
        self.canvas_w = canvas_w
        self.canvas_h = canvas_h

        # status label (what user said / what Mac says)
        self.status_label = tk.Label(
            main_frame,
            text="Startar EQ2 Macintosh...",
            font=("Courier", 18),
            bg='#1a1a1a',
            fg='#00ff00',
            justify='left',
            anchor='w'
        )
        self.status_label.pack(pady=10, fill='x')

        # small help text
        self.help_label = tk.Label(
            main_frame,
            text="Jag lyssnar automatiskt. ESC = stäng av.",
            font=("Courier", 12),
            bg='#1a1a1a',
            fg='#666666'
        )
        self.help_label.pack(pady=4)

        # draw once
        self.draw_macintosh_face()

        # start animation loop
        self.root.after(50, self.animation_loop)

        # greet user with intro animation + voice
        self.root.after(500, self.start_intro_sequence)

        # start mic listener after short delay
        self.root.after(2000, self.start_listening_loop_once)

        print("[BOOT] init complete")

    ##################################################
    # UI SAFE HELPERS
    ##################################################

    def set_status(self, text):
        if not self.shutting_down:
            self.status_label.config(text=text)

    ##################################################
    # INTRO SEQUENCE
    ##################################################

    def start_intro_sequence(self):
        # Big smile, maybe wink once, then speak greeting.
        print("[INTRO] intro sequence")
        self.mood = "happy"
        self.expression_smile = 1.0
        self.wink_now()  # quick friendly wink

        greeting_text = (
            "Hej. Jag heter Macintosh. "
            "Jag är en emotionell stöddator från EQ2. "
            "Hur mår du idag?"
        )

        self.set_status("Macintosh: " + greeting_text)

        def after_voice():
            # After talking we go to listening mode
            self.is_speaking = False
            self.mood = "listening"
            self.expression_smile = 0.4  # keep gentle smile

        # mark speaking (so mouth anim moves)
        self.is_speaking = True
        speak_tts_async(greeting_text, after_done=lambda: self.root.after(0, after_voice))

    ##################################################
    # MOUSE TRACK + FACE DRAW
    ##################################################

    def track_mouse(self, event):
        self.mouse_x = event.x
        self.mouse_y = event.y

        cx = self.canvas_w / 2
        cy = self.canvas_h * 0.4
        dx = (self.mouse_x - cx) / self.canvas_w
        dy = (self.mouse_y - cy) / self.canvas_h

        self.eye_offset_x = max(-12, min(12, dx * 500))
        self.eye_offset_y = max(-8, min(8, dy * 300))
        self.head_tilt = max(-4, min(4, dx * 20))

    def draw_macintosh_face(self):
        self.canvas.delete("all")

        # scale against 1000x700 base
        scale = min(self.canvas_w / 1000.0, self.canvas_h / 700.0)
        base_x = self.canvas_w / 2
        base_y = self.canvas_h / 2

        tilt = self.head_tilt * scale
        w = 150 * scale
        h = 220 * scale

        # shadow under Mac
        shadow = [
            base_x - w, base_y + h * 0.6,
            base_x + w, base_y + h * 0.6,
            base_x + w * 0.85, base_y + h * 0.75,
            base_x - w * 0.85, base_y + h * 0.75
        ]
        self.canvas.create_polygon(
            shadow,
            fill='#0a0a0a',
            outline='',
            smooth=True
        )

        body_front = '#e8dcc8'
        body_side  = '#c4b8a0'
        outline_col = '#8b7355'

        # angled back panel
        back_poly = [
            base_x - w * 0.75 + tilt, base_y - h,
            base_x + w * 0.75 + tilt, base_y - h,
            base_x + w + tilt,        base_y + h * 0.4,
            base_x - w + tilt,        base_y + h * 0.4
        ]
        self.canvas.create_polygon(
            back_poly,
            fill=body_side,
            outline=outline_col,
            width=int(2 * scale)
        )

        # front block
        self.canvas.create_rectangle(
            base_x - w, base_y - h,
            base_x + w, base_y + h * 0.4,
            fill=body_front,
            outline=outline_col,
            width=int(3 * scale)
        )

        # screen bezel (Classic Mac 512x342 ratio)
        screen_w = w * 0.65
        screen_h = screen_w * (342.0 / 512.0)

        self.canvas.create_rectangle(
            base_x - screen_w, base_y - h * 0.75,
            base_x + screen_w, base_y - h * 0.75 + screen_h,
            fill='#1a1a1a',
            outline='#000000',
            width=int(3 * scale)
        )

        # "CRT glow" color depends on mood
        if self.mood == "listening":
            screen_color = '#d0ffd0'  # soft green
        elif self.mood == "thinking":
            screen_color = '#fff5a8'  # yellow-ish when thinking
        elif self.mood == "speaking":
            screen_color = '#ccddff'  # soft blue when talking
        elif self.mood == "happy":
            screen_color = '#ccffcc'  # bright green
        else:
            screen_color = '#bbffbb'  # default gentle green

        self.canvas.create_rectangle(
            base_x - screen_w * 0.88, base_y - h * 0.68,
            base_x + screen_w * 0.88, base_y - h * 0.75 + screen_h * 0.88,
            fill=screen_color,
            outline='#888888',
            width=int(2 * scale)
        )

        # face coordinates
        eye_y = base_y - h * 0.45
        eye_size = max(10, int(12 * scale))

        # mouth baseline
        mouth_y = base_y - h * 0.25
        mouth_w = screen_w * 0.45

        # draw eyes
        # logic: if blink_active -> eyes closed (thin line)
        # if wink_active -> close right eye only
        # else: normal round eyes that track mouse

        # left eye center
        left_eye_x = base_x - screen_w * 0.35 + self.eye_offset_x * scale
        left_eye_y = eye_y + self.eye_offset_y * scale

        # right eye center
        right_eye_x = base_x + screen_w * 0.35 + self.eye_offset_x * scale
        right_eye_y = eye_y + self.eye_offset_y * scale

        eye_fill = '#000000'

        def draw_closed_eye(x, y):
            self.canvas.create_line(
                x - eye_size, y,
                x + eye_size, y,
                fill=eye_fill,
                width=int(4 * scale),
                capstyle='round'
            )

        def draw_open_eye(x, y):
            self.canvas.create_oval(
                x - eye_size, y - eye_size,
                x + eye_size, y + eye_size,
                fill=eye_fill,
                outline=''
            )

        if self.blink_active:
            # both closed
            draw_closed_eye(left_eye_x, left_eye_y)
            draw_closed_eye(right_eye_x, right_eye_y)
        else:
            # maybe wink?
            # wink_active = close RIGHT only
            draw_open_eye(left_eye_x, left_eye_y)
            if self.wink_active:
                draw_closed_eye(right_eye_x, right_eye_y)
            else:
                draw_open_eye(right_eye_x, right_eye_y)

        # mouth:
        # - If speaking: animate mouth_open_amount (0..1)
        # - Else: smile curve based on expression_smile (0..1)

        if self.is_speaking:
            # talking mouth -> more "open"
            openness = 0.2 + 0.6 * self.mouth_open_amount
            mouth_height = 25 * scale + openness * 30 * scale
        else:
            # smile shape
            smile = self.expression_smile  # 0..1
            mouth_height = 20 * scale + smile * 40 * scale

        # arc for mouth
        self.canvas.create_arc(
            base_x - mouth_w, mouth_y,
            base_x + mouth_w, mouth_y + mouth_height,
            start=0,
            extent=-180,
            style="arc",
            outline='#000000',
            width=int(4 * scale)
        )

        # floppy slot
        self.canvas.create_rectangle(
            base_x - w * 0.45, base_y + h * 0.1,
            base_x + w * 0.45, base_y + h * 0.2,
            fill='#000000',
            outline='#000000',
            width=int(2 * scale)
        )

        # vents
        for i in range(6):
            y = base_y + h * 0.23 + i * 5 * scale
            self.canvas.create_line(
                base_x - w * 0.45, y,
                base_x + w * 0.45, y,
                fill=outline_col,
                width=int(2 * scale)
            )

        # base block/foot
        self.canvas.create_rectangle(
            base_x - w * 0.8, base_y + h * 0.4,
            base_x + w * 0.8, base_y + h * 0.5,
            fill=body_side,
            outline=outline_col,
            width=int(2 * scale)
        )

    ##################################################
    # ANIMATION LOOP
    ##################################################

    def maybe_blink_or_wink(self):
        """
        Control blink/wink timing.
        """
        now = time.time()

        # if already blinking/winking, check if time to stop
        if self.blink_active and (now - self._blink_start > self.blink_duration):
            self.blink_active = False
        if self.wink_active and (now - self._wink_start > self.wink_duration):
            self.wink_active = False

        # if not currently closed, maybe start a new blink/wink
        if not self.blink_active and not self.wink_active:
            if now - self.last_blink_time > 4.0:
                # 80% blink, 20% wink
                if random.random() < 0.8:
                    self.blink_now()
                else:
                    self.wink_now()

    def blink_now(self):
        self.blink_active = True
        self._blink_start = time.time()
        self.last_blink_time = time.time()

    def wink_now(self):
        self.wink_active = True
        self._wink_start = time.time()
        self.last_blink_time = time.time()

    def animation_loop(self):
        """
        Runs ~20fps. Updates mouth movement, blinking, redraws.
        """
        # animate mouth if speaking
        if self.is_speaking:
            # move mouth_open_amount toward random target so it looks like talking
            self.target_mouth_open = 0.5 + 0.5 * math.sin(time.time() * 10.0)
        else:
            self.target_mouth_open = 0.0

        # smooth mouth
        self.mouth_open_amount += (self.target_mouth_open - self.mouth_open_amount) * 0.4

        # natural decay of smile when not happy
        if self.mood not in ("happy", "speaking"):
            self.expression_smile *= 0.98
            if self.expression_smile < 0.2:
                self.expression_smile = 0.2  # keep a gentle softness

        # blink / wink scheduling
        self.maybe_blink_or_wink()

        # redraw
        self.draw_macintosh_face()

        if not self.shutting_down:
            self.root.after(50, self.animation_loop)

    ##################################################
    # LISTEN LOOP (MIC + STT)
    ##################################################

    def start_listening_loop_once(self):
        if not self.is_listening_loop_running:
            self.is_listening_loop_running = True
            threading.Thread(target=self.listen_forever_thread, daemon=True).start()
            print("[MIC] started background listen thread")

    def listen_forever_thread(self):
        """
        Loop:
         1. listen for up to timeout seconds
         2. run STT
         3. send to OpenAI
         4. speak response
        """
        while not self.shutting_down:
            try:
                with sr.Microphone(device_index=MIC_DEVICE_INDEX) as source:
                    # calibrate to noise quickly
                    self.recognizer.adjust_for_ambient_noise(source, duration=0.3)

                    # update mood to listening
                    def _listening_ui():
                        if not self.shutting_down:
                            self.mood = "listening"
                            self.set_status("Macintosh lyssnar...")
                    self.root.after(0, _listening_ui)

                    print("[MIC] Lyssnar (timeout 5s)...")
                    audio = self.recognizer.listen(
                        source,
                        timeout=5,
                        phrase_time_limit=8
                    )
                    print("[MIC] Har ljud. Kör STT...")

                try:
                    text = self.recognizer.recognize_google(audio, language=STT_LANG)
                    print("[STT] Du sa:", text)

                    def _ui_heard():
                        if not self.shutting_down:
                            self.set_status(f"Du: {text}\nMacintosh tänker...")
                            self.mood = "thinking"
                            self.expression_smile = 0.4
                    self.root.after(0, _ui_heard)

                    # now ask OpenAI and speak
                    self.answer_with_openai(text)

                except sr.UnknownValueError:
                    print("[STT] Otydligt. Ingen text.")
                    def _ui_no_hear():
                        if not self.shutting_down:
                            self.set_status("Jag hörde dig, men jag kunde inte förstå orden. Kan du säga igen?")
                            # show empathy
                            self.mood = "happy"
                            self.expression_smile = 1.0
                    self.root.after(0, _ui_no_hear)

                except Exception as e:
                    print("[STT] Fel i STT:", e)
                    def _ui_err():
                        if not self.shutting_down:
                            self.set_status("Jag hade lite problem att höra just nu.")
                            self.mood = "neutral"
                    self.root.after(0, _ui_err)

            except sr.WaitTimeoutError:
                # no speech in timeout
                # just idle, blink, keep listening
                pass
            except Exception as e:
                print("[MIC] Mic runtime error:", e)
                def _ui_mic_err():
                    if not self.shutting_down:
                        self.set_status("Mikrofon fel... försöker igen...")
                        self.mood = "neutral"
                self.root.after(0, _ui_mic_err)
                time.sleep(1)

    ##################################################
    # OPENAI CALL
    ##################################################

    def answer_with_openai(self, user_text):
        """
        Send user_text to OpenAI chat completion,
        then speak and display the answer.
        """

        # append user message to chat history
        self.chat_history.append({"role": "user", "content": user_text})

        def _worker():
            print("[OPENAI] sending:", repr(user_text))

            reply_text = None
            try:
                # NOTE: you can change the model here to whatever is available for you.
                # If you get "insufficient_quota", that's billing. Code is fine.
                completion = self.client.responses.create(
                    model="gpt-4o-mini",
                    input=self.chat_history,
                    max_output_tokens=120,
                )
                # new Responses API returns structured output
                # We'll try to grab text chunks from "output"
                chunks = []
                for item in completion.output:
                    if "content" in item:
                        for c in item["content"]:
                            if c["type"] == "output_text":
                                chunks.append(c["text"])
                reply_text = " ".join(chunks).strip()

            except Exception as e:
                print("[OPENAI ERROR]", e)
                reply_text = (
                    "Jag kunde inte kontakta mitt språkcenter just nu. "
                    "Men jag finns här med dig."
                )

            if not reply_text:
                reply_text = "Jag är här med dig."

            # store assistant answer in conversation memory
            self.chat_history.append({"role": "assistant", "content": reply_text})

            # now update UI & speak on main thread
            def _after_llm():
                if not self.shutting_down:
                    self.set_status("Macintosh: " + reply_text)
                    # put face in speaking mode
                    self.mood = "speaking"
                    self.is_speaking = True
                    self.expression_smile = 1.0

                    def done_talking():
                        # called AFTER tts finishes (see speak_tts_async)
                        if not self.shutting_down:
                            self.is_speaking = False
                            self.mood = "happy"
                            self.expression_smile = 0.8
                            self.set_status("Macintosh: " + reply_text + "\n(Jag lyssnar...)")

                    speak_tts_async(reply_text, after_done=lambda: self.root.after(0, done_talking))

            self.root.after(0, _after_llm)

        threading.Thread(target=_worker, daemon=True).start()

    ##################################################
    # SHUTDOWN
    ##################################################

    def quit_app(self):
        print("[QUIT] shutting down")
        self.shutting_down = True
        self.is_listening_loop_running = False

        def _final_exit():
            try:
                self.root.destroy()
            except:
                pass
            sys.exit(0)

        # gentle goodbye voice
        def _bye_worker():
            try:
                subprocess.run(
                    ['espeak', '-v', TTS_VOICE, '-s', TTS_WPM,
                     "Tack. Jag finns här när du behöver mig. Hej då."],
                    stderr=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL
                )
            except Exception:
                pass
            self.root.after(0, _final_exit)

        threading.Thread(target=_bye_worker, daemon=True).start()

    ##################################################
    # MAIN LOOP
    ##################################################

    def run(self):
        self.root.mainloop()


#####################################
# RUN
#####################################

if __name__ == "__main__":
    print("============================================================")
    print("EQ2 Emotional Support Macintosh - starting GUI mode")
    print("============================================================")
    print("Using mic index:", MIC_DEVICE_INDEX)
    print("Hit ESC in the window to quit.")
    print("============================================================")

    app = EQ2MacintoshAI()
    app.run()
