"""
====================================================================
 WiFi Print Server Application
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
    <title>WiFi Print Server - BENOZIR</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: system-ui, sans-serif; background: #eef2f5; color: #333; padding: 20px; display: flex; justify-content: center; align-items: center; min-height: 100vh; }
        .card { background: #fff; width: 100%; max-width: 480px; padding: 30px; border-radius: 16px; box-shadow: 0 10px 25px rgba(0,0,0,0.08); text-align: center; }
        .printer-badge { background: #eef6ff; color: #0066cc; border: 1px solid #cce5ff; padding: 8px 14px; border-radius: 20px; font-weight: 600; font-size: 13px; display: inline-block; margin-bottom: 20px; }
        .alert { padding: 12px; border-radius: 8px; margin-bottom: 20px; font-size: 14px; text-align: left; }
        .alert-success { background: #e6f4ea; color: #137333; }
        .alert-error { background: #fce8e6; color: #c5221f; }
        .file-drop { border: 2px dashed #0066cc; border-radius: 12px; padding: 24px 16px; background: #fafcff; cursor: pointer; margin-bottom: 20px; }
        button { background: #0066cc; color: white; border: none; padding: 14px; border-radius: 8px; width: 100%; font-size: 16px; font-weight: 600; cursor: pointer; }
        .qr-section { margin-top: 24px; padding-top: 20px; border-top: 1px solid #eee; display: flex; flex-direction: column; align-items: center; }
        .qr-section img { border-radius: 8px; border: 1px solid #ddd; padding: 4px; width: 130px; height: 130px; }
        .footer-copy { margin-top: 20px; font-size: 11px; color: #888; font-weight: 500; }
    </style>
</head>
<body>
    <div class="card">
        <h2 style="margin-bottom:8px;">🖨️ WiFi Print Server</h2>
        <div class="printer-badge">Printer: {{ printer }}</div>

        {% with messages = get_flashed_messages(with_categories=true) %}
          {% if messages %}
            {% for category, message in messages %}
              <div class="alert alert-{{ category }}">{{ message }}</div>
            {% endfor %}
          {% endif %}
        {% endwith %}

        <form method="post" enctype="multipart/form-data">
            <div class="file-drop" onclick="document.getElementById('file-input').click()">
                <div style="color:#0066cc; font-weight:bold;">📄 Tap or Click to Select File</div>
                <div id="fname" style="font-size:12px; color:#666; margin-top:6px;">Supports Images, PDFs & Docs</div>
            </div>
            <input type="file" id="file-input" name="file" style="display:none;" onchange="document.getElementById('fname').innerText=this.files[0].name" required>
            <button type="submit">Print Document Now</button>
        </form>

        <div class="qr-section">
            <img src="/qr.png" alt="QR">
            <div style="font-size:12px; color:#888; margin-top:6px;">Scan to connect instantly from phone</div>
        </div>

        <div class="footer-copy">
            © 2026 BENOZIR. All Rights Reserved.
        </div>
    </div>
</body>
</html>
"""

def get_default_printer():
    if WIN32_AVAILABLE:
        try:
            return win32print.GetDefaultPrinter()
        except Exception:
            pass
    return "Default Windows Printer"

def print_file(filepath):
    if WIN32_AVAILABLE:
        win32api.ShellExecute(0, "print", filepath, None, ".", 0)

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
    default_printer = get_default_printer()
    if request.method == "POST":
        file = request.files.get("file")
        if file and file.filename != "":
            save_path = os.path.join(UPLOAD_FOLDER, file.filename)
            file.save(save_path)
            try:
                print_file(save_path)
                flash(f"Sent '{file.filename}' to printer!", "success")
            except Exception as e:
                flash(f"Error printing: {str(e)}", "error")
            return redirect("/")
    return render_template_string(HTML_TEMPLATE, printer=default_printer)

@app.route("/qr.png")
def qr_code():
    import qrcode
    ip = get_local_ip()
    qr = qrcode.QRCode(box_size=4, border=2)
    qr.add_data(f"http://{ip}:5000")
    qr.make(fit=True)
    img = qr.make_image(fill_color="#0066cc", back_color="white")
    img_io = io.BytesIO()
    img.save(img_io, 'PNG')
    img_io.seek(0)
    return send_file(img_io, mimetype='image/png')

def create_tray_icon():
    image = Image.new('RGB', (64, 64), color=(0, 102, 204))
    draw = ImageDraw.Draw(image)
    draw.rectangle([14, 16, 50, 42], fill='white')
    draw.rectangle([18, 42, 46, 52], fill='#dddddd')
    return image

def setup_tray():
    local_ip = get_local_ip()
    url_str = f"http://{local_ip}:5000"
    menu = pystray.Menu(
        pystray.MenuItem("WiFi Print Server", lambda: None, enabled=False),
        pystray.MenuItem("© 2026 BENOZIR", lambda: None, enabled=False),
        pystray.MenuItem(f"URL: {url_str}", lambda: None, enabled=False),
        pystray.MenuItem("Exit Print Server", lambda icon, item: (icon.stop(), os._exit(0)))
    )
    icon = pystray.Icon("LocalPrintServer", create_tray_icon(), f"WiFi Printer - © 2026 BENOZIR", menu)
    icon.run()

if __name__ == "__main__":
    threading.Thread(target=lambda: app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False), daemon=True).start()
    setup_tray()
