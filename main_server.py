"""
====================================================================
 Offline Desktop & Network Print Server Suite
 Copyright (c) 2026 BENOZIR. All Rights Reserved.
====================================================================
"""

import os
import sys
import threading
import socket
import io
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageDraw, ImageTk
import pystray
from flask import Flask, render_template_string, request, flash, redirect, send_file

app = Flask(__name__)
app.secret_key = "local_print_secret_key_benozir_2026"
UPLOAD_FOLDER = os.path.join(os.path.expanduser("~"), "LocalPrintServer_Temp")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

try:
    import win32api
    import win32print
    WIN32_AVAILABLE = True
except ImportError:
    WIN32_AVAILABLE = False

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>LAN Print Server - BENOZIR</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: system-ui, -apple-system, sans-serif; background: #e2e8f0; color: #1e293b; padding: 20px; display: flex; justify-content: center; align-items: center; min-height: 100vh; }
        .card { background: #fff; width: 100%; max-width: 520px; padding: 28px; border-radius: 16px; box-shadow: 0 10px 25px rgba(0,0,0,0.1); }
        h2 { font-size: 22px; text-align: center; color: #0f172a; margin-bottom: 4px; }
        p.subtitle { font-size: 13px; color: #64748b; text-align: center; margin-bottom: 20px; }
        .form-group { margin-bottom: 16px; text-align: left; }
        label { font-size: 13px; font-weight: 600; color: #334155; display: block; margin-bottom: 6px; }
        select, input[type="text"], input[type="number"] { width: 100%; padding: 10px 12px; border: 1px solid #cbd5e1; border-radius: 8px; font-size: 14px; background: #f8fafc; }
        .row { display: flex; gap: 12px; }
        .col { flex: 1; }
        .alert { padding: 12px; border-radius: 8px; margin-bottom: 16px; font-size: 14px; }
        .alert-success { background: #dcfce7; color: #166534; }
        .alert-error { background: #fee2e2; color: #991b1b; }
        .file-drop { border: 2px dashed #0284c7; border-radius: 12px; padding: 20px; background: #f0f9ff; cursor: pointer; text-align: center; margin-bottom: 16px; }
        button { background: #0284c7; color: white; border: none; padding: 12px; border-radius: 8px; width: 100%; font-size: 15px; font-weight: 600; cursor: pointer; }
        button:hover { background: #0369a1; }
        .qr-section { margin-top: 20px; padding-top: 16px; border-top: 1px solid #e2e8f0; text-align: center; }
        .qr-section img { border-radius: 8px; border: 1px solid #cbd5e1; padding: 4px; width: 100px; height: 100px; }
        .footer-copy { margin-top: 16px; font-size: 11px; color: #94a3b8; text-align: center; font-weight: 500; }
    </style>
</head>
<body>
    <div class="card">
        <h2>🖨️ LAN / WiFi Print Server</h2>
        <p class="subtitle">Shared Printer Network Access</p>

        {% with messages = get_flashed_messages(with_categories=true) %}
          {% if messages %}
            {% for category, message in messages %}
              <div class="alert alert-{{ category }}">{{ message }}</div>
            {% endfor %}
          {% endif %}
        {% endwith %}

        <form method="post" enctype="multipart/form-data">
            <div class="form-group">
                <label for="printer_name">Target Printer</label>
                <select name="printer_name" id="printer_name">
                    {% for p in printers %}
                        <option value="{{ p }}" {% if p == default_printer %}selected{% endif %}>{{ p }}</option>
                    {% endfor %}
                </select>
            </div>

            <div class="file-drop" onclick="document.getElementById('file-input').click()">
                <div style="color:#0284c7; font-weight:bold;">📄 Select File to Print</div>
                <div id="fname" style="font-size:12px; color:#64748b; margin-top:4px;">Supports Images, PDFs & Text</div>
            </div>
            <input type="file" id="file-input" name="file" style="display:none;" onchange="document.getElementById('fname').innerText = 'Selected: ' + this.files[0].name" required>

            <div class="row">
                <div class="col form-group">
                    <label>Copies</label>
                    <input type="number" name="copies" value="1" min="1" max="99">
                </div>
            </div>

            <button type="submit">Print File Now</button>
        </form>

        <div class="qr-section">
            <img src="/qr.png" alt="QR">
            <div style="font-size:11px; color:#64748b; margin-top:4px;">Scan to connect from Mobile or PC</div>
        </div>

        <div class="footer-copy">
            © 2026 BENOZIR. All Rights Reserved.
        </div>
    </div>
</body>
</html>
"""

def get_installed_printers():
    printers = []
    default_printer = "Default Windows Printer"
    if WIN32_AVAILABLE:
        try:
            default_printer = win32print.GetDefaultPrinter()
            flags = win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
            printer_objs = win32print.EnumPrinters(flags)
            for p in printer_objs:
                printers.append(p[2])
        except Exception:
            pass
    if not printers:
        printers = [default_printer]
    return printers, default_printer

def print_file_advanced(filepath, printer_name, copies=1):
    if WIN32_AVAILABLE:
        old_printer = win32print.GetDefaultPrinter()
        win32print.SetDefaultPrinter(printer_name)
        try:
            for _ in range(int(copies)):
                win32api.ShellExecute(0, "print", filepath, None, ".", 0)
        finally:
            win32print.SetDefaultPrinter(old_printer)

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

@app.route("/", methods=["GET", "POST"])
def index():
    printers, default_printer = get_installed_printers()
    if request.method == "POST":
        file = request.files.get("file")
        selected_printer = request.form.get("printer_name", default_printer)
        copies = request.form.get("copies", 1)
        
        if file and file.filename != "":
            save_path = os.path.join(UPLOAD_FOLDER, file.filename)
            file.save(save_path)
            try:
                print_file_advanced(save_path, selected_printer, copies)
                flash(f"Sent '{file.filename}' ({copies} copies) to {selected_printer}!", "success")
            except Exception as e:
                flash(f"Error printing: {str(e)}", "error")
            return redirect("/")
            
    return render_template_string(HTML_TEMPLATE, printers=printers, default_printer=default_printer)

@app.route("/qr.png")
def qr_code():
    import qrcode
    ip = get_local_ip()
    qr = qrcode.QRCode(box_size=4, border=2)
    qr.add_data(f"http://{ip}:5000")
    qr.make(fit=True)
    img = qr.make_image(fill_color="#0284c7", back_color="white")
    img_io = io.BytesIO()
    img.save(img_io, 'PNG')
    img_io.seek(0)
    return send_file(img_io, mimetype='image/png')

def start_desktop_gui():
    root = tk.Tk()
    root.title("Print Server Control Panel - BENOZIR 2026")
    root.geometry("520x460")
    root.configure(bg="#f8fafc")

    ip = get_local_ip()
    printers, default_p = get_installed_printers()

    tk.Label(root, text="🖨️ Offline & LAN Print Server", font=("Segoe UI", 16, "bold"), bg="#f8fafc", fg="#0f172a").pack(pady=(15, 2))
    tk.Label(root, text="© 2026 BENOZIR. All Rights Reserved.", font=("Segoe UI", 9), bg="#f8fafc", fg="#64748b").pack(pady=(0, 15))

    status_frame = tk.LabelFrame(root, text=" Server Network Status ", font=("Segoe UI", 10, "bold"), bg="#f8fafc", fg="#0284c7", padx=15, pady=10)
    status_frame.pack(fill="x", px=20, py=5)

    tk.Label(status_frame, text=f"Network IP URL: http://{ip}:5000", font=("Segoe UI", 11, "bold"), bg="#f8fafc", fg="#166534").pack(anchor="w")
    tk.Label(status_frame, text="Status: Active & Broadcasting to LAN/WiFi Clients", font=("Segoe UI", 9), bg="#f8fafc", fg="#475569").pack(anchor="w", pady=(2, 0))

    printer_frame = tk.LabelFrame(root, text=" Hosted Shared Printers ", font=("Segoe UI", 10, "bold"), bg="#f8fafc", fg="#0284c7", padx=15, pady=10)
    printer_frame.pack(fill="both", expand=True, px=20, py=10)

    listbox = tk.Listbox(printer_frame, font=("Segoe UI", 9), selectmode=tk.SINGLE)
    listbox.pack(fill="both", expand=True)
    for p in printers:
        listbox.insert(tk.END, f"  •  {p}")

    def quick_print():
        file_path = filedialog.askopenfilename(title="Select File to Print")
        if file_path:
            try:
                print_file_advanced(file_path, default_p, 1)
                messagebox.showinfo("Success", f"Sent '{os.path.basename(file_path)}' to default printer!")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to print: {str(e)}")

    btn_frame = tk.Frame(root, bg="#f8fafc")
    btn_frame.pack(fill="x", px=20, py=(0, 15))
    
    tk.Button(btn_frame, text="📄 Quick Local Print", command=quick_print, font=("Segoe UI", 10, "bold"), bg="#0284c7", fg="white", relief="flat", padding=8).pack(fill="x")

    root.protocol("WM_DELETE_WINDOW", lambda: os._exit(0))
    root.mainloop()

if __name__ == "__main__":
    threading.Thread(target=lambda: app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False), daemon=True).start()
    start_desktop_gui()
