#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import tkinter as tk
from tkinter import Canvas, NW
from dataclasses import dataclass, field

# =========================
#  Minimal spelvärld
# =========================
@dataclass
class Room:
    name: str
    desc: str
    bg_key: str
    exits: dict[str, str] = field(default_factory=dict)     # direction -> room_key
    items: list[str] = field(default_factory=list)           # item keys present


WORLD: dict[str, Room] = {
    "clearing": Room(
        name="Forest Clearing",
        desc="You are in a small forest clearing. Paths lead north and east.",
        bg_key="clearing",
        exits={"north": "path", "east": "cellar"},
        items=["lamp"],
    ),
    "path": Room(
        name="Forest Path",
        desc="A narrow path under dark trees. South returns to the clearing; west to a vault.",
        bg_key="path",
        exits={"south": "clearing", "west": "vault"},
        items=["key"],
    ),
    "cellar": Room(
        name="Damp Cellar",
        desc="It smells of old stone and dust. A ladder goes west to the clearing.",
        bg_key="cellar",
        exits={"west": "clearing"},
        items=[],
    ),
    "vault": Room(
        name="Ancient Vault",
        desc="A quiet stone vault. An alcove glitters faintly.",
        bg_key="vault",
        exits={"east": "path"},
        items=["gem"],
    ),
}

ITEM_NAMES = {
    "lamp": "Brass Lamp",
    "key":  "Small Key",
    "gem":  "Blue Gem",
}

# =========================
#  Bildhanterare
# =========================
class Assets:
    """
    Laddar PNG:er för rumsbakgrund och inventarieikoner.
    Använder endast Tk PhotoImage (PNG stöds i Tk 8.6+).
    """
    def __init__(self, root: tk.Tk, base: str = "images"):
        self.root = root
        self.base = base
        self.rooms: dict[str, tk.PhotoImage] = {}
        self.items: dict[str, tk.PhotoImage] = {}

        # Ladda rum (fördefinierade)
        for rkey in ["clearing", "path", "cellar", "vault"]:
            self.rooms[rkey] = self._load_png(os.path.join(base, "rooms", f"{rkey}.png"))

        # Ladda items
        for ikey in ["lamp", "key", "gem"]:
            self.items[ikey] = self._load_png(os.path.join(base, "items", f"{ikey}.png"))

        # Liten placeholder om något saknas
        self.placeholder_room = self._mk_placeholder(512, 342, fill="#C0D8C0", border="#000000")
        self.placeholder_icon = self._mk_placeholder(48, 48, fill="#E0E0E0", border="#000000")

    def _load_png(self, path: str) -> tk.PhotoImage | None:
        try:
            if os.path.exists(path):
                return tk.PhotoImage(file=path)
        except Exception as e:
            print(f"[assets] kunde inte ladda {path}: {e}", file=sys.stderr)
        return None

    def _mk_placeholder(self, w: int, h: int, fill="#DDD", border="#000"):
        # PhotoImage fungerar men pixel-pixel är omständligt; rita en 1x1 och zooma
        img = tk.PhotoImage(width=1, height=1)
        img.put(fill, to=(0, 0, 1, 1))
        # zoom() måste vara heltal; vi skalar ungefär: bygg en canvas-rect istället vid draw om du vill.
        # För enkelhet: returnera 1x1, så används som “färgad pixel” (ser liten ut).
        return img

