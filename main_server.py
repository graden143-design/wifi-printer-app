"""
====================================================================
 WiFi & LAN Print Server Application Pro
 Copyright (c) 2026 BENOZIR. All Rights Reserved.
====================================================================
"""

import os
import sys
import threading
import socket
import io
from PIL import Image, ImageDraw
import pystray
from flask import Flask, render_template_string, request, flash, redirect, send_file, jsonify

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
    <title>Network Print Server - BENOZIR</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: system-ui, -apple-system, sans-serif; background: #f0f4f8; color: #333; padding: 20px; display: flex; justify-content: center; align-items: center; min-height: 100vh; }
        .card { background: #fff; width: 100%; max-width: 520px; padding: 28px; border-radius: 16px; box-shadow: 0 10px 30px rgba(0,0,0,0.08); }
        h2 { font-size: 22px; margin-bottom: 4px; text-align: center; color: #1e293b; }
        p.subtitle { font-size: 13px; color: #64748b; text-align: center; margin-bottom: 20px; }
        .form-group { margin-bottom: 16px; text-align: left; }
        label { font-size: 13px; font-weight: 600; color: #475569; display: block; margin-bottom: 6px; }
        select, input[type="text"], input[type="number"] { width: 100%; padding: 10px 12px; border: 1px solid #cbd5e1; border-radius: 8px; font-size: 14px; outline: none; background: #f8fafc; }
        select:focus, input:focus { border-color: #0284c7; background: #fff; }
        .row { display: flex; gap: 12px; }
        .col { flex: 1; }
        .alert { padding: 12px; border-radius: 8px; margin-bottom: 16px; font-size: 14px; }
        .alert-success { background: #dcfce7; color: #166534; border: 1px solid #bbf7d0; }
        .alert-error { background: #fee2e2; color: #991b1b; border: 1px solid #fecaca; }
        .file-drop { border: 2px dashed #0284c7; border-radius: 12px; padding: 20px; background: #f0f9ff; cursor: pointer; text-align: center; margin-bottom: 16px; }
        button { background: #0284c7; color: white; border: none; padding: 14px; border-radius: 8px; width: 100%; font-size: 16px; font-weight: 600; cursor: pointer; transition: background 0.2s; }
        button:hover { background: #0369a1; }
        #preview-container { display: none; margin-bottom: 16px; text-align: center; background: #f1f5f9; padding: 10px; border-radius: 8px; border: 1px solid #e2e8f0; }
        #preview-img { max-width: 100%; max-height: 220px; border-radius: 4px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }
        .qr-section { margin-top: 20px; padding-top: 16px; border-top: 1px solid #e2e8f0; text-align: center; }
        .qr-section img { border-radius: 8px; border: 1px solid #cbd5e1; padding: 4px; width: 110px; height: 110px; }
        .footer-copy { margin-top: 16px; font-size: 11px; color: #94a3b8; text-align: center; font-weight: 500; }
    </style>
</head>
<body>
    <div class="card">
        <h2>🖨️ Universal Print Server</h2>
        <p class="subtitle">LAN & WiFi Printer Sharing Suite</p>

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
                <div style="color:#0284c7; font-weight:bold;">📄 Choose File to Print</div>
                <div id="fname" style="font-size:12px; color:#64748b; margin-top:4px;">Supports Images, PDFs & Text</div>
            </div>
            <input type="file" id="file-input" name="file" style="display:none;" onchange="handleFileSelect(this)" required>

            <div id="preview-container">
                <label>Document Preview</label>
                <img id="preview-img" src="" alt="Preview">
            </div>

            <div class="row">
                <div class="col form-group">
                    <label>Copies</label>
                    <input type="number" name="copies" value="1" min="1" max="99">
                </div>
                <div class="col form-group">
                    <label>Pages (e.g. 1-3, 5)</label>
                    <input type="text" name="pages" placeholder="All">
                </div>
            </div>

            <button type="submit">Print Document</button>
        </form>

        <div class="qr-section">
            <img src="/qr.png" alt="QR">
            <div style="font-size:11px; color:#64748b; margin-top:4px;">Scan to connect on Network</div>
        </div>

        <div class="footer-copy">
            © 2026 BENOZIR. All Rights Reserved.
        </div>
    </div>

    <script>
        function handleFileSelect(input) {
            if (input.files && input.files[0]) {
                const file = input.files[0];
                document.getElementById('fname').innerText = "Selected: " + file.name;
                
                if (file.type.startsWith('image/')) {
                    const reader = new FileReader();
                    reader.onload = function(e) {
                        document.getElementById('preview-img').src = e.target.result;
                        document.getElementById('preview-container').style.display = 'block';
                    }
                    reader.readAsDataURL(file);
                } else {
                    document.getElementById('preview-container').style.display = 'none';
                }
            }
        }
    </script>
</body>
</html>
"""

def get_installed_printers():
    printers = []
    default_printer = "Default Windows Printer"
    if WIN32_AVAILABLE:
        try:
            default_printer = win32print.GetDefaultPrinter()
            printer_objs = win32print.EnumPrinters(win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS)
            for p in printer_objs:
                printers.append(p[2])
        except Exception:
            pass
    if not printers:
        printers = [default_printer]
    return printers, default_printer

def print_file_advanced(filepath, printer_name, copies=1):
    if WIN32_AVAILABLE:
        # Set target printer temporarily for process execution
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

def create_tray_icon():
    image = Image.new('RGB', (64, 64), color=(2, 132, 199))
    draw = ImageDraw.Draw(image)
    draw.rectangle([14, 16, 50, 42], fill='white')
    draw.rectangle([18, 42, 46, 52], fill='#cbd5e1')
    return image

def setup_tray():
    local_ip = get_local_ip()
    url_str = f"http://{local_ip}:5000"
    menu = pystray.Menu(
        pystray.MenuItem("LAN & WiFi Print Server Pro", lambda: None, enabled=False),
        pystray.MenuItem("© 2026 BENOZIR", lambda: None, enabled=False),
        pystray.MenuItem(f"URL: {url_str}", lambda: None, enabled=False),
        pystray.MenuItem("Exit Print Server", lambda icon, item: (icon.stop(), os._exit(0)))
    )
    icon = pystray.Icon("LocalPrintServer", create_tray_icon(), f"Network Printer - © 2026 BENOZIR", menu)
    icon.run()

if __name__ == "__main__":
    threading.Thread(target=lambda: app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False), daemon=True).start()
    setup_tray()
