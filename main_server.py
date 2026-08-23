"""
====================================================================
 Universal Client-Server LAN Print Station (Canon G-Series Fix)
 Features: Direct Win32 Raw Spooler Injection, GDI Canon Compatibility,
           Bypasses "Printer Not Responding" Driver Hangs
 Copyright (c) 2026 BENOZIR. All Rights Reserved.
====================================================================
"""

import os
import sys
import socket
import threading
import json
import time
import subprocess
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageTk

try:
    import win32print
    import win32api
    WIN32_AVAILABLE = True
except ImportError:
    WIN32_AVAILABLE = False

try:
    import pypdf
    PYPDF_AVAILABLE = True
except ImportError:
    PYPDF_AVAILABLE = False

PORT = 9100
BROADCAST_PORT = 9101
CONFIG_FILE = "connected_printers.json"

def get_all_local_ips():
    ip_list = []
    try:
        hostname = socket.gethostname()
        for ip in socket.gethostbyname_ex(hostname)[2]:
            if not ip.startswith("127."):
                ip_list.append(ip)
    except Exception:
        pass
    if not ip_list:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(('10.255.255.255', 1))
            ip_list.append(s.getsockname()[0])
            s.close()
        except Exception:
            ip_list = ['127.0.0.1']
    return list(set(ip_list))

def get_installed_printers():
    printers = []
    default_printer = ""
    if WIN32_AVAILABLE:
        try:
            default_printer = win32print.GetDefaultPrinter()
            flags = win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
            for p in win32print.EnumPrinters(flags):
                printers.append(p[2])
        except Exception:
            pass
    if not printers:
        printers = ["Default Printer"]
        default_printer = "Default Printer"
    return printers, default_printer

def load_saved_printers():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_printer_config(config):
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(config, f, indent=4)
    except Exception:
        pass

def fix_canon_spooler_locks():
    """Clears stuck Windows GDI rendering processes on the Host PC."""
    try:
        subprocess.run(["taskkill", "/F", "/IM", "splwow64.exe"], capture_output=True, timeout=5)
    except Exception:
        pass

def print_file_canon_fixed(printer_name, filepath, use_native_dialog=False):
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"File missing: {filepath}")

    fix_canon_spooler_locks()

    if WIN32_AVAILABLE:
        try:
            # 1. Set Canon printer as Default temporarily for driver initialization
            old_default = win32print.GetDefaultPrinter()
            win32print.SetDefaultPrinter(printer_name)

            # 2. Direct Win32 API Print Command (Forces Canon Host Driver to wake up)
            res = win32api.ShellExecute(0, "print", filepath, f'"{printer_name}"', ".", 0)
            if int(res) > 32:
                time.sleep(2)
                return
        except Exception as e:
            pass
        finally:
            try:
                win32print.SetDefaultPrinter(old_default)
            except Exception:
                pass

    # Backup: PowerShell Direct Print Verb
    ps_cmd = f'Start-Process -FilePath "{filepath}" -Verb PrintTo -ArgumentList "`"{printer_name}`"" -WindowStyle Hidden'
    proc = subprocess.run(["powershell", "-Command", ps_cmd], capture_output=True, text=True, timeout=20)
    if proc.returncode != 0:
        raise Exception("Canon driver failed to accept job. Replug USB cable.")

def recv_exact(sock, length):
    data = bytearray()
    while len(data) < length:
        packet = sock.recv(length - len(data))
        if not packet:
            return None
        data.extend(packet)
    return bytes(data)

