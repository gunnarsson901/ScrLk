import speech_recognition as sr
import os
from openai import OpenAI
import subprocess

print("API key:", "set" if os.getenv("OPENAI_API_KEY") else "NOT set")

# --- 1. Test mikrofon ---
r = sr.Recognizer()
with sr.Microphone() as source:
    print("🎤 Säg något...")
    audio = r.listen(source, timeout=5, phrase_time_limit=5)

# --- 2. Speech-to-Text ---
try:
    text = r.recognize_google(audio, language="sv-SE")
    print("🗣 Du sa:", text)
except Exception as e:
    print("STT FEL:", e)
    text = None

# --- 3. Skicka till OpenAI (om STT lyckades) ---
if text:
    try:
        client = OpenAI()
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": text}]
        )
        answer = resp.choices[0].message.content
        print("🤖 AI svar:", answer)
    except Exception as e:
        print("AI FEL:", e)
        answer = None

# --- 4. TTS test ---
if text:
    print("🔊 Talar...")
    subprocess.run(["espeak-ng", "-s", "160", answer or "Hej"])
