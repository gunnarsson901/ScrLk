import os, time, tkinter as tk
from tkinter import Canvas, END
try:
    from PIL import Image, ImageTk
    PIL_OK = True
except Exception:
    PIL_OK = False

from .engine import Game
from .resources import *
from .audio import AudioIO, AI_OK, USE_AUDIO

class VoxZorkApp:
    def __init__(self):
        self.audio = AudioIO()
        self.game = Game()
        self._img_cache, self._tk_cache, self._sprite_refs = {}, {}, []

        self.root = tk.Tk()
        self.root.title("Zork-like (Voice) – CRT")
        self.root.configure(bg=CRT_BG)
        self.root.attributes("-fullscreen", True)
        self.root.bind("<Escape>", lambda e: self.quit())
        self.root.bind("<Return>", lambda e: self.send_text())
        self.root.bind("<v>", lambda e: self.push_to_talk())
        self.root.bind("<V>", lambda e: self.push_to_talk())

        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        self.scale = min(sw/LOGW, (sh*0.92)/LOGH)
        cw, ch = int(LOGW*self.scale), int(LOGH*self.scale)

        top = tk.Frame(self.root, bg=CRT_BG); top.pack(expand=True, fill="both")
        self.canvas = Canvas(top, width=cw, height=ch, bg=CRT_BG, highlightthickness=0)
        self.canvas.grid(row=0, column=0, padx=12, pady=12, sticky="nsew")
        right = tk.Frame(top, bg=CRT_BG); right.grid(row=0, column=1, sticky="ns", pady=12, padx=(0,12))
        top.columnconfigure(0, weight=1); top.rowconfigure(0, weight=1)

        self.log = tk.Text(right, width=44, height=28, bg=CRT_BG, fg=CRT_FG,
                           insertbackground=CRT_FG, bd=0, highlightthickness=1,
                           highlightbackground=CRT_DIM, wrap="word"); self.log.pack(pady=(0,8))
        self.entry = tk.Entry(right, bg=CRT_BG, fg=CRT_FG, insertbackground=CRT_FG,
                              highlightthickness=1, highlightbackground=CRT_DIM)
        self.entry.pack(fill="x"); self.entry.insert(0, "Type here… or press V to speak")

        btns = tk.Frame(right, bg=CRT_BG); btns.pack(pady=8, fill="x")
        tk.Button(btns, text="Look", command=lambda: self.do_cmd("look")).pack(side="left", padx=2)
        tk.Button(btns, text="Inv",  command=lambda: self.do_cmd("inventory")).pack(side="left", padx=2)
        tk.Button(btns, text="Speak",command=self.push_to_talk).pack(side="left", padx=2)

        self.status = tk.Label(right, text="Ready.", bg=CRT_BG, fg=CRT_FG); self.status.pack(anchor="w", pady=(8,0))

        self.draw_world()
        self.tell(self.game.look(), speak=True)
        # Starta hands-free konversation
        self.audio.start_auto_listen(self._heard_text)
        self.root.after(100, self.redraw_loop)

    def _heard_text(self, text):
        # körs från lyssnartråd – hoppa till Tk:s main thread
        self.root.after(0, lambda: self._handle_text(text))

    def _handle_text(self, text):
        self.entry.delete(0, END)
        self.entry.insert(0, text)
        self.do_cmd(text)


    # helpers
    def fx(self, x): return int(x*self.scale)
    def fy(self, y): return int(y*self.scale)
    def log_write(self, s): self.log.insert(END, s + "\n\n"); self.log.see(END)
    def set_status(self, s): self.status.config(text=s)

    # images
    def _load_image(self, path):
        if not PIL_OK: return None
        if path in self._img_cache: return self._img_cache[path]
        try:
            img = Image.open(path).convert("RGBA"); self._img_cache[path] = img; return img
        except Exception: return None
    def _get_tk_image(self, path, w, h):
        key = (path, w, h)
        if key in self._tk_cache: return self._tk_cache[key]
        pil = self._load_image(path)
        if pil is None: return None
        try: resized = pil.resize((max(1,w), max(1,h)), Image.LANCZOS)
        except Exception: resized = pil
        tkimg = ImageTk.PhotoImage(resized); self._tk_cache[key] = tkimg; return tkimg

    # draw
    def draw_world(self):
        c = self.canvas; c.delete("all"); self._sprite_refs.clear()
        self.draw_location_image()
        for y in range(0, LOGH, 4):
            c.create_line(self.fx(0), self.fy(y), self.fx(LOGW), self.fy(y), fill=CRT_GRID)
        self.draw_face()
        self.draw_inventory_bar()
        rname = self.game and self.game.room and self.game.room in ROOM_IMAGE and ""
        c.create_text(self.fx(LOC_X + LOC_W//2), self.fy(LOC_Y - 20),
                      text=self.game and self.game.room and (self.game.room.replace("_"," ").title()),
                      fill=CRT_FG, font=("Courier", int(16*self.scale)))

    def draw_location_image(self):
        c = self.canvas; lw = max(1, int(2*self.scale))
        c.create_rectangle(self.fx(LOC_X-6), self.fy(LOC_Y-6),
                           self.fx(LOC_X+LOC_W+6), self.fy(LOC_Y+LOC_H+6),
                           outline=CRT_DIM, width=lw)
        base = ROOM_IMAGE.get(self.game.room)
        path = os.path.join(LOC_DIR, f"{base}.png") if base else None
        if PIL_OK and path and os.path.exists(path):
            tkimg = self._get_tk_image(path, self.fx(LOC_W), self.fy(LOC_H))
            if tkimg:
                c.create_image(self.fx(LOC_X), self.fy(LOC_Y), image=tkimg, anchor="nw")
                self._sprite_refs.append(tkimg); return
        c.create_rectangle(self.fx(LOC_X), self.fy(LOC_Y),
                           self.fx(LOC_X+LOC_W), self.fy(LOC_Y+LOC_H),
                           outline=CRT_FG, width=lw)
        c.create_text(self.fx(LOC_X+LOC_W/2), self.fy(LOC_Y+LOC_H/2),
                      text="No image", fill=CRT_FG, font=("Courier", int(14*self.scale)))

    def draw_inventory_bar(self):
        c = self.canvas
        c.create_rectangle(self.fx(0), self.fy(INV_Y), self.fx(LOGW), self.fy(LOGH),
                           outline=CRT_DIM, fill=CRT_BG, width=1)
        c.create_text(self.fx(12), self.fy(INV_Y + 16),
                      text="Inventory:", anchor="w",
                      fill=CRT_FG, font=("Courier", int(12*self.scale)))
        if not self.game.inv:
            c.create_text(self.fx(120), self.fy(INV_Y + 18),
                          text="(empty)", anchor="w",
                          fill=CRT_DIM, font=("Courier", int(12*self.scale)))
            return
        x = 120
        for item in self.game.inv:
            base = ITEM_IMAGE.get(item, item)
            path = os.path.join(ITEM_DIR, f"{base}.png")
            size = (self.fx(ICON_SIZE), self.fx(ICON_SIZE))
            if PIL_OK and os.path.exists(path):
                tkimg = self._get_tk_image(path, *size)
                if tkimg:
                    c.create_image(self.fx(x), self.fy(INV_Y + 10), image=tkimg, anchor="nw")
                    self._sprite_refs.append(tkimg)
                else:
                    self._icon_placeholder(x, INV_Y + 10, item)
            else:
                self._icon_placeholder(x, INV_Y + 10, item)
            x += ICON_SIZE + INV_PAD

    def _icon_placeholder(self, lx, ly, label):
        c = self.canvas; lw = max(1, int(1*self.scale))
        c.create_rectangle(self.fx(lx), self.fy(ly),
                           self.fx(lx+ICON_SIZE), self.fy(ly+ICON_SIZE),
                           outline=CRT_FG, width=lw)
        c.create_text(self.fx(lx+ICON_SIZE/2), self.fy(ly+ICON_SIZE/2),
                      text=label[:4], fill=CRT_FG, font=("Courier", int(10*self.scale)))

    def draw_face(self):
        c = self.canvas
        x0,y0,x1,y1 = 40, 60, 240, 160
        lw = max(1, int(2*self.scale))
        c.create_rectangle(self.fx(x0), self.fy(y0), self.fx(x1), self.fy(y1), outline=CRT_FG, width=lw)
        cx, cy = (x0+x1)/2, (y0+y1)/2
        eye_dx, eye_h = 28, 14

        # ögon
        blink = (int(time.time()*2) % 6 == 0) and (not self.audio.is_speaking)
        if blink:
            c.create_line(self.fx(cx-eye_dx-6), self.fy(cy), self.fx(cx-eye_dx+6), self.fy(cy), fill=CRT_FG, width=lw)
            c.create_line(self.fx(cx+eye_dx-6), self.fy(cy), self.fx(cx+eye_dx+6), self.fy(cy), fill=CRT_FG, width=lw)
        else:
            c.create_rectangle(self.fx(cx-eye_dx-3), self.fy(cy-eye_h), self.fx(cx-eye_dx+3), self.fy(cy+eye_h), outline=CRT_FG, fill=CRT_FG, width=1)
            c.create_rectangle(self.fx(cx+eye_dx-3), self.fy(cy-eye_h), self.fx(cx+eye_dx+3), self.fy(cy+eye_h), outline=CRT_FG, fill=CRT_FG, width=1)

        # näsa ┘
        c.create_line(self.fx(cx), self.fy(cy-8), self.fx(cx), self.fy(cy+14), fill=CRT_FG, width=lw)
        c.create_line(self.fx(cx), self.fy(cy+14), self.fx(cx+10), self.fy(cy+14), fill=CRT_FG, width=lw)

        # mun: öppna/stäng beroende på is_speaking
        t = time.time()
        if getattr(self.audio, "is_speaking", False):
            phase = (math.sin(t*10) + 1)/2  # 0..1
            open_h = 4 + int(10*phase)
            c.create_rectangle(self.fx(cx-14), self.fy(cy+22-open_h), self.fx(cx+14), self.fy(cy+22+open_h),
                            outline=CRT_FG, fill=CRT_FG, width=1)
        else:
            # leende
            c.create_line(self.fx(cx-24), self.fy(cy+26), self.fx(cx), self.fy(cy+34), fill=CRT_FG, width=lw)
            c.create_line(self.fx(cx), self.fy(cy+34), self.fx(cx+24), self.fy(cy+26), fill=CRT_FG, width=lw)


    def redraw_loop(self):
        self.draw_world()
        self.root.after(250, self.redraw_loop)

    # commands
    def do_cmd(self, cmd):
        if not self.game.running:
            self.tell("The session has ended. Press ESC to quit.", speak=False); return
        self.tell(f"> {cmd}", speak=False)
        out = self.game.parse(cmd)
        self.draw_world()
        self.tell(out, speak=True if out else False)

    def send_text(self):
        s = self.entry.get().strip()
        if not s: return
        self.entry.delete(0, END)
        self.do_cmd(s)

    def tell(self, text, speak=False):
        self.log_write(text)
        if speak and not self.audio.is_speaking: self.audio.speak(text)
        self.set_status("Ready. Press V to speak.")

    def push_to_talk(self):
        if not (AI_OK and USE_AUDIO): self.set_status("Voice off."); return
        if self.audio.is_speaking: self.set_status("Speaking…"); return
        txt = self.audio.stt_once()
        if txt:
            self.entry.delete(0, END); self.entry.insert(0, txt); self.send_text()
        else:
            self.set_status("…no speech detected.")

    def quit(self):
        try: self.root.destroy()
        except Exception: pass

# ... längst ned i zork/app.py, inuti klassen VoxZorkApp
def run(self):
    self.root.mainloop()

