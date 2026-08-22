"""
====================================================================
 Universal Client-Server LAN & Wi-Fi Print Station (Win 10/11 Ready)
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

try:
    import win32print
    import win32api
    WIN32_AVAILABLE = True
except ImportError:
    WIN32_AVAILABLE = False

PORT = 9100
BROADCAST_PORT = 9101

# --- MULTI-INTERFACE & NETWORK UTILITIES ---
def get_all_local_ips():
    """Gets all IPv4 addresses across Ethernet and Wi-Fi adapters."""
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

def print_file_host_win10_11(printer_name, filepath):
    """Windows 10/11 Native Raw Spooler Submission."""
    if not WIN32_AVAILABLE:
        raise Exception("Windows Print Spooler API unavailable.")

    # Try native WinSpool Raw Direct Stream first (Fastest for Windows 10/11)
    try:
        hPrinter = win32print.OpenPrinter(printer_name)
        try:
            hJob = win32print.StartDocPrinter(hPrinter, 1, ("LAN_Print_Job", None, "RAW"))
            win32print.StartPagePrinter(hPrinter)
            with open(filepath, "rb") as f:
                win32print.WritePrinter(hPrinter, f.read())
            win32print.EndPagePrinter(hPrinter)
            win32print.EndDocPrinter(hPrinter)
            return
        finally:
            win32print.ClosePrinter(hPrinter)
    except Exception:
        pass

    # Fallback to ShellExecute verb method with Default Printer swap
    old_printer = win32print.GetDefaultPrinter()
    try:
        win32print.SetDefaultPrinter(printer_name)
        win32api.ShellExecute(0, "print", filepath, None, ".", 0)
    finally:
        win32print.SetDefaultPrinter(old_printer)

# --- HOST SERVER LOGIC ---
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
            local_ips = get_all_local_ips()
            for ip in local_ips:
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
        try:
            header_bytes = conn.recv(2048)
            if not header_bytes:
                return
            
            header = json.loads(header_bytes.decode('utf-8'))
            action = header.get("action")

            if action == "ping":
                conn.sendall(json.dumps({"status": "PONG", "app": "BENOZIR_PRINT_SERVER"}).encode('utf-8'))

            elif action == "get_printers":
                printers, default_p = get_installed_printers()
                response = json.dumps({"printers": printers, "default": default_p})
                conn.sendall(response.encode('utf-8'))

            elif action == "print":
                printer_name = header.get("printer_name")
                file_size = header.get("file_size")
                file_name = header.get("file_name")
                
                conn.sendall(b"READY")
                
                temp_path = os.path.join(os.path.expanduser("~"), f"temp_job_{file_name}")
                received = 0
                with open(temp_path, "wb") as f:
                    while received < file_size:
                        chunk = conn.recv(4096)
                        if not chunk:
                            break
                        f.write(chunk)
                        received += len(chunk)

                print_file_host_win10_11(printer_name, temp_path)
                conn.sendall(b"SUCCESS")
                self.status_callback(f"Printed '{file_name}' from {addr[0]} on '{printer_name}'")
        except Exception as e:
            self.status_callback(f"Error handling job from {addr[0]}: {str(e)}")
        finally:
            conn.close()

# --- GRAPHICAL INTERFACE ---
class AppGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Universal LAN & Wi-Fi Print Station (Windows 10/11) - BENOZIR 2026")
        self.root.geometry("580x560")
        self.root.configure(bg="#f8fafc")

        self.mode = None
        self.host_ip = None
        self.server_instance = None

        self.setup_welcome_screen()

    def setup_welcome_screen(self):
        for widget in self.root.winfo_children():
            widget.destroy()

        tk.Label(self.root, text="🖨️ LAN / Wi-Fi Print Station", font=("Segoe UI", 16, "bold"), bg="#f8fafc", fg="#0f172a").pack(pady=(25, 2))
        tk.Label(self.root, text="Compatible with Windows 10 & 11 | © 2026 BENOZIR", font=("Segoe UI", 9), bg="#f8fafc", fg="#64748b").pack(pady=(0, 20))

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
        
        ip_text = " | ".join(ip_addresses)
        tk.Label(ip_frame, text=f"Host Active IP(s):  {ip_text}", font=("Segoe UI", 10, "bold"), bg="#e2e8f0", fg="#0f172a").pack()

        p_frame = tk.LabelFrame(self.root, text=" Shared Printers Active ", font=("Segoe UI", 9, "bold"), bg="#f8fafc", padx=10, pady=10)
        p_frame.pack(fill="x", padx=20, pady=5)

        listbox = tk.Listbox(p_frame, height=3, font=("Segoe UI", 9))
        listbox.pack(fill="x")
        for p in printers:
            listbox.insert(tk.END, f"  • {p}")

        log_frame = tk.LabelFrame(self.root, text=" Server Print Log ", font=("Segoe UI", 9, "bold"), bg="#f8fafc", padx=10, pady=10)
        log_frame.pack(fill="both", expand=True, padx=20, pady=(0, 15))

        self.log_box = tk.Text(log_frame, font=("Consolas", 9), state="disabled", bg="#0f172a", fg="#38bdf8")
        self.log_box.pack(fill="both", expand=True)

        self.server_instance = PrintServer(self.log_message)
        self.server_instance.start()
        self.log_message("Host server running on Windows 10/11 Print Engine...")

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
        
        host_box = tk.Frame(self.root, bg="#f8fafc", padx=20)
        host_box.pack(fill="x", pady=5)
        
        tk.Label(host_box, text="Host IP Address:", font=("Segoe UI", 9, "bold"), bg="#f8fafc").pack(side="left")
        self.ip_entry = tk.Entry(host_box, font=("Segoe UI", 10), width=16)
        self.ip_entry.pack(side="left", padx=8)
        tk.Button(host_box, text="Connect", command=self.manual_connect, font=("Segoe UI", 9, "bold"), bg="#0284c7", fg="white", relief="flat").pack(side="left")
        tk.Button(host_box, text="Scan Network", command=self.scan_network_for_host, font=("Segoe UI", 9, "bold"), bg="#475569", fg="white", relief="flat").pack(side="left", padx=5)

        self.status_lbl = tk.Label(self.root, text="Searching LAN / Wi-Fi for Host...", font=("Segoe UI", 9, "italic"), bg="#f8fafc", fg="#d97706")
        self.status_lbl.pack(pady=4)

        c_frame = tk.Frame(self.root, bg="#f8fafc", padx=20, pady=5)
        c_frame.pack(fill="both", expand=True)

        tk.Label(c_frame, text="Select Target Printer:", font=("Segoe UI", 10, "bold"), bg="#f8fafc").pack(anchor="w", pady=(5, 2))
        self.printer_combo = ttk.Combobox(c_frame, state="readonly", font=("Segoe UI", 10))
        self.printer_combo.pack(fill="x", pady=(0, 10))

        tk.Label(c_frame, text="Select File to Print:", font=("Segoe UI", 10, "bold"), bg="#f8fafc").pack(anchor="w", pady=(5, 2))
        
        file_box = tk.Frame(c_frame, bg="#f8fafc")
        file_box.pack(fill="x", pady=(0, 15))
        
        self.file_entry = tk.Entry(file_box, font=("Segoe UI", 10))
        self.file_entry.pack(side="left", fill="x", expand=True, padx=(0, 5))
        tk.Button(file_box, text="Browse...", command=self.browse_file, font=("Segoe UI", 9, "bold")).pack(side="right")

        tk.Button(c_frame, text="🖨️ Send Print Job to Host", command=self.send_print_job, font=("Segoe UI", 12, "bold"), bg="#166534", fg="white", relief="flat", pady=10).pack(fill="x", pady=10)

        threading.Thread(target=self._auto_discover_host, daemon=True).start()

    def browse_file(self):
        f = filedialog.askopenfilename(title="Select File to Print")
        if f:
            self.file_entry.delete(0, tk.END)
            self.file_entry.insert(0, f)

    def manual_connect(self):
        ip = self.ip_entry.get().strip()
        if ip:
            self.host_ip = ip
            self.status_lbl.config(text=f"Connecting to {ip}...", fg="#0284c7")
            self.fetch_host_printers()

    def scan_network_for_host(self):
        self.status_lbl.config(text="Scanning subnet for Host IP...", fg="#0284c7")
        threading.Thread(target=self._subnet_sweep, daemon=True).start()

    def _subnet_sweep(self):
        local_ips = get_all_local_ips()
        if not local_ips:
            return
        
        base_ip = ".".join(local_ips[0].split(".")[:-1])
        found_ip = None

        def check_ip(ip_suffix):
            nonlocal found_ip
            if found_ip:
                return
            target_ip = f"{base_ip}.{ip_suffix}"
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(0.3)
                if s.connect_ex((target_ip, PORT)) == 0:
                    s.sendall(json.dumps({"action": "ping"}).encode('utf-8'))
                    res = s.recv(512)
                    if b"BENOZIR_PRINT_SERVER" in res:
                        found_ip = target_ip
                s.close()
            except Exception:
                pass

        threads = []
        for i in range(1, 255):
            t = threading.Thread(target=check_ip, args=(i,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        if found_ip:
            self.host_ip = found_ip
            self.ip_entry.delete(0, tk.END)
            self.ip_entry.insert(0, self.host_ip)
            self.fetch_host_printers()
        else:
            self.status_lbl.config(text="No Host found. Enter Host IP manually.", fg="#dc2626")

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
            s.settimeout(4.0)
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
            self.status_lbl.config(text=f"Connected to Host ({self.host_ip})", fg="#166534")
            s.close()
        except Exception as e:
            self.status_lbl.config(text="Connection Failed. Check IP/Firewall.", fg="#dc2626")
            messagebox.showerror("Connection Error", f"Cannot connect to Host PC ({self.host_ip}): {str(e)}")

    def send_print_job(self):
        filepath = self.file_entry.get().strip()
        printer_name = self.printer_combo.get()

        if not self.host_ip:
            messagebox.showwarning("Host Required", "Enter Host IP address and click Connect first.")
            return
        if not filepath or not os.path.exists(filepath):
            messagebox.showwarning("Invalid File", "Please select a valid file.")
            return
        if not printer_name:
            messagebox.showwarning("No Printer", "Please select a printer.")
            return

        try:
            file_size = os.path.getsize(filepath)
            file_name = os.path.basename(filepath)

            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(10.0)
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
                    messagebox.showinfo("Success", f"Print job sent successfully to Host!")
            s.close()
        except Exception as e:
            messagebox.showerror("Print Failed", f"Network error sending print job: {str(e)}")

if __name__ == "__main__":
    root = tk.Tk()
    app = AppGUI(root)
    root.protocol("WM_DELETE_WINDOW", lambda: os._exit(0))
    root.mainloop()
