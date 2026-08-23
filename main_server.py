"""
====================================================================
 Universal Client-Server LAN Print Station (Enterprise Edition)
 Features: Direct File Menu Bar, Hotkeys (Ctrl+O, Ctrl+P),
           Print Preview, Page Ranges, Native Windows Print Dialogs
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
from tkinter import ttk, filedialog, messagebox, simpledialog
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

# --- UTILITY & NETWORK FUNCTIONS ---
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

def parse_page_range(range_str, max_pages):
    if not range_str or range_str.strip().lower() == "all":
        return list(range(max_pages))
    
    pages = set()
    parts = range_str.split(',')
    for part in parts:
        part = part.strip()
        if '-' in part:
            try:
                start, end = map(int, part.split('-'))
                for p in range(start, end + 1):
                    if 1 <= p <= max_pages:
                        pages.add(p - 1)
            except ValueError:
                pass
        else:
            try:
                p = int(part)
                if 1 <= p <= max_pages:
                    pages.add(p - 1)
            except ValueError:
                pass
    return sorted(list(pages))

def slice_pdf_file(input_path, output_path, pages_to_keep):
    if not PYPDF_AVAILABLE:
        return False
    reader = pypdf.PdfReader(input_path)
    writer = pypdf.PdfWriter()
    for p_idx in pages_to_keep:
        if p_idx < len(reader.pages):
            writer.add_page(reader.pages[p_idx])
    with open(output_path, "wb") as f_out:
        writer.write(f_out)
    return True

def print_file_robust(printer_name, filepath, use_native_dialog=False):
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"Temp file missing: {filepath}")

    ext = os.path.splitext(filepath)[1].lower()

    if use_native_dialog and WIN32_AVAILABLE:
        try:
            old_default = win32print.GetDefaultPrinter()
            win32print.SetDefaultPrinter(printer_name)
            try:
                win32api.ShellExecute(0, "printto", filepath, f'"{printer_name}"', ".", 1)
                time.sleep(3)
                return
            finally:
                win32print.SetDefaultPrinter(old_default)
        except Exception:
            pass

    if ext in ['.pdf', '.doc', '.docx', '.txt', '.png', '.jpg', '.jpeg']:
        try:
            ps_cmd = (
                f'$p = "{printer_name}"; '
                f'$f = "{filepath}"; '
                f'Start-Process -FilePath $f -Verb PrintTo -ArgumentList "`"$p`"" -WindowStyle Hidden -ErrorAction Stop'
            )
            proc = subprocess.run(["powershell", "-Command", ps_cmd], capture_output=True, text=True, timeout=20)
            if proc.returncode == 0:
                time.sleep(3)
                return
        except Exception:
            pass

    if WIN32_AVAILABLE:
        try:
            old_default = win32print.GetDefaultPrinter()
            win32print.SetDefaultPrinter(printer_name)
            try:
                res = win32api.ShellExecute(0, "print", filepath, None, ".", 0)
                if int(res) > 32:
                    time.sleep(3)
                    return
            finally:
                win32print.SetDefaultPrinter(old_default)
        except Exception:
            pass

    raise Exception(f"Failed to submit file to '{printer_name}'. Check driver and default program associations.")

def recv_exact(sock, length):
    data = bytearray()
    while len(data) < length:
        packet = sock.recv(length - len(data))
        if not packet:
            return None
        data.extend(packet)
    return bytes(data)

# --- HOST SERVER CLASS ---
class PrintServer:
    def __init__(self, status_callback):
        self.status_callback = status_callback
        self.running = False

    def start(self):
        self.running = True
        threading.Thread(target=self._udp_multi_broadcaster, daemon=True).start()
        threading.Thread(target=self._tcp_listener, daemon=True).start()

    def _udp_multi_broadcaster(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        while self.running:
            for ip in get_all_local_ips():
                try:
                    msg = json.dumps({"server_ip": ip, "app": "BENOZIR_PRINT_SERVER"})
                    sock.sendto(msg.encode(), ('<broadcast>', BROADCAST_PORT))
                    sock.sendto(msg.encode(), ('255.255.255.255', BROADCAST_PORT))
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

            if action == "ping":
                conn.sendall(json.dumps({"status": "PONG", "app": "BENOZIR_PRINT_SERVER"}).encode('utf-8'))

            elif action == "get_printers":
                printers, default_p = get_installed_printers()
                conn.sendall(json.dumps({"printers": printers, "default": default_p}).encode('utf-8'))

            elif action == "print":
                printer_name = header.get("printer_name")
                file_size = header.get("file_size")
                file_name = header.get("file_name")
                use_native_dialog = header.get("use_native_dialog", False)

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

                print_file_robust(printer_name, temp_path, use_native_dialog)
                conn.sendall(b"SUCCESS")
                self.status_callback(f"Successfully printed '{file_name}' on '{printer_name}'")

        except Exception as e:
            self.status_callback(f"Error from {addr[0]}: {str(e)}")
            try:
                conn.sendall(b"ERROR")
            except Exception:
                pass
        finally:
            conn.close()
            if temp_path and os.path.exists(temp_path):
                def delayed_remove(path):
                    time.sleep(6)
                    try:
                        if os.path.exists(path):
                            os.remove(path)
                    except Exception:
                        pass
                threading.Thread(target=delayed_remove, args=(temp_path,), daemon=True).start()

# --- GUI CLASS WITH FILE MENU BAR ---
class AppGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Universal LAN Print Station - Enterprise 2026")
        self.root.geometry("720x720")
        self.root.configure(bg="#f8fafc")

        self.mode = None
        self.host_ip = None
        self.preview_image_ref = None
        self.selected_file_path = None
        self.total_pages = 1
        self.saved_printers = load_saved_printers()

        self.setup_menu_bar()
        self.setup_welcome_screen()

    def setup_menu_bar(self):
        """Creates top application File Menu Bar."""
        self.menu_bar = tk.Menu(self.root)
        
        # File Menu
        self.file_menu = tk.Menu(self.menu_bar, tearoff=0)
        self.file_menu.add_command(label="📂 Open File...", command=self.browse_file, accelerator="Ctrl+O")
        self.file_menu.add_command(label="🖨️ Direct Print File", command=self.send_print_job, accelerator="Ctrl+P")
        self.file_menu.add_separator()
        self.file_menu.add_command(label="➕ Add Network Printer...", command=self.add_network_printer_dialog)
        self.file_menu.add_separator()
        self.file_menu.add_command(label="❌ Exit", command=self.root.quit)

        self.menu_bar.add_cascade(label="File", menu=self.file_menu)
        
        # Keyboard Shortcuts
        self.root.bind_all("<Control-o>", lambda event: self.browse_file())
        self.root.bind_all("<Control-p>", lambda event: self.send_print_job())
        
        self.root.config(menu=self.menu_bar)

    def setup_welcome_screen(self):
        for widget in self.root.winfo_children():
            widget.destroy()

        tk.Label(self.root, text="🖨️ Enterprise LAN Print Station", font=("Segoe UI", 16, "bold"), bg="#f8fafc", fg="#0f172a").pack(pady=(25, 2))
        tk.Label(self.root, text="Bypasses Windows SMB Share Errors | Native Print Support", font=("Segoe UI", 9), bg="#f8fafc", fg="#64748b").pack(pady=(0, 20))

        frame = tk.LabelFrame(self.root, text=" Choose Operating Mode ", font=("Segoe UI", 10, "bold"), bg="#f8fafc", fg="#0284c7", padx=20, pady=20)
        frame.pack(fill="both", expand=True, padx=30, pady=10)

        tk.Button(frame, text="🖥️ Host Mode\n(Run on PC connected to physical printers)", command=self.start_host_mode, font=("Segoe UI", 11, "bold"), bg="#0284c7", fg="white", relief="flat", pady=12).pack(fill="x", pady=10)
        tk.Button(frame, text="💻 Client Mode\n(Run on network PCs to send print jobs)", command=self.start_client_mode, font=("Segoe UI", 11, "bold"), bg="#475569", fg="white", relief="flat", pady=12).pack(fill="x", pady=10)

    # --- HOST GUI ---
    def start_host_mode(self):
        self.mode = "HOST"
        for widget in self.root.winfo_children():
            widget.destroy()

        ip_addresses = get_all_local_ips()
        printers, _ = get_installed_printers()

        tk.Label(self.root, text="🖥️ HOST PRINT SERVER", font=("Segoe UI", 15, "bold"), bg="#f8fafc", fg="#166534").pack(pady=(15, 2))
        
        ip_frame = tk.Frame(self.root, bg="#e2e8f0", padx=10, pady=6)
        ip_frame.pack(fill="x", padx=20, pady=5)
        tk.Label(ip_frame, text=f"Host IPs:  {' | '.join(ip_addresses)}", font=("Segoe UI", 10, "bold"), bg="#e2e8f0", fg="#0f172a").pack()

        p_frame = tk.LabelFrame(self.root, text=" Active Printers ", font=("Segoe UI", 9, "bold"), bg="#f8fafc", padx=10, pady=10)
        p_frame.pack(fill="x", padx=20, pady=5)

        listbox = tk.Listbox(p_frame, height=4, font=("Segoe UI", 9))
        listbox.pack(fill="x")
        for p in printers:
            listbox.insert(tk.END, f"  • {p}")

        log_frame = tk.LabelFrame(self.root, text=" Print Activity Log ", font=("Segoe UI", 9, "bold"), bg="#f8fafc", padx=10, pady=10)
        log_frame.pack(fill="both", expand=True, padx=20, pady=(0, 15))

        self.log_box = tk.Text(log_frame, font=("Consolas", 9), state="disabled", bg="#0f172a", fg="#38bdf8")
        self.log_box.pack(fill="both", expand=True)

        self.server_instance = PrintServer(self.log_message)
        self.server_instance.start()
        self.log_message("Host server running. Listening for direct TCP print requests...")

    def log_message(self, msg):
        if hasattr(self, 'log_box'):
            self.log_box.config(state="normal")
            self.log_box.insert(tk.END, f"[{time.strftime('%H:%M:%S')}] {msg}\n")
            self.log_box.see(tk.END)
            self.log_box.config(state="disabled")

    # --- CLIENT GUI ---
    def start_client_mode(self):
        self.mode = "CLIENT"
        for widget in self.root.winfo_children():
            widget.destroy()

        tk.Label(self.root, text="💻 CLIENT PRINT STATION", font=("Segoe UI", 15, "bold"), bg="#f8fafc", fg="#0284c7").pack(pady=(10, 2))

        # Host Connect Toolbar
        host_box = tk.Frame(self.root, bg="#f8fafc", padx=15)
        host_box.pack(fill="x", pady=2)

        tk.Label(host_box, text="Host IP:", font=("Segoe UI", 9, "bold"), bg="#f8fafc").pack(side="left")
        self.ip_entry = tk.Entry(host_box, font=("Segoe UI", 9), width=15)
        self.ip_entry.pack(side="left", padx=5)
        
        tk.Button(host_box, text="Connect", command=self.manual_connect, font=("Segoe UI", 8, "bold"), bg="#0284c7", fg="white", relief="flat").pack(side="left", padx=2)
        tk.Button(host_box, text="➕ Add Network Printer", command=self.add_network_printer_dialog, font=("Segoe UI", 8, "bold"), bg="#166534", fg="white", relief="flat").pack(side="right", padx=2)

        self.status_lbl = tk.Label(self.root, text="Searching LAN for Host Server...", font=("Segoe UI", 8, "italic"), bg="#f8fafc", fg="#d97706")
        self.status_lbl.pack(pady=2)

        # Configuration Box
        c_frame = tk.Frame(self.root, bg="#f8fafc", padx=15)
        c_frame.pack(fill="x")

        tk.Label(c_frame, text="Target Printer:", font=("Segoe UI", 9, "bold"), bg="#f8fafc").pack(anchor="w")
        self.printer_combo = ttk.Combobox(c_frame, state="readonly", font=("Segoe UI", 9))
        self.printer_combo.pack(fill="x", pady=(0, 5))
        self.update_printer_dropdown([])

        tk.Label(c_frame, text="Select File (PDF, Image, Doc):", font=("Segoe UI", 9, "bold"), bg="#f8fafc").pack(anchor="w")
        file_box = tk.Frame(c_frame, bg="#f8fafc")
        file_box.pack(fill="x", pady=(0, 5))
        self.file_entry = tk.Entry(file_box, font=("Segoe UI", 9))
        self.file_entry.pack(side="left", fill="x", expand=True, padx=(0, 5))
        tk.Button(file_box, text="Browse...", command=self.browse_file, font=("Segoe UI", 8, "bold")).pack(side="right")

        # Page Selection Frame
        page_frame = tk.Frame(c_frame, bg="#e2e8f0", padx=8, pady=5)
        page_frame.pack(fill="x", pady=5)
        
        tk.Label(page_frame, text="Pages (e.g. 'All' or '1-3, 5'):", font=("Segoe UI", 8, "bold"), bg="#e2e8f0").pack(side="left")
        self.pages_entry = tk.Entry(page_frame, font=("Segoe UI", 9), width=12)
        self.pages_entry.insert(0, "All")
        self.pages_entry.pack(side="left", padx=8)

        self.native_dialog_var = tk.BooleanVar(value=False)
        tk.Checkbutton(page_frame, text="Use Host Native Print Dialog", variable=self.native_dialog_var, font=("Segoe UI", 8), bg="#e2e8f0").pack(side="right")

        # Print Preview Canvas Frame
        prev_frame = tk.LabelFrame(self.root, text=" Print Preview ", font=("Segoe UI", 9, "bold"), bg="#f8fafc", padx=5, pady=5)
        prev_frame.pack(fill="both", expand=True, padx=15, pady=5)

        self.preview_canvas = tk.Canvas(prev_frame, bg="#64748b", highlightthickness=0)
        self.preview_canvas.pack(fill="both", expand=True)

        tk.Button(self.root, text="🖨️ Send Print Job to Host (Ctrl+P)", command=self.send_print_job, font=("Segoe UI", 11, "bold"), bg="#166534", fg="white", relief="flat", pady=8).pack(fill="x", padx=15, pady=(5, 12))

        threading.Thread(target=self._auto_discover_host, daemon=True).start()

    def add_network_printer_dialog(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Add Network Printer")
        dialog.geometry("380x200")
        dialog.configure(bg="#f8fafc")
        dialog.transient(self.root)
        dialog.grab_set()

        tk.Label(dialog, text="➕ Add Shared Network Printer", font=("Segoe UI", 11, "bold"), bg="#f8fafc", fg="#0284c7").pack(pady=10)

        f1 = tk.Frame(dialog, bg="#f8fafc")
        f1.pack(fill="x", padx=20, pady=5)
        tk.Label(f1, text="Host IP Address:", font=("Segoe UI", 9, "bold"), bg="#f8fafc").pack(anchor="w")
        host_ip_ent = tk.Entry(f1, font=("Segoe UI", 9))
        host_ip_ent.insert(0, self.host_ip if self.host_ip else "")
        host_ip_ent.pack(fill="x")

        f2 = tk.Frame(dialog, bg="#f8fafc")
        f2.pack(fill="x", padx=20, pady=5)
        tk.Label(f2, text="Display Alias (Optional):", font=("Segoe UI", 9, "bold"), bg="#f8fafc").pack(anchor="w")
        alias_ent = tk.Entry(f2, font=("Segoe UI", 9))
        alias_ent.pack(fill="x")

        def save_and_connect():
            target_ip = host_ip_ent.get().strip()
            alias = alias_ent.get().strip()
            if not target_ip:
                messagebox.showerror("Error", "Please enter a valid Host IP address.", parent=dialog)
                return

            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(4.0)
                s.connect((target_ip, PORT))

                payload = json.dumps({"action": "get_printers"}).encode('utf-8')
                s.sendall(len(payload).to_bytes(4, byteorder='big') + payload)

                data = s.recv(4096)
                res = json.loads(data.decode('utf-8'))
                printers = res.get("printers", [])
                s.close()

                if printers:
                    key_name = alias if alias else f"Network Host ({target_ip})"
                    self.saved_printers[key_name] = {"ip": target_ip, "printers": printers}
                    save_printer_config(self.saved_printers)

                    self.host_ip = target_ip
                    if hasattr(self, 'ip_entry'):
                        self.ip_entry.delete(0, tk.END)
                        self.ip_entry.insert(0, target_ip)

                    self.update_printer_dropdown(printers)
                    self.status_lbl.config(text=f"Connected to {key_name}", fg="#166534")
                    messagebox.showinfo("Success", f"Connected to {len(printers)} printer(s) on Host {target_ip}!", parent=dialog)
                    dialog.destroy()
                else:
                    messagebox.showwarning("No Printers", "Connected to host, but no printers were found.", parent=dialog)
            except Exception as e:
                messagebox.showerror("Connection Error", f"Cannot connect to Host IP {target_ip}.\nError: {str(e)}", parent=dialog)

        tk.Button(dialog, text="Connect & Save Printer", command=save_and_connect, font=("Segoe UI", 10, "bold"), bg="#166534", fg="white", relief="flat", pady=6).pack(fill="x", padx=20, pady=10)

    def update_printer_dropdown(self, host_printers):
        combined_list = list(host_printers)
        for label, data in self.saved_printers.items():
            for p in data.get("printers", []):
                combo_item = f"{p} [{data['ip']}]"
                if combo_item not in combined_list:
                    combined_list.append(combo_item)

        if hasattr(self, 'printer_combo'):
            self.printer_combo['values'] = combined_list
            if combined_list:
                self.printer_combo.current(0)

    def browse_file(self):
        f = filedialog.askopenfilename(title="Select Document or Image", filetypes=[("Printable Files", "*.pdf;*.png;*.jpg;*.jpeg;*.txt;*.doc;*.docx")])
        if f:
            self.selected_file_path = f
            if hasattr(self, 'file_entry'):
                self.file_entry.delete(0, tk.END)
                self.file_entry.insert(0, f)
                self.generate_preview(f)

    def generate_preview(self, filepath):
        if not hasattr(self, 'preview_canvas'):
            return
        self.preview_canvas.delete("all")
        ext = os.path.splitext(filepath)[1].lower()

        try:
            img = None
            if ext in ['.png', '.jpg', '.jpeg']:
                img = Image.open(filepath)
            elif ext == '.pdf' and PYPDF_AVAILABLE:
                reader = pypdf.PdfReader(filepath)
                self.total_pages = len(reader.pages)
                self.preview_canvas.create_text(200, 100, text=f"PDF Loaded ({self.total_pages} Pages)\n\nPage Range: {self.pages_entry.get()}", fill="white", font=("Segoe UI", 12, "bold"))
                return

            if img:
                img.thumbnail((300, 250))
                self.preview_image_ref = ImageTk.PhotoImage(img)
                self.preview_canvas.create_image(150, 125, image=self.preview_image_ref)
            else:
                self.preview_canvas.create_text(200, 100, text=f"Document Selected:\n{os.path.basename(filepath)}", fill="white", font=("Segoe UI", 11))
        except Exception as e:
            self.preview_canvas.create_text(200, 100, text=f"Preview Unavailable\n({str(e)})", fill="#f87171", font=("Segoe UI", 9))

    def manual_connect(self):
        ip = self.ip_entry.get().strip()
        if ip:
            self.host_ip = ip
            self.status_lbl.config(text=f"Connecting to {ip}...", fg="#0284c7")
            self.fetch_host_printers()

    def _auto_discover_host(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(('', BROADCAST_PORT))
        sock.settimeout(3.0)
        while self.mode == "CLIENT" and not self.host_ip:
            try:
                data, addr = sock.recvfrom(1024)
                payload = json.loads(data.decode('utf-8'))
                if payload.get("app") == "BENOZIR_PRINT_SERVER":
                    self.host_ip = payload.get("server_ip")
                    self.ip_entry.delete(0, tk.END)
                    self.ip_entry.insert(0, self.host_ip)
                    self.fetch_host_printers()
            except Exception:
                pass

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

            self.update_printer_dropdown(printers)
            self.status_lbl.config(text=f"Connected to Host ({self.host_ip})", fg="#166534")
            s.close()
        except Exception:
            self.status_lbl.config(text="Connection Failed.", fg="#dc2626")

    def send_print_job(self):
        if not hasattr(self, 'file_entry'):
            messagebox.showwarning("Client Mode Required", "Please switch to Client Mode first.")
            return

        filepath = self.file_entry.get().strip()
        selected_printer_raw = self.printer_combo.get()

        if not filepath or not os.path.exists(filepath) or not selected_printer_raw:
            messagebox.showwarning("Incomplete Details", "Verify Printer and File path.")
            return

        printer_name = selected_printer_raw
        target_ip = self.host_ip

        if "[" in selected_printer_raw and "]" in selected_printer_raw:
            printer_name = selected_printer_raw.split(" [")[0]
            target_ip = selected_printer_raw.split("[")[1].replace("]", "")

        if not target_ip:
            messagebox.showerror("Host Missing", "No Host IP specified for this printer.")
            return

        temp_job_path = filepath
        temp_created = False
        ext = os.path.splitext(filepath)[1].lower()

        if ext == '.pdf' and PYPDF_AVAILABLE:
            page_range_str = self.pages_entry.get().strip()
            if page_range_str.lower() != "all":
                reader = pypdf.PdfReader(filepath)
                pages_to_keep = parse_page_range(page_range_str, len(reader.pages))
                if pages_to_keep:
                    temp_dir = os.environ.get("TEMP", os.path.expanduser("~"))
                    temp_job_path = os.path.join(temp_dir, f"sliced_{int(time.time())}.pdf")
                    if slice_pdf_file(filepath, temp_job_path, pages_to_keep):
                        temp_created = True

        try:
            file_size = os.path.getsize(temp_job_path)
            file_name = os.path.basename(filepath)

            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(15.0)
            s.connect((target_ip, PORT))

            header_dict = {
                "action": "print",
                "printer_name": printer_name,
                "file_name": file_name,
                "file_size": file_size,
                "use_native_dialog": self.native_dialog_var.get()
            }
            payload = json.dumps(header_dict).encode('utf-8')
            s.sendall(len(payload).to_bytes(4, byteorder='big') + payload)

            if s.recv(1024) == b"READY":
                with open(temp_job_path, "rb") as f:
                    while True:
                        chunk = f.read(8192)
                        if not chunk:
                            break
                        s.sendall(chunk)

                if s.recv(1024) == b"SUCCESS":
                    messagebox.showinfo("Success", f"Print job sent successfully to {printer_name}!")
                else:
                    messagebox.showerror("Failed", "Host printer failed to process document.")
            s.close()
        except Exception as e:
            messagebox.showerror("Error", f"Transmission Failure: {str(e)}")
        finally:
            if temp_created and os.path.exists(temp_job_path):
                os.remove(temp_job_path)

if __name__ == "__main__":
    root = tk.Tk()
    app = AppGUI(root)
    root.protocol("WM_DELETE_WINDOW", lambda: os._exit(0))
    root.mainloop()