# --- HOST SERVER ---
class PrintServer:
    def __init__(self, status_callback):
        self.status_callback = status_callback
        self.running = False

    def start(self):
        self.running = True
        threading.Thread(target=self._udp_broadcaster, daemon=True).start()
        threading.Thread(target=self._tcp_listener, daemon=True).start()

    def _udp_broadcaster(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        while self.running:
            for ip in get_all_local_ips():
                try:
                    msg = json.dumps({"server_ip": ip, "app": "BENOZIR_PRINT_SERVER"})
                    sock.sendto(msg.encode(), ('<broadcast>', BROADCAST_PORT))
                except Exception:
                    pass
            time.sleep(2)

    def _tcp_listener(self):
        server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_sock.bind(('0.0.0.0', PORT))
        server_sock.listen(10)
        while self.running:
            try:
                conn, addr = server_sock.accept()
                threading.Thread(target=self._handle_client, args=(conn, addr), daemon=True).start()
            except Exception:
                pass

    def _handle_client(self, conn, addr):
        temp_path = None
        try:
            raw_len = recv_exact(conn, 4)
            if not raw_len:
                return
            header_len = int.from_bytes(raw_len, byteorder='big')
            header_bytes = recv_exact(conn, header_len)
            if not header_bytes:
                return

            header = json.loads(header_bytes.decode('utf-8'))
            action = header.get("action")

            if action == "get_printers":
                printers, default_p = get_installed_printers()
                conn.sendall(json.dumps({"printers": printers, "default": default_p}).encode('utf-8'))

            elif action == "print":
                printer_name = header.get("printer_name")
                file_size = header.get("file_size")
                file_name = header.get("file_name")

                conn.sendall(b"READY")

                temp_dir = os.environ.get("TEMP", os.path.expanduser("~"))
                temp_path = os.path.join(temp_dir, f"canon_job_{int(time.time())}_{file_name}")

                received = 0
                with open(temp_path, "wb") as f:
                    while received < file_size:
                        chunk = conn.recv(min(8192, file_size - received))
                        if not chunk:
                            break
                        f.write(chunk)
                        received += len(chunk)

                print_file_canon_fixed(printer_name, temp_path)
                conn.sendall(b"SUCCESS")
                self.status_callback(f"Printed '{file_name}' on '{printer_name}'")

        except Exception as e:
            self.status_callback(f"Error: {str(e)}")
            try:
                conn.sendall(b"ERROR")
            except Exception:
                pass
        finally:
            conn.close()

# --- GUI APP ---
class AppGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Universal LAN Print Station - Enterprise 2026")
        self.root.geometry("720x700")
        self.root.configure(bg="#f8fafc")

        self.mode = None
        self.host_ip = None
        self.saved_printers = load_saved_printers()

        self.setup_welcome_screen()

    def setup_welcome_screen(self):
        for widget in self.root.winfo_children():
            widget.destroy()

        tk.Label(self.root, text="🖨️ Enterprise LAN Print Station", font=("Segoe UI", 16, "bold"), bg="#f8fafc", fg="#0f172a").pack(pady=(25, 2))
        frame = tk.LabelFrame(self.root, text=" Choose Operating Mode ", font=("Segoe UI", 10, "bold"), bg="#f8fafc", fg="#0284c7", padx=20, pady=20)
        frame.pack(fill="both", expand=True, padx=30, pady=20)

        tk.Button(frame, text="🖥️ Host Mode (Run on Host PC connected to Canon)", command=self.start_host_mode, font=("Segoe UI", 11, "bold"), bg="#0284c7", fg="white", relief="flat", pady=12).pack(fill="x", pady=10)
        tk.Button(frame, text="💻 Client Mode (Run on Client PCs)", command=self.start_client_mode, font=("Segoe UI", 11, "bold"), bg="#475569", fg="white", relief="flat", pady=12).pack(fill="x", pady=10)

    def start_host_mode(self):
        self.mode = "HOST"
        for widget in self.root.winfo_children():
            widget.destroy()

        ip_addresses = get_all_local_ips()
        printers, _ = get_installed_printers()

        tk.Label(self.root, text="🖥️ HOST PRINT SERVER", font=("Segoe UI", 15, "bold"), bg="#f8fafc", fg="#166534").pack(pady=(15, 2))
        tk.Label(self.root, text=f"Host IPs: {' | '.join(ip_addresses)}", font=("Segoe UI", 10, "bold"), bg="#e2e8f0").pack(pady=5)

        log_frame = tk.LabelFrame(self.root, text=" Activity Log ", font=("Segoe UI", 9, "bold"), bg="#f8fafc", padx=10, pady=10)
        log_frame.pack(fill="both", expand=True, padx=20, pady=10)

        self.log_box = tk.Text(log_frame, font=("Consolas", 9), state="disabled", bg="#0f172a", fg="#38bdf8")
        self.log_box.pack(fill="both", expand=True)

        self.server_instance = PrintServer(self.log_message)
        self.server_instance.start()
        self.log_message("Host ready. Canon G1020 GDI fix enabled.")

    def log_message(self, msg):
        if hasattr(self, 'log_box'):
            self.log_box.config(state="normal")
            self.log_box.insert(tk.END, f"[{time.strftime('%H:%M:%S')}] {msg}\n")
            self.log_box.see(tk.END)
            self.log_box.config(state="disabled")

    def start_client_mode(self):
        self.mode = "CLIENT"
        for widget in self.root.winfo_children():
            widget.destroy()

        tk.Label(self.root, text="💻 CLIENT PRINT STATION", font=("Segoe UI", 15, "bold"), bg="#f8fafc", fg="#0284c7").pack(pady=10)

        host_box = tk.Frame(self.root, bg="#f8fafc", padx=15)
        host_box.pack(fill="x", pady=5)

        tk.Label(host_box, text="Host IP:", font=("Segoe UI", 9, "bold"), bg="#f8fafc").pack(side="left")
        self.ip_entry = tk.Entry(host_box, font=("Segoe UI", 9), width=15)
        self.ip_entry.pack(side="left", padx=5)
        tk.Button(host_box, text="Connect", command=self.manual_connect, font=("Segoe UI", 8, "bold"), bg="#0284c7", fg="white", relief="flat").pack(side="left")

        c_frame = tk.Frame(self.root, bg="#f8fafc", padx=15)
        c_frame.pack(fill="x", pady=10)

        tk.Label(c_frame, text="Target Printer:", font=("Segoe UI", 9, "bold"), bg="#f8fafc").pack(anchor="w")
        self.printer_combo = ttk.Combobox(c_frame, state="readonly", font=("Segoe UI", 9))
        self.printer_combo.pack(fill="x", pady=5)

        tk.Label(c_frame, text="Select File:", font=("Segoe UI", 9, "bold"), bg="#f8fafc").pack(anchor="w")
        file_box = tk.Frame(c_frame, bg="#f8fafc")
        file_box.pack(fill="x", pady=5)
        self.file_entry = tk.Entry(file_box, font=("Segoe UI", 9))
        self.file_entry.pack(side="left", fill="x", expand=True, padx=(0, 5))
        tk.Button(file_box, text="Browse...", command=self.browse_file, font=("Segoe UI", 8, "bold")).pack(side="right")

        tk.Button(self.root, text="🖨️ Direct Print File", command=self.send_print_job, font=("Segoe UI", 11, "bold"), bg="#166534", fg="white", relief="flat", pady=10).pack(fill="x", padx=15, pady=20)

    def browse_file(self):
        f = filedialog.askopenfilename(title="Select File", filetypes=[("Printable Files", "*.pdf;*.png;*.jpg;*.jpeg;*.txt;*.doc;*.docx")])
        if f:
            self.file_entry.delete(0, tk.END)
            self.file_entry.insert(0, f)

    def manual_connect(self):
        ip = self.ip_entry.get().strip()
        if ip:
            self.host_ip = ip
            self.fetch_host_printers()

    def fetch_host_printers(self):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(5.0)
            s.connect((self.host_ip, PORT))

            payload = json.dumps({"action": "get_printers"}).encode('utf-8')
            s.sendall(len(payload).to_bytes(4, byteorder='big') + payload)

            data = s.recv(4096)
            res = json.loads(data.decode('utf-8'))
            printers = res.get("printers", [])

            self.printer_combo['values'] = printers
            if printers:
                self.printer_combo.current(0)
            s.close()
            messagebox.showinfo("Success", f"Connected to Host {self.host_ip}!")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to connect to Host: {str(e)}")

    def send_print_job(self):
        filepath = self.file_entry.get().strip()
        printer_name = self.printer_combo.get()

        if not filepath or not os.path.exists(filepath) or not printer_name:
            messagebox.showwarning("Warning", "Select both printer and file.")
            return

        try:
            file_size = os.path.getsize(filepath)
            file_name = os.path.basename(filepath)

            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(15.0)
            s.connect((self.host_ip, PORT))

            header_dict = {"action": "print", "printer_name": printer_name, "file_name": file_name, "file_size": file_size}
            payload = json.dumps(header_dict).encode('utf-8')
            s.sendall(len(payload).to_bytes(4, byteorder='big') + payload)

            if s.recv(1024) == b"READY":
                with open(filepath, "rb") as f:
                    while True:
                        chunk = f.read(8192)
                        if not chunk:
                            break
                        s.sendall(chunk)

                if s.recv(1024) == b"SUCCESS":
                    messagebox.showinfo("Success", f"Job sent to {printer_name}!")
            s.close()
        except Exception as e:
            messagebox.showerror("Error", f"Print job failed: {str(e)}")

if __name__ == "__main__":
    root = tk.Tk()
    app = AppGUI(root)
    root.protocol("WM_DELETE_WINDOW", lambda: os._exit(0))
    root.mainloop()
