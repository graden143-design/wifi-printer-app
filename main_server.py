"""
====================================================================
 Universal Client-Server LAN Print Station (Enterprise 2026)
 Features:
   - Windows Printers & Scanners Direct IP Port Installer
   - Responsive Scaling UI Layout
   - Full Visual Content Preview (.docx, .pdf, .png, .jpg)
   - Host GDI Spooler Bypass for Canon G1020 Series
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
from PIL import Image, ImageTk, ImageDraw, ImageFont

# Optional Preview & Win32 Modules
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

try:
    import docx
    DOCX_AVAILABLE = True
except ImportError:
    DOCX_AVAILABLE = False

try:
    from pdf2image import convert_from_path
    PDF2IMAGE_AVAILABLE = True
except ImportError:
    PDF2IMAGE_AVAILABLE = False

PORT = 9100
BROADCAST_PORT = 9101
CONFIG_FILE = "connected_printers.json"

# --- UTILITY & WINDOWS INTEGRATION ---
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

def add_windows_direct_ip_printer(host_ip, printer_alias="LAN Network Canon G1020"):
    """Installs a Standard TCP/IP Port in Windows using auto-detected existing drivers."""
    port_name = f"IP_{host_ip}"
    
    # 1. Dynamically find an existing driver on this client PC
    ps_get_drivers = '(Get-PrinterDriver).Name'
    proc_drv = subprocess.run(["powershell", "-Command", ps_get_drivers], capture_output=True, text=True)
    installed_drivers = [d.strip() for d in proc_drv.stdout.splitlines() if d.strip()]

    # Priority driver order to avoid "Driver does not exist" errors
    selected_driver = None
    preferred_drivers = [
        "Canon G1020 series",
        "Canon G1000 series",
        "Generic / Text Only",
        "Microsoft Print to PDF",
        "Microsoft XPS Document Writer"
    ]

    for pref in preferred_drivers:
        if pref in installed_drivers:
            selected_driver = pref
            break

    if not selected_driver and installed_drivers:
        selected_driver = installed_drivers[0]

    if not selected_driver:
        return False, "No valid printer drivers found on this PC."

    try:
        # 2. Create Standard TCP/IP Port silently (ignore error if port already exists)
        ps_port_cmd = f'if (-not (Get-PrinterPort -Name "{port_name}" -ErrorAction SilentlyContinue)) {{ Add-PrinterPort -Name "{port_name}" -PrinterHostAddress "{host_ip}" -PortNumber 9100 }}'
        subprocess.run(["powershell", "-Command", ps_port_cmd], capture_output=True, text=True)

        # 3. Add Printer using guaranteed existing system driver
        ps_print_cmd = f'if (-not (Get-Printer -Name "{printer_alias}" -ErrorAction SilentlyContinue)) {{ Add-Printer -Name "{printer_alias}" -DriverName "{selected_driver}" -PortName "{port_name}" }}'
        res = subprocess.run(["powershell", "-Command", ps_print_cmd], capture_output=True, text=True)

        if res.returncode == 0:
            return True, f"Successfully added '{printer_alias}' using driver '{selected_driver}'!"
        else:
            return False, f"PowerShell Error: {res.stderr or res.stdout}"
            
    except Exception as e:
        return False, str(e)

def fix_canon_spooler_locks():
    try:
        subprocess.run(["taskkill", "/F", "/IM", "splwow64.exe"], capture_output=True, timeout=5)
    except Exception:
        pass

def print_file_canon_fixed(printer_name, filepath):
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"File missing: {filepath}")

    fix_canon_spooler_locks()

    if WIN32_AVAILABLE:
        try:
            old_default = win32print.GetDefaultPrinter()
            win32print.SetDefaultPrinter(printer_name)

            res = win32api.ShellExecute(0, "print", filepath, f'"{printer_name}"', ".", 0)
            if int(res) > 32:
                time.sleep(2)
                return
        except Exception:
            pass
        finally:
            try:
                win32print.SetDefaultPrinter(old_default)
            except Exception:
                pass

    ps_cmd = f'Start-Process -FilePath "{filepath}" -Verb PrintTo -ArgumentList "`"{printer_name}`"" -WindowStyle Hidden'
    proc = subprocess.run(["powershell", "-Command", ps_cmd], capture_output=True, text=True, timeout=20)
    if proc.returncode != 0:
        raise Exception("Canon driver failed to accept job. Check USB cable.")

def recv_exact(sock, length):
    data = bytearray()
    while len(data) < length:
        packet = sock.recv(length - len(data))
        if not packet:
            return None
        data.extend(packet)
    return bytes(data)

# --- SERVER ENGINE ---
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
                temp_path = os.path.join(temp_dir, f"lan_job_{int(time.time())}_{file_name}")

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

# --- RESPONSIVE GUI APP ---
class AppGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Universal LAN Print Station - Enterprise 2026")
        self.root.geometry("750x750")
        self.root.minsize(650, 600)
        self.root.configure(bg="#f8fafc")

        # Configure root grid responsiveness
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        self.mode = None
        self.host_ip = None
        self.preview_image_ref = None

        self.main_container = tk.Frame(self.root, bg="#f8fafc")
        self.main_container.grid(row=0, column=0, sticky="nsew", padx=15, pady=15)
        self.main_container.columnconfigure(0, weight=1)

        self.setup_welcome_screen()

    def setup_welcome_screen(self):
        for widget in self.main_container.winfo_children():
            widget.destroy()

        tk.Label(self.main_container, text="🖨️ Enterprise LAN Print Station", font=("Segoe UI", 16, "bold"), bg="#f8fafc", fg="#0f172a").pack(pady=(20, 2))
        
        frame = tk.LabelFrame(self.main_container, text=" Operating Mode ", font=("Segoe UI", 10, "bold"), bg="#f8fafc", fg="#0284c7", padx=20, pady=20)
        frame.pack(fill="both", expand=True, pady=15)

        tk.Button(frame, text="🖥️ Host Mode (Connected to Physical Canon Printer)", command=self.start_host_mode, font=("Segoe UI", 11, "bold"), bg="#0284c7", fg="white", relief="flat", pady=12).pack(fill="x", pady=10)
        tk.Button(frame, text="💻 Client Mode (Send Jobs & Install Windows Printer)", command=self.start_client_mode, font=("Segoe UI", 11, "bold"), bg="#475569", fg="white", relief="flat", pady=12).pack(fill="x", pady=10)

    # --- CLIENT MODE WITH RESPONSIVE LAYOUT ---
    def start_client_mode(self):
        self.mode = "CLIENT"
        for widget in self.main_container.winfo_children():
            widget.destroy()

        self.main_container.rowconfigure(5, weight=1)  # Preview Canvas expands dynamically

        tk.Label(self.main_container, text="💻 CLIENT PRINT STATION", font=("Segoe UI", 14, "bold"), bg="#f8fafc", fg="#0284c7").grid(row=0, column=0, sticky="w", pady=(0, 5))

        # Toolbar Frame
        tb = tk.Frame(self.main_container, bg="#f8fafc")
        tb.grid(row=1, column=0, sticky="ew", pady=5)
        tb.columnconfigure(1, weight=1)

        tk.Label(tb, text="Host IP:", font=("Segoe UI", 9, "bold"), bg="#f8fafc").grid(row=0, column=0, padx=(0, 5))
        self.ip_entry = tk.Entry(tb, font=("Segoe UI", 9))
        self.ip_entry.grid(row=0, column=1, sticky="ew", padx=5)
        tk.Button(tb, text="Connect", command=self.manual_connect, font=("Segoe UI", 8, "bold"), bg="#0284c7", fg="white", relief="flat").grid(row=0, column=2, padx=2)
        
        # Feature 1: Install Printer in Windows Settings Menu
        tk.Button(tb, text="⚙️ Add to Windows Printers Menu", command=self.install_to_windows_menu, font=("Segoe UI", 8, "bold"), bg="#d97706", fg="white", relief="flat").grid(row=0, column=3, padx=2)

        # Target Printer Box
        p_frame = tk.Frame(self.main_container, bg="#f8fafc")
        p_frame.grid(row=2, column=0, sticky="ew", pady=5)
        p_frame.columnconfigure(0, weight=1)

        tk.Label(p_frame, text="Target Printer:", font=("Segoe UI", 9, "bold"), bg="#f8fafc").pack(anchor="w")
        self.printer_combo = ttk.Combobox(p_frame, state="readonly", font=("Segoe UI", 9))
        self.printer_combo.pack(fill="x", pady=2)

        # File Chooser
        f_frame = tk.Frame(self.main_container, bg="#f8fafc")
        f_frame.grid(row=3, column=0, sticky="ew", pady=5)
        f_frame.columnconfigure(0, weight=1)

        tk.Label(f_frame, text="Select File (PDF, DOCX, Images):", font=("Segoe UI", 9, "bold"), bg="#f8fafc").pack(anchor="w")
        file_box = tk.Frame(f_frame, bg="#f8fafc")
        file_box.pack(fill="x")
        self.file_entry = tk.Entry(file_box, font=("Segoe UI", 9))
        self.file_entry.pack(side="left", fill="x", expand=True, padx=(0, 5))
        tk.Button(file_box, text="Browse...", command=self.browse_file, font=("Segoe UI", 8, "bold")).pack(side="right")

        # Feature 2: Content Visual Print Preview Canvas
        prev_frame = tk.LabelFrame(self.main_container, text=" Document Visual Content Preview ", font=("Segoe UI", 9, "bold"), bg="#f8fafc", padx=5, pady=5)
        prev_frame.grid(row=5, column=0, sticky="nsew", pady=10)
        prev_frame.columnconfigure(0, weight=1)
        prev_frame.rowconfigure(0, weight=1)

        self.preview_canvas = tk.Canvas(prev_frame, bg="#334155", highlightthickness=0)
        self.preview_canvas.grid(row=0, column=0, sticky="nsew")

        tk.Button(self.main_container, text="🖨️ Send Print Job to Host", command=self.send_print_job, font=("Segoe UI", 11, "bold"), bg="#166534", fg="white", relief="flat", pady=10).grid(row=6, column=0, sticky="ew", pady=(5, 0))

    def install_to_windows_menu(self):
        host_ip = self.ip_entry.get().strip() if hasattr(self, 'ip_entry') else ""
        if not host_ip:
            messagebox.showwarning("Missing IP", "Please enter or connect to a Host IP first.")
            return

        success, msg = add_windows_direct_ip_printer(host_ip)
        if success:
            messagebox.showinfo("Windows Integration", f"{msg}\n\nYou can now print directly from Word, Chrome, or Email by selecting this printer in Windows!")
        else:
            messagebox.showerror("Installation Failed", f"Could not create Windows IP printer port:\n{msg}")

    def browse_file(self):
        f = filedialog.askopenfilename(title="Select Document", filetypes=[("Printable Files", "*.pdf;*.docx;*.png;*.jpg;*.jpeg;*.txt")])
        if f:
            self.file_entry.delete(0, tk.END)
            self.file_entry.insert(0, f)
            self.render_content_preview(f)

    # Feature 2: Renders Real Document Text & Image Content
    def render_content_preview(self, filepath):
        self.preview_canvas.delete("all")
        self.root.update_idletasks()
        
        cw = self.preview_canvas.winfo_width()
        ch = self.preview_canvas.winfo_height()
        if cw < 50: cw = 500
        if ch < 50: ch = 300

        ext = os.path.splitext(filepath)[1].lower()

        try:
            if ext in ['.png', '.jpg', '.jpeg']:
                img = Image.open(filepath)
                img.thumbnail((cw - 20, ch - 20))
                self.preview_image_ref = ImageTk.PhotoImage(img)
                self.preview_canvas.create_image(cw // 2, ch // 2, image=self.preview_image_ref)

            elif ext == '.docx' and DOCX_AVAILABLE:
                doc = docx.Document(filepath)
                text_content = "\n".join([p.text for p in doc.paragraphs if p.text.strip()][:12])
                
                # Render virtual sheet of paper on Canvas
                page_img = Image.new("RGB", (400, 500), "white")
                draw = ImageDraw.Draw(page_img)
                draw.text((20, 20), f"[Word Document Content Preview]\n\n{text_content[:400]}...", fill="black")
                
                page_img.thumbnail((cw - 20, ch - 20))
                self.preview_image_ref = ImageTk.PhotoImage(page_img)
                self.preview_canvas.create_image(cw // 2, ch // 2, image=self.preview_image_ref)

            elif ext == '.pdf':
                if PDF2IMAGE_AVAILABLE:
                    images = convert_from_path(filepath, first_page=1, last_page=1)
                    if images:
                        img = images[0]
                        img.thumbnail((cw - 20, ch - 20))
                        self.preview_image_ref = ImageTk.PhotoImage(img)
                        self.preview_canvas.create_image(cw // 2, ch // 2, image=self.preview_image_ref)
                        return
                
                # Fallback PDF preview drawing
                page_img = Image.new("RGB", (400, 500), "#f8fafc")
                draw = ImageDraw.Draw(page_img)
                draw.text((30, 40), f"PDF DOCUMENT\n\nFile: {os.path.basename(filepath)}", fill="#0f172a")
                page_img.thumbnail((cw - 20, ch - 20))
                self.preview_image_ref = ImageTk.PhotoImage(page_img)
                self.preview_canvas.create_image(cw // 2, ch // 2, image=self.preview_image_ref)

            else:
                self.preview_canvas.create_text(cw // 2, ch // 2, text=f"File Selected:\n{os.path.basename(filepath)}", fill="white", font=("Segoe UI", 11))

        except Exception as e:
            self.preview_canvas.create_text(cw // 2, ch // 2, text=f"Preview Render Error:\n{str(e)}", fill="#f87171", font=("Segoe UI", 9))

    def manual_connect(self):
        ip = self.ip_entry.get().strip()
        if ip:
            self.host_ip = ip
            self.fetch_host_printers()

    def fetch_host_printers(self):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(4.0)
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
            messagebox.showinfo("Success", f"Connected to Host Server {self.host_ip}!")
        except Exception as e:
            messagebox.showerror("Error", f"Connection failed: {str(e)}")

    def send_print_job(self):
        filepath = self.file_entry.get().strip()
        printer_name = self.printer_combo.get()

        if not filepath or not os.path.exists(filepath) or not printer_name:
            messagebox.showwarning("Warning", "Select printer and file.")
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
                    messagebox.showinfo("Success", f"Print job sent to {printer_name}!")
            s.close()
        except Exception as e:
            messagebox.showerror("Error", f"Print job failed: {str(e)}")

    def start_host_mode(self):
        self.mode = "HOST"
        for widget in self.main_container.winfo_children():
            widget.destroy()

        ip_addresses = get_all_local_ips()
        printers, _ = get_installed_printers()

        tk.Label(self.main_container, text="🖥️ HOST PRINT SERVER", font=("Segoe UI", 15, "bold"), bg="#f8fafc", fg="#166534").pack(pady=(10, 2))
        tk.Label(self.main_container, text=f"Host IPs: {' | '.join(ip_addresses)}", font=("Segoe UI", 10, "bold"), bg="#e2e8f0").pack(pady=5)

        log_frame = tk.LabelFrame(self.main_container, text=" Activity Log ", font=("Segoe UI", 9, "bold"), bg="#f8fafc", padx=10, pady=10)
        log_frame.pack(fill="both", expand=True, pady=10)

        self.log_box = tk.Text(log_frame, font=("Consolas", 9), state="disabled", bg="#0f172a", fg="#38bdf8")
        self.log_box.pack(fill="both", expand=True)

        self.server_instance = PrintServer(self.log_message)
        self.server_instance.start()
        self.log_message("Host print server online.")

    def log_message(self, msg):
        if hasattr(self, 'log_box'):
            self.log_box.config(state="normal")
            self.log_box.insert(tk.END, f"[{time.strftime('%H:%M:%S')}] {msg}\n")
            self.log_box.see(tk.END)
            self.log_box.config(state="disabled")

if __name__ == "__main__":
    root = tk.Tk()
    app = AppGUI(root)
    root.protocol("WM_DELETE_WINDOW", lambda: os._exit(0))
    root.mainloop()