# =========================
#  Spel + UI
# =========================
class ZorkLikeUI:
    def __init__(self, title="Zork-like (Voice/PNG)"):
        self.root = tk.Tk()
        self.root.title(title)
        self.root.configure(bg="#111")
        self.root.attributes("-fullscreen", True)
        self.root.bind("<Escape>", lambda e: self.quit())

        self.W = self.root.winfo_screenwidth()
        self.H = self.root.winfo_screenheight()

        self.canvas = Canvas(self.root, width=self.W, height=int(self.H*0.85), bg="#111", highlightthickness=0)
        self.canvas.pack()

        # UI: kommandorad (fallback för test utan röst)
        cmd_frame = tk.Frame(self.root, bg="#111")
        cmd_frame.pack(fill="x")
        self.entry = tk.Entry(cmd_frame, font=("Courier", 16), bg="#222", fg="#EEE", insertbackground="#EEE")
        self.entry.pack(side="left", fill="x", expand=True, padx=12, pady=8)
        self.entry.bind("<Return>", self._on_enter)

        self.btn = tk.Button(cmd_frame, text="Send", command=self._on_click)
        self.btn.pack(side="right", padx=12)

        # status
        self.status = tk.StringVar(value="Say 'look', 'go north', 'take lamp', 'inventory', 'quit'")
        self.status_label = tk.Label(self.root, textvariable=self.status, font=("Courier", 14), bg="#111", fg="#8f8")
        self.status_label.pack(pady=(0, 10))

        self.assets = Assets(self.root)

        # Spelstate
        self.room_key = "clearing"
        self.inventory: list[str] = []
        self.message_lines: list[str] = []

        self.draw_all(initial=True)
        self.say("System ready. Welcome to the clearing.")

    # =========== Publik hook för STT ===========
    def feed_transcript(self, text: str):
        """
        Mata in röstkommandon hit från din Whisper-loop:
           ui.feed_transcript(transcribed_text)
        """
        self.handle_command(text)

    # =========== Rendering ===========
    def draw_all(self, initial=False):
        self.canvas.delete("all")

        # 1) Bakgrundsbild för rummet
        self._draw_room_bg()

        # 2) Textpanel (rumsnamn och beskrivning)
        self._draw_room_text()

        # 3) Inventarie-rad med ikoner
        self._draw_inventory_bar()

        if initial:
            self.look()

    def _draw_room_bg(self):
        r = WORLD[self.room_key]
        img = self.assets.rooms.get(r.bg_key) or self.assets.placeholder_room

        # PhotoImage saknar smidig skalning; för bästa resultat gör PNG ~fönstrets storlek.
        # Vi centrerar bilden på canvas.
        iw = img.width()
        ih = img.height()
        cx = self.W // 2
        cy = int(self.H*0.85) // 2
        self.canvas.create_image(cx - iw//2, cy - ih//2, image=img, anchor=NW)
        # HÅLL REFERENSEN! Annars garbage-collectas bilden.
        self._last_bg_ref = img

    def _draw_room_text(self):
        r = WORLD[self.room_key]
        panel_h = 140
        y0 = int(self.H*0.85) - panel_h

        # panelbakgrund
        self.canvas.create_rectangle(0, y0, self.W, int(self.H*0.85),
                                     fill="#101010", outline="#303030", width=2)
        # titel
        self.canvas.create_text(20, y0+12, text=r.name, fill="#E6F2E6",
                                font=("Courier", 22, "bold"), anchor=NW)

        # beskrivning
        self.canvas.create_text(20, y0+48, text=r.desc, fill="#CFE9CF",
                                width=self.W-40, font=("Courier", 14), anchor=NW)

        # senaste systemmeddelanden (2 rader)
        if self.message_lines:
            msg = "\n".join(self.message_lines[-2:])
            self.canvas.create_text(self.W-20, y0+12, text=msg, fill="#9FD39F",
                                    font=("Courier", 12), anchor="ne", justify="right")

    def _draw_inventory_bar(self):
        bar_h = 86
        y0 = int(self.H*0.85)
        self.canvas.create_rectangle(0, y0, self.W, self.H,
                                     fill="#0C0C0C", outline="#303030", width=2)
        self.canvas.create_text(16, y0+10, text="Inventory:", fill="#9FD39F",
                                font=("Courier", 14, "bold"), anchor=NW)

        x = 140
        gap = 14
        icon_size = 48

        for ikey in self.inventory:
            img = self.assets.items.get(ikey) or self.assets.placeholder_icon
            # Rita bricka bakom ikonen
            self.canvas.create_rectangle(x-6, y0+6, x+icon_size+6, y0+icon_size+18,
                                         outline="#2A2A2A", fill="#151515")
            # Ikon
            self.canvas.create_image(x, y0+12, image=img, anchor=NW)
            # Text
            label = ITEM_NAMES.get(ikey, ikey)
            self.canvas.create_text(x+icon_size//2, y0+icon_size+10,
                                    text=label, fill="#BFEABF",
                                    font=("Courier", 10), anchor="n")
            # Håll referens
            self.canvas.image = getattr(self.canvas, "image", []) + [img]
            x += icon_size + gap + 24

    # =========== Spelkommandon ===========
    def handle_command(self, raw: str):
        text = (raw or "").strip().lower()
        if not text:
            return
        self.entry.delete(0, "end")

        # Normalisera riktningar
        synonyms = {
            "n": "north", "s": "south", "e": "east", "w": "west",
            "north": "north", "south": "south", "east": "east", "west": "west",
            "upp": "north", "ner": "south", "vänster": "west", "höger": "east",
        }

        said = text
        self.note(f"> {said}")

        # GO
        if text.startswith("go ") or text.startswith("walk ") or text in synonyms:
            parts = text.split()
            direction = parts[-1] if parts else text
            direction = synonyms.get(direction, direction)
            return self.go(direction)

        # LOOK
        if text in ("look", "see", "examine", "inspect", "titta", "kolla"):
            return self.look()

        # TAKE
        if text.startswith("take ") or text.startswith("pick ") or text.startswith("grab ") or \
           text.startswith("plocka ") or text.startswith("ta "):
            word = text.split()[-1]
            return self.take(word)

        # INVENTORY
        if text in ("inventory", "inv", "i", "stuff", "saker"):
            return self.show_inventory()

        # QUIT
        if text in ("quit", "exit", "avsluta"):
            self.say("Shutting down. Goodbye.")
            self.root.after(500, self.quit)
            return

        # fallback
        self.say("I did not understand.")
        self.draw_all()

    def go(self, direction: str):
        r = WORLD[self.room_key]
        if direction in r.exits:
            self.room_key = r.exits[direction]
            self.say(f"Moving {direction}.")
            self.draw_all()
        else:
            self.say("No passage that way.")
            self.draw_all()

    def look(self):
        r = WORLD[self.room_key]
        msg = r.desc
        if r.items:
            nice = ", ".join(ITEM_NAMES.get(i, i) for i in r.items)
            msg += f" You see: {nice}."
        self.say(msg)
        self.draw_all()

    def take(self, word: str):
        # matcha mot item keys först
        key = None
        for k, name in ITEM_NAMES.items():
            if word == k or word in name.lower():
                key = k
                break
        if not key:
            self.say("I can't take that.")
            self.draw_all()
            return
        r = WORLD[self.room_key]
        if key in r.items:
            r.items.remove(key)
            self.inventory.append(key)
            self.say(f"Taken {ITEM_NAMES.get(key, key)}.")
            self.draw_all()
        else:
            self.say("It's not here.")
            self.draw_all()

    def show_inventory(self):
        if not self.inventory:
            self.say("You carry nothing.")
        else:
            nice = ", ".join(ITEM_NAMES.get(i, i) for i in self.inventory)
            self.say(f"You carry: {nice}.")
        self.draw_all()

    # =========== TTS/Status ===========
    def say(self, text: str):
        """
        Här kan du koppla på din Onyx-TTS.
        Just nu: uppdaterar status och print.
        """
        self.status.set(text)
        print("[SAY]", text)

        # ---- KOPPLA TTS HÄR ----
        # from openai import OpenAI
        # client = OpenAI()
        # audio = client.audio.speech.create(model="tts-1", voice="onyx", input=text, response_format="wav")
        # ...spela upp wav...

    def note(self, text: str):
        self.message_lines.append(text)
        if len(self.message_lines) > 10:
            self.message_lines = self.message_lines[-10:]

    # =========== Events ===========
    def _on_enter(self, _e):
        self.handle_command(self.entry.get())

    def _on_click(self):
        self.handle_command(self.entry.get())

    def quit(self):
        try:
            self.root.destroy()
        except Exception:
            pass
        sys.exit(0)

    def run(self):
        self.root.mainloop()


# =========================
#  Main
# =========================
if __name__ == "__main__":
    ui = ZorkLikeUI()
    # Exempel: så här skickar du text från din Whisper-tråd:
    # ui.feed_transcript("look")
    ui.run()
