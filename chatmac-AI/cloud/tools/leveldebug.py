import speech_recognition as sr
import audioop
import sys, time

# Välj PulseAudio (index 0 om listan var ['pulse','default'])
mic_index = 0

r = sr.Recognizer()
r.energy_threshold = 100

with sr.Microphone(device_index=mic_index, sample_rate=44100, chunk_size=1024) as source:
    print("🎤 Mäter ljudnivå i 3 sekunder... prata nära mikrofonen")
    s = source.stream
    t0 = time.time()
    while time.time() - t0 < 3:
        data = s.read(1024)   # <-- ändring här, inga extra argument
        rms = audioop.rms(data, 2)  # 16-bit audio
        sys.stdout.write(f"\rRMS: {rms:5d}")
        sys.stdout.flush()

print("\n✅ Klart – om RMS ökar när du pratar så når ljudet WSL.")
