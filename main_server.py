"""
====================================================================
 Universal Client-Server LAN Print Station
 Copyright (c) 2026 BENOZIR. All Rights Reserved.
====================================================================
"""

import os
import sys
import socket
import threading
import json
import time
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

try:
    import win32print
    import win32api
    WIN32_AVAILABLE = True
except ImportError:
    WIN32_AVAILABLE = False

PORT = 9100
BROADCAST_PORT = 9101

# --- NETWORK UTILITIES ---
def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('10.255.255.255', 1))
        ip = s.getsockname()[0]
    except Exception:
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip

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

def raw_print_file(printer_name, filepath):
    """Sends raw file data directly to the Windows Print Spooler queue."""
    if not WIN32_AVAILABLE:
        raise Exception("Windows Print API not available on this system.")
    
    hPrinter = win32print.OpenPrinter(printer_name)
    try:
        hJob = win32print.StartDocPrinter(hPrinter, 1, ("LAN Print Job", None, "RAW"))
        win32print.StartPagePrinter(hPrinter)
        
        with open(filepath, "rb") as f:
            win32print.WritePrinter(hPrinter, f.read())
            
        win32print.EndPagePrinter(hPrinter)
        win32print.EndDocPrinter(hPrinter)
    finally:
        win32print.ClosePrinter(hPrinter)

