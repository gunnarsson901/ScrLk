from .world import WORLD, DIRS

class Game:
    def __init__(self):
        self.room = "west_of_house"
        self.inv = []
        self.lamp_on = False
        self.running = True
        self.messages = []

    def add_msg(self, s): self.messages.append(s); return s

    def look(self):
        r = WORLD[self.room]
        text = f"{r['name']}\n{r['desc']}"
        if r["items"]:
            text += "\nYou see: " + ", ".join(r["items"]) + "."
        exits = ", ".join(r["exits"].keys())
        if exits: text += f"\nExits: {exits}."
        return text

    def move(self, direction):
        r = WORLD[self.room]
        if direction not in r["exits"]: return self.add_msg("You can't go that way.")
        dest = r["exits"][direction]
        if self.room == "cellar" and direction == "north":
            pass  # här kan du lägga dörrlogik
        self.room = dest
        if self.room == "cellar" and not self.lamp_on:
            return self.add_msg("It's very dark. Your lamp would help. " + self.look())
        return self.add_msg(self.look())

    def take(self, item):
        r = WORLD[self.room]
        if item in r["items"]:
            self.inv.append(item); r["items"].remove(item)
            return self.add_msg(f"Taken {item}.")
        return self.add_msg("You don't see that here.")

    def drop(self, item):
        if item in self.inv:
            self.inv.remove(item); WORLD[self.room]["items"].append(item)
            return self.add_msg(f"Dropped {item}.")
        return self.add_msg("You're not carrying that.")

    def open(self, what): return self.add_msg("It won't open.")
    def unlock(self, what): return self.add_msg("That doesn't seem to need unlocking.")
    def use(self, what): return self.light() if what == "lamp" else self.add_msg("How do you want to use that?")
    def read(self, what):
        if what == "leaflet" and (what in self.inv or what in WORLD[self.room]["items"]):
            return self.add_msg("The leaflet says: 'LIGHT HELPS BELOW.'")
        return self.add_msg("There's nothing to read.")
    def light(self):
        if "lamp" in self.inv:
            self.lamp_on = True; return self.add_msg("You switch on the brass lamp. The gloom retreats.")
        return self.add_msg("You don't have a lamp.")
    def inventory(self):
        return self.add_msg("You are empty-handed.") if not self.inv else self.add_msg("You carry: " + ", ".join(self.inv) + ".")

    def parse(self, raw):
        s = raw.strip().lower()
        if not s: return ""
        if s in ("quit","exit"): self.running = False; return "Goodbye."
        if s in ("look","l"):    return self.look()
        if s in ("inventory","i","inv"): return self.inventory()
        toks = [DIRS.get(t, t) for t in s.split()]
        if not toks: return "?"
        v = toks[0]
        if v in ("north","south","east","west","up","down"): return self.move(v)
        if v == "go" and len(toks) >= 2: return self.move(toks[1])
        if v == "take" and len(toks) >= 2: return self.take(toks[-1])
        if v == "drop" and len(toks) >= 2: return self.drop(toks[-1])
        if v == "open" and len(toks) >= 2: return self.open(" ".join(toks[1:]))
        if v == "unlock" and len(toks) >= 2: return self.unlock(" ".join(toks[1:]))
        if v == "use" and len(toks) >= 2: return self.use(toks[-1])
        if v == "read" and len(toks) >= 2: return self.read(toks[-1])
        if v == "light": return self.light()
        return self.add_msg("I don't understand that.")
