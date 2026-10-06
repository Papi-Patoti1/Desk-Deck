import tkinter as tk
from tkinter import ttk
import serial
import time
import threading
import json
import os
import sys
import keyboard
import pyautogui
from pynput import mouse
import pystray
from PIL import Image, ImageDraw

COM_PORT = 'COM6'
BAUD_RATE = 9600

# FIX: Force the app to always save/load in the exact folder where the .exe is located
def get_base_path():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

CONFIG_FILE = os.path.join(get_base_path(), 'desk_macros.json')

KEYPAD = [
    ['BTN_1', 'BTN_2', 'BTN_3'],
    ['BTN_4', 'BTN_5', 'BTN_6'],
    ['BTN_7', 'BTN_8', 'BTN_9'],
    ['BTN_*', 'BTN_0', 'BTN_#']
]

class DeskDeckApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Desk Deck - Macro Keypad")
        self.root.geometry("850x750") 
        self.root.minsize(400, 500)
        self.root.configure(bg="#000000")
        
        self.macros = self.load_macros()
        self.entries = {}
        self.btn_frames = {}
        self.current_mode = "full"
        self.serial_connection = None
        self.is_running = True
        self.is_recording = False
        self.tray_icon = None

        self.setup_ui()
        self.check_resize()
        
        self.thread = threading.Thread(target=self.listen_to_arduino, daemon=True)
        self.thread.start()

    def load_macros(self):
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r') as f:
                return json.load(f)
        return {btn: "" for row in KEYPAD for btn in row}

    def save_macros(self):
        for row in KEYPAD:
            for btn in row:
                self.macros[btn] = self.entries[btn].get().strip()
        with open(CONFIG_FILE, 'w') as f:
            json.dump(self.macros, f, indent=4)
            
        self.status_label.config(text="Status: Macros Saved!", fg="#AAAAAA")
        self.root.after(3000, self.reset_status)

    def reset_status(self):
        if self.serial_connection and self.serial_connection.is_open:
            self.status_label.config(text=f"Status: Connected to {COM_PORT}", fg="#AAAAAA")
        else:
            self.status_label.config(text=f"Status: Waiting for {COM_PORT}...", fg="#555555")

    def update_entry(self, btn, text):
        self.entries[btn].config(state=tk.NORMAL)
        self.entries[btn].delete(0, tk.END)
        self.entries[btn].insert(0, text)
        self.is_recording = False

    def record_keybind(self, btn):
        if self.is_recording: return
        self.is_recording = True
        self.update_entry(btn, "Listening... Press combo")
        
        def listen_keys():
            hotkey = keyboard.read_hotkey(suppress=False)
            self.root.after(0, lambda: self.update_entry(btn, f"key:{hotkey}"))

        threading.Thread(target=listen_keys, daemon=True).start()

    def record_mouse_macro(self, btn):
        if self.is_recording: return
        self.is_recording = True
        self.update_entry(btn, "Recording... Press ESC")
        
        clicks = []
        
        def on_click(x, y, button, pressed):
            if pressed:
                btn_name = "left" if button == mouse.Button.left else "right" if button == mouse.Button.right else "middle"
                clicks.append(f"{int(x)},{int(y)},{btn_name}")

        def listen_mouse():
            listener = mouse.Listener(on_click=on_click)
            listener.start()
            keyboard.wait('esc')
            listener.stop()
            macro_str = "mouse:" + ";".join(clicks)
            self.root.after(0, lambda: self.update_entry(btn, macro_str))

        threading.Thread(target=listen_mouse, daemon=True).start()

    def setup_ui(self):
        style = ttk.Style()
        style.theme_use('clam')
        style.configure("TButton", background="#1A1A1A", foreground="#CCCCCC", borderwidth=1, font=("Segoe UI", 9))
        style.map("TButton", background=[("active", "#333333")])

        self.title_label = tk.Label(self.root, text="DESK DECK", bg="#000000", fg="#CCCCCC", font=("Segoe UI", 22, "bold"))
        self.title_label.pack(pady=15)

        grid_frame = tk.Frame(self.root, bg="#000000")
        grid_frame.pack(fill="both", expand=True, padx=30, pady=10)

        for i in range(3):
            grid_frame.columnconfigure(i, weight=1)
        for i in range(4):
            grid_frame.rowconfigure(i, weight=1)

        for r, row in enumerate(KEYPAD):
            for c, btn in enumerate(row):
                tile = tk.Frame(grid_frame, bg="#111111", highlightbackground="#333333", highlightthickness=1)
                tile.grid(row=r, column=c, padx=5, pady=5, sticky="nsew")
                
                lbl_text = btn.replace("BTN_", "")
                lbl = tk.Label(tile, text=lbl_text, bg="#111111", fg="#888888", font=("Segoe UI", 20, "bold"))
                lbl.pack(pady=(10, 2))
                
                entry = tk.Entry(tile, bg="#000000", fg="#CCCCCC", justify="center", insertbackground="#CCCCCC", relief="flat", font=("Segoe UI", 9))
                entry.pack(fill="x", padx=10, ipady=4)
                entry.insert(0, self.macros.get(btn, ""))
                self.entries[btn] = entry
                
                btn_frame = tk.Frame(tile, bg="#111111")
                btn_frame.pack(pady=10)
                self.btn_frames[btn] = btn_frame
                
                key_btn = ttk.Button(btn_frame, text="Set Key", width=9, command=lambda b=btn: self.record_keybind(b))
                key_btn.pack(side="left", padx=2)
                
                mouse_btn = ttk.Button(btn_frame, text="Set Mouse", width=9, command=lambda b=btn: self.record_mouse_macro(b))
                mouse_btn.pack(side="left", padx=2)

        self.save_btn = ttk.Button(self.root, text="Save Settings", command=self.save_macros)
        self.save_btn.pack(pady=10, ipadx=20, ipady=5)

        self.status_label = tk.Label(self.root, text="Status: Connecting...", bg="#000000", fg="#888888", font=("Segoe UI", 10))
        self.status_label.pack(pady=5)

    def check_resize(self):
        width = self.root.winfo_width()
        if width > 1:
            if width < 650 and self.current_mode != "compact":
                self.current_mode = "compact"
                self.apply_compact_mode()
            elif width >= 650 and self.current_mode != "full":
                self.current_mode = "full"
                self.apply_full_mode()
        self.root.after(100, self.check_resize)

    def apply_compact_mode(self):
        self.title_label.config(font=("Segoe UI", 14, "bold"))
        for btn, frame in self.btn_frames.items():
            frame.pack_forget()

    def apply_full_mode(self):
        self.title_label.config(font=("Segoe UI", 22, "bold"))
        for btn, frame in self.btn_frames.items():
            frame.pack(pady=10)

    def listen_to_arduino(self):
        while self.is_running:
            try:
                if not self.serial_connection or not self.serial_connection.is_open:
                    self.serial_connection = serial.Serial(COM_PORT, BAUD_RATE, timeout=0.1)
                    time.sleep(2)
                    self.serial_connection.reset_input_buffer() 
                    self.root.after(0, self.reset_status)

                if self.serial_connection.in_waiting > 0:
                    data = self.serial_connection.readline().decode('utf-8').strip()
                    if data in self.macros and self.macros[data] and not self.is_recording:
                        self.execute_macro(self.macros[data])
                        
            except serial.SerialException:
                self.root.after(0, lambda: self.status_label.config(text=f"Status: Waiting for {COM_PORT}...", fg="#555555"))
                time.sleep(2)
            except Exception as e:
                time.sleep(0.5)

    def execute_macro(self, action):
        if not action: return
        try:
            action_lower = action.lower()
            
            # --- NEW FEATURE: OPEN APPS & LINKS ---
            if action_lower.startswith("run:"):
                target = action[4:].strip() # Preserves exact casing for file paths
                os.startfile(target)
                
            elif action_lower.startswith("mouse:"):
                moves = action_lower[6:].split(";")
                for move in moves:
                    if not move: continue
                    x, y, btn = move.split(",")
                    pyautogui.click(x=int(x), y=int(y), button=btn)
                    time.sleep(0.05)
            elif action_lower.startswith("type:"):
                text = action[5:] # Preserves casing so uppercase letters type correctly
                keyboard.write(text, delay=0.01)
                
            elif action_lower in ['playpause', 'nexttrack', 'prevtrack', 'volumemute', 'volumeup', 'volumedown']:
                pyautogui.press(action_lower)
                
            else:
                if action_lower.startswith("key:"):
                    action_lower = action_lower[4:]
                
                keys = action_lower.split("+")
                for k in keys:
                    keyboard.press(k)
                time.sleep(0.05) 
                for k in reversed(keys):
                    keyboard.release(k)
                    
        except Exception as e:
            print(f"Macro Execution Error: {e}")

    def create_tray_image(self):
        image = Image.new('RGB', (64, 64), color=(17, 17, 17))
        draw = ImageDraw.Draw(image)
        draw.rectangle((16, 16, 48, 48), fill=(85, 85, 85))
        return image

    def restore_window(self, icon, item):
        self.tray_icon.stop()
        self.root.after(0, self.root.deiconify)

    def quit_app(self, icon, item):
        self.tray_icon.stop()
        self.is_running = False
        if self.serial_connection and self.serial_connection.is_open:
            self.serial_connection.close()
        self.root.after(0, self.root.destroy)

    def on_close(self):
        self.root.withdraw()
        image = self.create_tray_image()
        menu = pystray.Menu(
            pystray.MenuItem('Open Desk Deck', self.restore_window),
            pystray.MenuItem('Quit', self.quit_app)
        )
        self.tray_icon = pystray.Icon("desk_deck", image, "Desk Deck", menu)
        threading.Thread(target=self.tray_icon.run, daemon=True).start()

if __name__ == "__main__":
    root = tk.Tk()
    app = DeskDeckApp(root)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()