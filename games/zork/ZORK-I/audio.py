import os, tempfile, threading
import collections, time, os
import webrtcvad

VAD_AGGR = int(os.getenv("ZORK_VAD", "2"))   # 0–3
VAD_FRAME_MS = 20                            # 10/20/30 ms
VAD_SR = 16000                               # måste vara 16k mono
SILENCE_HANG_MS = 500                        # hur länge tystnad krävs för att avsluta
UTTER_MAX_MS = 15000   
AI_OK = False; USE_AUDIO = False
try:
    from openai import OpenAI
    AI_OK = bool(os.getenv("OPENAI_API_KEY"))
except Exception:
    OpenAI = None; AI_OK = False

try:
    import numpy as np, sounddevice as sd, soundfile as sf
    from scipy.io.wavfile import write as wav_write
    USE_AUDIO = True
except Exception:
    USE_AUDIO = False

MODEL_WHISPER = "whisper-1"
MODEL_TTS     = "tts-1"
VOICE_TTS     = "onyx"
REC_SR, REC_SEC, REC_CH = 16000, 4.0, 1

class AudioIO:
    def __init__(self):
        self.client = OpenAI() if AI_OK else None
        self.is_speaking = False
        self.lock = threading.Lock()
        self.vad = webrtcvad.Vad(VAD_AGGR)
        self.keep_listen = False
        self.on_transcript = None   # callback(text)

    def _frame_bytes(self, samples_f32):
        # float32 [-1,1] -> int16 bytes 16k mono
        import numpy as np
        s = (samples_f32 * 32767.0).clip(-32768, 32767).astype(np.int16)
        return s.tobytes()
    
    def start_auto_listen(self, on_transcript):
        if not (AI_OK and USE_AUDIO): return
        if self.keep_listen: return
        self.on_transcript = on_transcript
        self.keep_listen = True
        t = threading.Thread(target=self._listen_loop, daemon=True)
        t.start()

    def stop_auto_listen(self):
        self.keep_listen = False

    def _listen_loop(self):
        import numpy as np, sounddevice as sd
        frame_len = int(VAD_SR * VAD_FRAME_MS/1000)
        hang_frames = int(SILENCE_HANG_MS / VAD_FRAME_MS)
        max_frames = int(UTTER_MAX_MS / VAD_FRAME_MS)

        while self.keep_listen:
            try:
                # vänta tills vi inte pratar, för att undvika eko
                if self.is_speaking:
                    time.sleep(0.05); continue

                # inspelningsström i 16k mono
                q = collections.deque(maxlen=hang_frames)
                voiced = False
                collected = []
                with sd.InputStream(samplerate=VAD_SR, channels=1, dtype='float32', blocksize=frame_len):
                    start_t = time.time()
                    while self.keep_listen and not self.is_speaking:
                        block, _ = sd.RawInputStream  # hint för IDE
                        data, _ = sd.rec(int(frame_len), samplerate=VAD_SR, channels=1, dtype='float32'), sd.wait()
                        # sd.rec ovan är blockande; gör om till 1 block:
                        x = data.reshape(-1).astype('float32')
                        fb = self._frame_bytes(x)
                        is_speech = self.vad.is_speech(fb, VAD_SR)

                        if is_speech:
                            voiced = True
                            collected.append(fb)
                            q.clear()
                        else:
                            if voiced:
                                q.append(fb)
                                if len(q) >= hang_frames:
                                    break
                            else:
                                # fortfarande tyst före start
                                pass

                        if voiced and len(collected) >= max_frames:
                            break

                if not voiced:
                    continue

                # lägg till hangover-tystnad i slutet för stabilitet
                collected.extend(list(q))
                # skriv temporär wav
                import wave
                tmp = os.path.join(tempfile.gettempdir(), f"vad_{int(time.time()*1000)}.wav")
                with wave.open(tmp, 'wb') as wf:
                    wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(VAD_SR)
                    wf.writeframes(b"".join(collected))

                # transkribera
                try:
                    with open(tmp, "rb") as f:
                        tr = self.client.audio.transcriptions.create(model="whisper-1", file=f)
                    txt = (tr.text or "").strip()
                    if txt and self.on_transcript:
                        self.on_transcript(txt)
                finally:
                    try: os.remove(tmp)
                    except: pass

            except Exception:
                time.sleep(0.2)


    def speak(self, text):
        if not text or not (AI_OK and USE_AUDIO): return
        def _w():
            self.is_speaking = True
            try:
                res = self.client.audio.speech.create(model=MODEL_TTS, voice=VOICE_TTS, input=text, response_format="wav")
                try: audio_bytes = res.read()
                except AttributeError:
                    audio_bytes = getattr(res, "content", None) or bytes(res)
                tmp = os.path.join(tempfile.gettempdir(), "tts.wav")
                with open(tmp, "wb") as f: f.write(audio_bytes)
                data, sr = sf.read(tmp, dtype="float32", always_2d=False)
                sd.play(data, sr); sd.wait()
            except Exception:
                pass
            finally:
                self.is_speaking = False
        threading.Thread(target=_w, daemon=True).start()

    def stt_once(self):
        if not (AI_OK and USE_AUDIO): return None
        try:
            import numpy as np
            frames = int(REC_SR * REC_SEC)
            audio = sd.rec(frames, samplerate=REC_SR, channels=REC_CH, dtype="float32"); sd.wait()
            peak = float(np.max(np.abs(audio))) if audio.size else 0.0
            if peak > 0: audio = audio / max(1.0, peak)
            tmp = os.path.join(tempfile.gettempdir(), "stt.wav")
            wav_write(tmp, REC_SR, (audio * 32767).astype(np.int16))
            with open(tmp, "rb") as f:
                tr = self.client.audio.transcriptions.create(model=MODEL_WHISPER, file=f)
            return (tr.text or "").strip()
        except Exception:
            return None
