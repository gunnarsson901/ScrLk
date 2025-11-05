#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import time
import math
import shutil
import threading
import tempfile
import subprocess
import tkinter as tk
from tkinter import Canvas

import numpy as np
import sounddevice as sd
import soundfile as sf
from scipy.io.wavfile import write as wav_write

# -------------------------
# OpenAI
# -------------------------
try:
    from openai import OpenAI
    AI_AVAILABLE = bool(os.getenv("OPENAI_API_KEY"))
except Exception:
    OpenAI = None
    AI_AVAILABLE = False
    print("WARNING: openai ej installerat eller OPENAI_API_KEY saknas", file=sys.stderr)

# -------------------------
# Modeller & röst
# -------------------------
MODEL_CHAT = "gpt-4o-mini"
MODEL_WHISPER = "whisper-1"   # STT
MODEL_TTS = "tts-1"           # TTS
VOICE_TTS = "onyx"            # röst

# STT-inspelning
REC_SAMPLE_RATE = 16000
REC_CHANNELS = 1
REC_SECONDS = 4.0

# Canvas-layout
MAC_REL_SCALE = 0.62
MOUTH_PX_H = 3

class MacintoshAI:
    def __init__(self):
        # state
        self.client = None
        self.is_listening_loop_running = False
        self.shutting_down = False
        self.is_speaking = False
        self.debug = True
        self.block_stt_until = 0.0  # tidpunkt då STT åter tillåten

        # UI
        self.root = tk.Tk()
        self.root.title("Macintosh AI")
        self.root.attributes("-fullscreen", True)
        self.root.configure(bg="#1a1a1a")
        self.root.bind("<Escape>", lambda e: self.quit_app())
        self.root.bind("<Motion>", self.track_mouse)

        self.screen_width = self.root.winfo_screenwidth()
        self.screen_height = self.root.winfo_screenheight()

        self.mouse_x = self.screen_width // 2
        self.mouse_y = self.screen_height // 2
        self.eye_offset_x = 0
        self.eye_offset_y = 0
        self.head_tilt = 0

        main_frame = tk.Frame(self.root, bg="#1a1a1a")
        main_frame.pack(expand=True, fill="both")

        canvas_height = int(self.screen_height * 0.75)
        canvas_width = self.screen_width
        self.canvas = Canvas(
            main_frame, width=canvas_width, height=canvas_height,
            bg="#1a1a1a", highlightthickness=0
        )
        self.canvas.pack()

        self.canvas_width = canvas_width
        self.canvas_height = canvas_height

        self.status_label = tk.Label(
            main_frame, text="Initializing...", font=("Courier", 16),
            bg="#1a1a1a", fg="#00ff00"
        )
        self.status_label.pack(pady=20)

        self.control_label = tk.Label(
            main_frame, text="ESC: Quit", font=("Courier", 12),
            bg="#1a1a1a", fg="#666666"
        )
        self.control_label.pack()

        # mouth anim
        self.mouth_open = 0.0
        self.target_mouth = 0.0

        self.draw_mac()

        # model init
        threading.Thread(target=self.load_model_thread, daemon=True).start()

        # anim loop
        self.animate()

        # mic loop startas efter init
        self.root.after(1500, self.start_listening_loop_once)

    # -------------------------
    # UI helpers
    # -------------------------
    def safe_set_status(self, text: str):
        if not self.shutting_down:
            self.root.after(0, lambda: self.status_label.config(text=text))

    # -------------------------
    # Mouse + drawing + anim
    # -------------------------
    def track_mouse(self, event):
        self.mouse_x = event.x
        self.mouse_y = event.y
        cx = self.canvas_width / 2
        cy = self.canvas_height * 0.4
        dx = (self.mouse_x - cx) / self.canvas_width
        dy = (self.mouse_y - cy) / self.canvas_height
        self.eye_offset_x = max(-12, min(12, dx * 500))
        self.eye_offset_y = max(-8, min(8, dy * 300))
        self.head_tilt = max(-4, min(4, dx * 20))

    def draw_mac(self):
        """Ritar en vektoriserad Happy-Mac i Canvas med 1x2-ögon, spegelvänt L-näsa, leende mun."""
        c = self.canvas
        c.delete("all")

        W, H = self.canvas_width, self.canvas_height

        # Skala och centrering
        mac_h = int(H * MAC_REL_SCALE)
        mac_w = int(mac_h * 0.82)
        x0 = (W - mac_w) // 2
        y0 = (H - mac_h) // 2
        x1 = x0 + mac_w
        y1 = y0 + mac_h

        px = mac_h / 200.0
        bg = "#ffffff"
        fg = "#000000"
        c.configure(bg=bg)
        lw = int(3 * px)

        # Kropp
        c.create_rectangle(x0, y0, x1, y1 - 30*px, outline=fg, width=lw)
        c.create_rectangle(x0 + 20*px, y1 - 28*px, x1 - 20*px, y1 - 6*px, outline=fg, width=lw)

        # Skärm
        sx0 = x0 + 24*px; sy0 = y0 + 18*px
        sx1 = x1 - 24*px; sy1 = y0 + 118*px
        c.create_rectangle(sx0, sy0, sx1, sy1, outline=fg, width=lw)
        c.create_rectangle(sx0+6*px, sy0+6*px, sx1-6*px, sy1-6*px, outline=fg, width=lw)

        # Front-springor
        c.create_line(x0+28*px, y0+138*px, x0+40*px, y0+138*px, fill=fg, width=lw)
        c.create_line(x0+96*px, y0+138*px, x0+138*px, y0+138*px, fill=fg, width=lw)

        # Ansikte
        sw = sx1 - sx0
        sh = sy1 - sy0

        ox = max(-3*px, min(3*px, self.eye_offset_x * 0.05))
        oy = max(-2*px, min(2*px, self.eye_offset_y * 0.05))

        # Ögon 1x2 “pixlar”
        eye_w = 4 * px
        eye_h = 7 * px
        exl = sx0 + 0.32*sw + ox
        exr = sx0 + 0.68*sw + ox
        ey  = sy0 + 0.42*sh + oy
        c.create_rectangle(exl - eye_w/2, ey - eye_h, exl + eye_w/2, ey + eye_h, fill=fg, outline=fg)
        c.create_rectangle(exr - eye_w/2, ey - eye_h, exr + eye_w/2, ey + eye_h, fill=fg, outline=fg)

        # Näsa: spegelvänt “L” (┘) – lodrät nedåt + kort horisontell åt höger
        nx = sx0 + 0.50*sw + ox*0.2
        n_top = sy0 + 0.36*sh
        n_bot = sy0 + 0.52*sh
        c.create_line(nx, n_top, nx, n_bot, fill=fg, width=lw)
        c.create_line(nx, n_bot, nx + 6*px, n_bot, fill=fg, width=lw)

        # Mun: standard = leende. Öppning ökar nedåt med mouth_open.
        mcy = sy0 + 0.66*sh
        base_drop  = 4 * px
        extra_drop = (self.mouth_open * 6.0) * px
        drop = base_drop + extra_drop
        mw = 0.36*sw
        seg = mw/3

        # U-form: vänster \_ / höger
        c.create_line(nx - seg, mcy, nx - seg/2, mcy + drop, fill=fg, width=MOUTH_PX_H*px)
        c.create_line(nx - seg/2, mcy + drop, nx + seg/2, mcy + drop, fill=fg, width=MOUTH_PX_H*px)
        c.create_line(nx + seg/2, mcy + drop, nx + seg, mcy, fill=fg, width=MOUTH_PX_H*px)

    def animate(self):
        if abs(self.mouth_open - self.target_mouth) > 0.01:
            self.mouth_open += (self.target_mouth - self.mouth_open) * 0.3
        self.target_mouth = 0.5 + 0.5 * math.sin(time.time() * 10) if self.is_speaking else 0.0
        self.draw_mac()
        if not self.shutting_down:
            self.root.after(50, self.animate)

    # -------------------------
    # AI
    # -------------------------
    def load_model_thread(self):
        if not AI_AVAILABLE:
            self.safe_set_status("AI ej tillgänglig. Installera openai och sätt OPENAI_API_KEY.")
            return
        try:
            self.client = OpenAI()
            self.safe_set_status("Klar. Lyssnar.")
            # Hälsning, blockera STT så den inte hör sig själv
            self.speak_text("God kväll. Jag är online i detta Macintosh-chassi.")
        except Exception as e:
            self.client = None
            self.safe_set_status(f"OpenAI-initfel: {e}")
            print(f"OpenAI init error: {e}", file=sys.stderr)

    def mac_system_prompt(self) -> str:
        return (
            "Du är en lugn, lågmäld AI med ton inspirerad av HAL 9000. "
            "Tala tydligt, mjukt och med självsäker precision. "
            "Du kör i ett vintage Macintosh Classic-gränssnitt. "
            "Var artig, logisk, lite kylig men aldrig hotfull. "
            "Håll meningarna korta. Referera subtilt till miljön: "
            "’detta Macintosh-chassi’, ’min katodstråleskärm’, ’dina musrörelser’. "
            "Citera inte HAL ordagrant. Svara på svenska."
        )

    def generate_response_blocking(self, user_text: str) -> str:
        if not self.client:
            return "AI-klienten är inte initialiserad."
        try:
            resp = self.client.chat.completions.create(
                model=MODEL_CHAT,
                messages=[
                    {"role": "system", "content": self.mac_system_prompt()},
                    {"role": "system", "content": "Svara alltid på svenska."},
                    {"role": "user", "content": user_text}
                ],
                temperature=0.4,
                max_tokens=160,
            )
            text = (resp.choices[0].message.content or "").strip()
            # Kortare svar: max två meningar
            parts = [p.strip() for p in text.split(".") if p.strip()]
            if len(parts) >= 2:
                return parts[0] + ". " + parts[1] + "."
            return text
        except Exception as e:
            print(f"[CHAT] {e}", file=sys.stderr)
            return "Jag stötte på ett bearbetningsfel."

    # -------------------------
    # STT (Whisper)
    # -------------------------
    def record_phrase_wav(self) -> str | None:
        # blockera inspelning medan/strax efter tal
        if time.time() < self.block_stt_until:
            time.sleep(0.1)
            return None
        try:
            self.safe_set_status("🎤 Lyssnar… (prata nu)")
            frames = int(REC_SAMPLE_RATE * REC_SECONDS)
            audio = sd.rec(frames, samplerate=REC_SAMPLE_RATE, channels=REC_CHANNELS, dtype="float32")
            sd.wait()

            if not isinstance(audio, np.ndarray) or audio.size == 0:
                if self.debug: print("[STT] tom buffert")
                return None

            if audio.ndim > 1:
                audio = audio[:, 0]

            peak = float(np.max(np.abs(audio)))
            rms  = float(np.sqrt(np.mean(audio**2)))
            if self.debug:
                print(f"[STT] peak={peak:.3f} rms={rms:.3f}")

            # Enkel VAD: justera vid behov
            if rms < 0.005:
                if self.debug: print("[STT] för tyst, hoppar")
                return None

            if peak > 0:
                audio = audio / max(1.0, peak)

            tmp_wav = os.path.join(tempfile.gettempdir(), f"mac_phrase_{int(time.time()*1000)}.wav")
            wav_write(tmp_wav, REC_SAMPLE_RATE, (audio * 32767).astype(np.int16))
            return tmp_wav
        except Exception as e:
            print(f"[STT] Record error: {e}", file=sys.stderr)
            return None

    def transcribe_with_whisper(self, wav_path: str) -> str | None:
        try:
            with open(wav_path, "rb") as f:
                tr = self.client.audio.transcriptions.create(
                    model=MODEL_WHISPER,
                    file=f,
                    # Lås gärna språket:
                    language="sv"
                )
            text = (getattr(tr, "text", "") or "").strip()
            if self.debug:
                print(f"[STT] whisper: {text!r}")
            return text or None
        except Exception as e:
            print(f"[STT] Whisper error: {e}", file=sys.stderr)
            return None
        finally:
            try: os.remove(wav_path)
            except Exception: pass

    # -------------------------
    # TTS (Onyx) – WAV → sounddevice
    # -------------------------
    def speak_text(self, text: str):
        if not text:
            return
        self.is_speaking = True
        self.block_stt_until = time.time() + 0.9  # blockera STT medan han pratar
        self.safe_set_status("🔊 Talar…")

        def _speak():
            try:
                if self.client is None:
                    raise RuntimeError("OpenAI client saknas")

                res = self.client.audio.speech.create(
                    model=MODEL_TTS,
                    voice=VOICE_TTS,
                    input=text,
                    response_format="wav"
                )
                try:
                    audio_bytes = getattr(res, "read", None) and res.read() or getattr(res, "content", None)
                    if audio_bytes is None:
                        audio_bytes = bytes(res)
                except Exception:
                    audio_bytes = bytes(res)

                wav_path = os.path.join(tempfile.gettempdir(), f"mac_tts_{int(time.time()*1000)}.wav")
                with open(wav_path, "wb") as f:
                    f.write(audio_bytes)

                data, sr = sf.read(wav_path, dtype="float32", always_2d=False)
                sd.play(data, sr)
                sd.wait()
            except Exception as e:
                print(f"[TTS] {e}", file=sys.stderr)
                # Fallback: SAPI (WSL)
                try:
                    if self._in_wsl() and shutil.which("powershell.exe"):
                        ps = shutil.which("powershell.exe")
                        cmd = [
                            ps, "-NoProfile", "-Command",
                            'Add-Type -AssemblyName System.Speech; '
                            '$s=New-Object System.Speech.Synthesis.SpeechSynthesizer; '
                            '$s.Rate=-1; $s.Volume=100; '
                            f'$s.Speak(@\'{text}\'@);'
                        ]
                        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                except Exception:
                    pass
            finally:
                self.is_speaking = False
                self.block_stt_until = time.time() + 0.6  # lite svans efter tal
                if self.debug:
                    print("[TTS] done")
                if not self.shutting_down:
                    self.safe_set_status("Klar. Lyssnar.")

        threading.Thread(target=_speak, daemon=True).start()

    def _in_wsl(self) -> bool:
        try:
            return "microsoft" in open("/proc/sys/kernel/osrelease").read().lower()
        except Exception:
            return False

    # -------------------------
    # High-level: text → svar → tala
    # -------------------------
    def handle_user_text_mainthread(self, user_text: str):
        self.safe_set_status(f"Du sa: {user_text}")
        threading.Thread(target=self._answer_worker, args=(user_text,), daemon=True).start()

    def _answer_worker(self, user_text: str):
        try:
            answer = self.generate_response_blocking(user_text)
        except Exception as e:
            print(f"[AI] {e}", file=sys.stderr)
            answer = "Jag fick ett fel när jag skulle svara."
        if not self.shutting_down:
            self.root.after(0, lambda a=answer: self.status_label.config(text=f"Jag: {a}"))
            self.speak_text(answer)

    # -------------------------
    # Lyssningsloop
    # -------------------------
    def start_listening_loop_once(self):
        if self.is_listening_loop_running or self.shutting_down or not AI_AVAILABLE:
            return
        self.is_listening_loop_running = True
        threading.Thread(target=self.listen_loop_thread, daemon=True).start()

    def listen_loop_thread(self):
        while not self.shutting_down:
            try:
                # hoppa om TTS fortfarande “svansar”
                if time.time() < self.block_stt_until or self.is_speaking:
                    time.sleep(0.05)
                    continue

                wav_path = self.record_phrase_wav()
                if not wav_path:
                    time.sleep(0.05)
                    continue

                text = self.transcribe_with_whisper(wav_path)
                if text:
                    self.root.after(0, lambda t=text: self.handle_user_text_mainthread(t))
                else:
                    self.safe_set_status("…(ingen röst uppfattad)")
            except Exception as e:
                print(f"[STT] listen loop error: {e}", file=sys.stderr)
                self.safe_set_status("Mikrofonfel. Försöker igen…")
                time.sleep(0.3)

    # -------------------------
    # Shutdown
    # -------------------------
    def quit_app(self):
        self.shutting_down = True
        self.is_listening_loop_running = False

        def _final_exit():
            try:
                self.root.destroy()
            except Exception:
                pass
            sys.exit(0)

        try:
            self.speak_text("Avslutar. Tack för sällskapet.")
            self.root.after(900, _final_exit)
        except Exception:
            _final_exit()

    # -------------------------
    # Mainloop
    # -------------------------
    def run(self):
        self.root.mainloop()

# -------------------------
# Entrypoint
# -------------------------
if __name__ == "__main__":
    print("=" * 60)
    print("Macintosh AI - Starting...")
    print("=" * 60)
    print("Controls:")
    print("  ESC    - Quit")
    print("=" * 60)
    if not AI_AVAILABLE:
        print("Installera: pip install openai  # och sätt OPENAI_API_KEY")
    print("Kräver även: pip install sounddevice soundfile scipy numpy")
    print("=" * 60)

    # Tips WSLg: export PULSE_SERVER=/mnt/wslg/PulseServer i ~/.bashrc
    # Testa enheter: python -c "import sounddevice as sd; print(sd.query_devices())"

    app = MacintoshAI()
    app.run()