# --- HOST SERVER LOGIC ---
class PrintServer:
    def __init__(self, status_callback):
        self.status_callback = status_callback
        self.running = False

    def start(self):
        self.running = True
        threading.Thread(target=self._udp_broadcaster, daemon=True).start()
        threading.Thread(target=self._tcp_listener, daemon=True).start()

    def _udp_broadcaster(self):
        """Broadcaster so clients can auto-detect the Host IP on LAN."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        while self.running:
            try:
                msg = json.dumps({"server_ip": get_local_ip(), "app": "BENOZIR_PRINT_SERVER"})
                sock.sendto(msg.encode(), ('<broadcast>', BROADCAST_PORT))
            except Exception:
                pass
            time.sleep(3)

    def _tcp_listener(self):
        """TCP Listener to process print commands & file streams from Client PCs."""
        server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_sock.bind(('0.0.0.0', PORT))
        server_sock.listen(5)
        
        while self.running:
            conn, addr = server_sock.accept()
            threading.Thread(target=self._handle_client, args=(conn, addr), daemon=True).start()

    def _handle_client(self, conn, addr):
        try:
            header_bytes = conn.recv(1024)
            if not header_bytes:
                return
            
            header = json.loads(header_bytes.decode('utf-8'))
            action = header.get("action")

            if action == "get_printers":
                printers, default_p = get_installed_printers()
                response = json.dumps({"printers": printers, "default": default_p})
                conn.sendall(response.encode('utf-8'))

            elif action == "print":
                printer_name = header.get("printer_name")
                file_size = header.get("file_size")
                file_name = header.get("file_name")
                
                conn.sendall(b"READY")
                
                # Receive full binary file payload
                temp_path = os.path.join(os.path.expanduser("~"), f"temp_recv_{file_name}")
                received = 0
                with open(temp_path, "wb") as f:
                    while received < file_size:
                        chunk = conn.recv(4096)
                        if not chunk:
                            break
                        f.write(chunk)
                        received += len(chunk)

                raw_print_file(printer_name, temp_path)
                conn.sendall(b"SUCCESS")
                self.status_callback(f"Printed '{file_name}' from {addr[0]} on '{printer_name}'")
                
                if os.path.exists(temp_path):
                    os.remove(temp_path)
        except Exception as e:
            self.status_callback(f"Error handling job from {addr[0]}: {str(e)}")
        finally:
            conn.close()

# --- GRAPHICAL INTERFACE ---
class AppGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Universal LAN Print Station - BENOZIR 2026")
        self.root.geometry("540x520")
        self.root.configure(bg="#f8fafc")

        self.mode = None
        self.host_ip = None
        self.server_instance = None

        self.setup_welcome_screen()

    def setup_welcome_screen(self):
        for widget in self.root.winfo_children():
            widget.destroy()

        tk.Label(self.root, text="🖨️ Universal LAN Print Station", font=("Segoe UI", 16, "bold"), bg="#f8fafc", fg="#0f172a").pack(pady=(25, 2))
        tk.Label(self.root, text="© 2026 BENOZIR. All Rights Reserved.", font=("Segoe UI", 9), bg="#f8fafc", fg="#64748b").pack(pady=(0, 20))

        frame = tk.LabelFrame(self.root, text=" Choose PC Operating Mode ", font=("Segoe UI", 10, "bold"), bg="#f8fafc", fg="#0284c7", padx=20, pady=20)
        frame.pack(fill="both", expand=True, padx=30, pady=10)

        tk.Button(frame, text="🖥️ Host Mode\n(Run on PC connected to physical printers)", command=self.start_host_mode, font=("Segoe UI", 11, "bold"), bg="#0284c7", fg="white", relief="flat", pady=12).pack(fill="x", pady=10)
        tk.Button(frame, text="💻 Client Mode\n(Run on network PCs to send print jobs)", command=self.start_client_mode, font=("Segoe UI", 11, "bold"), bg="#475569", fg="white", relief="flat", pady=12).pack(fill="x", pady=10)

    # --- HOST GUI ---
    def start_host_mode(self):
        self.mode = "HOST"
        for widget in self.root.winfo_children():
            widget.destroy()

        ip = get_local_ip()
        printers, default_p = get_installed_printers()

        tk.Label(self.root, text="🖥️ HOST PRINT SERVER", font=("Segoe UI", 15, "bold"), bg="#f8fafc", fg="#166534").pack(pady=(15, 2))
        tk.Label(self.root, text=f"Broadcasting Printers on LAN IP: {ip}", font=("Segoe UI", 10, "bold"), bg="#f8fafc", fg="#0284c7").pack()

        p_frame = tk.LabelFrame(self.root, text=" Shared Printers Active ", font=("Segoe UI", 9, "bold"), bg="#f8fafc", padx=10, pady=10)
        p_frame.pack(fill="x", padx=20, pady=10)

        listbox = tk.Listbox(p_frame, height=4, font=("Segoe UI", 9))
        listbox.pack(fill="x")
        for p in printers:
            listbox.insert(tk.END, f"  • {p}")

        log_frame = tk.LabelFrame(self.root, text=" Server Print Activity Log ", font=("Segoe UI", 9, "bold"), bg="#f8fafc", padx=10, pady=10)
        log_frame.pack(fill="both", expand=True, padx=20, pady=(0, 15))

        self.log_box = tk.Text(log_frame, font=("Consolas", 9), state="disabled", bg="#0f172a", fg="#38bdf8")
        self.log_box.pack(fill="both", expand=True)

        self.server_instance = PrintServer(self.log_message)
        self.server_instance.start()
        self.log_message("Server started successfully. Listening for LAN jobs...")

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

        tk.Label(self.root, text="💻 CLIENT PRINT STATION", font=("Segoe UI", 15, "bold"), bg="#f8fafc", fg="#0284c7").pack(pady=(15, 2))
        self.status_lbl = tk.Label(self.root, text="Searching for Host Printer Server on LAN...", font=("Segoe UI", 9, "italic"), bg="#f8fafc", fg="#d97706")
        self.status_lbl.pack()

        c_frame = tk.Frame(self.root, bg="#f8fafc", padx=20, pady=10)
        c_frame.pack(fill="both", expand=True)

        tk.Label(c_frame, text="Select Target Host Printer:", font=("Segoe UI", 10, "bold"), bg="#f8fafc").pack(anchor="w", pady=(10, 2))
        self.printer_combo = ttk.Combobox(c_frame, state="readonly", font=("Segoe UI", 10))
        self.printer_combo.pack(fill="x", pady=(0, 15))

        tk.Label(c_frame, text="Select Document / Image to Print:", font=("Segoe UI", 10, "bold"), bg="#f8fafc").pack(anchor="w", pady=(5, 2))
        
        file_box = tk.Frame(c_frame, bg="#f8fafc")
        file_box.pack(fill="x", pady=(0, 15))
        
        self.file_entry = tk.Entry(file_box, font=("Segoe UI", 10))
        self.file_entry.pack(side="left", fill="x", expand=True, padx=(0, 5))
        tk.Button(file_box, text="Browse...", command=self.browse_file, font=("Segoe UI", 9, "bold")).pack(side="right")

        tk.Button(c_frame, text="🖨️ Send Print Job to Host", command=self.send_print_job, font=("Segoe UI", 12, "bold"), bg="#166534", fg="white", relief="flat", pady=10).pack(fill="x", pady=15)

        threading.Thread(target=self._auto_discover_host, daemon=True).start()

    def browse_file(self):
        f = filedialog.askopenfilename(title="Select File to Print")
        if f:
            self.file_entry.delete(0, tk.END)
            self.file_entry.insert(0, f)

    def _auto_discover_host(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(('', BROADCAST_PORT))
        sock.settimeout(4.0)
        
        while self.mode == "CLIENT" and not self.host_ip:
            try:
                data, addr = sock.recvfrom(1024)
                payload = json.loads(data.decode('utf-8'))
                if payload.get("app") == "BENOZIR_PRINT_SERVER":
                    self.host_ip = payload.get("server_ip")
                    self.status_lbl.config(text=f"Connected to Host Server at {self.host_ip}", fg="#166534")
                    self.fetch_host_printers()
            except socket.timeout:
                pass
            except Exception:
                pass

    def fetch_host_printers(self):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.connect((self.host_ip, PORT))
            s.sendall(json.dumps({"action": "get_printers"}).encode('utf-8'))
            data = s.recv(4096)
            res = json.loads(data.decode('utf-8'))
            printers = res.get("printers", [])
            default_p = res.get("default", "")
            
            self.printer_combo['values'] = printers
            if default_p in printers:
                self.printer_combo.set(default_p)
            elif printers:
                self.printer_combo.current(0)
            s.close()
        except Exception as e:
            messagebox.showerror("Network Error", f"Failed to fetch printers from host: {str(e)}")

    def send_print_job(self):
        filepath = self.file_entry.get().strip()
        printer_name = self.printer_combo.get()

        if not self.host_ip:
            messagebox.showwarning("Host Missing", "Searching for host server on LAN. Please wait...")
            return
        if not filepath or not os.path.exists(filepath):
            messagebox.showwarning("Invalid File", "Please select a valid file to print.")
            return
        if not printer_name:
            messagebox.showwarning("No Printer", "Please select a target printer.")
            return

        try:
            file_size = os.path.getsize(filepath)
            file_name = os.path.basename(filepath)

            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.connect((self.host_ip, PORT))

            header = {
                "action": "print",
                "printer_name": printer_name,
                "file_name": file_name,
                "file_size": file_size
            }
            s.sendall(json.dumps(header).encode('utf-8'))

            ack = s.recv(1024)
            if ack == b"READY":
                with open(filepath, "rb") as f:
                    s.sendall(f.read())

                res = s.recv(1024)
                if res == b"SUCCESS":
                    messagebox.showinfo("Success", f"Print job '{file_name}' successfully sent to {printer_name}!")
            s.close()
        except Exception as e:
            messagebox.showerror("Print Failed", f"Could not complete print job: {str(e)}")

if __name__ == "__main__":
    root = tk.Tk()
    app = AppGUI(root)
    root.protocol("WM_DELETE_WINDOW", lambda: os._exit(0))
    root.mainloop()
