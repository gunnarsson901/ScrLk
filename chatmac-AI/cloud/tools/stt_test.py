import sounddevice as sd
import scipy.io.wavfile as wav
from openai import OpenAI

client = OpenAI()

fs = 16000
duration = 5
print("🎙️ Spelar in...")
audio = sd.rec(int(duration*fs), samplerate=fs, channels=1, dtype='int16')
sd.wait()
wav.write("temp.wav", fs, audio)

result = client.audio.transcriptions.create(
    model="whisper-1",
    file=open("temp.wav", "rb"),
    language="sv"
)

print("Du sa:", result.text)
