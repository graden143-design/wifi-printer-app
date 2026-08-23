# wifi-printer-app
"""
====================================================================
 Universal Client-Server LAN Print Station (Enterprise Edition)
 Features: Print Preview, Page Ranges, Native Dialogs, Signed Pipeline
 Copyright (c) 2026 BENOZIR. All Rights Reserved.
 Email: bhbony@gmail.com
====================================================================
"""
Network Wifi Printer 
Open the Start Menu on the Host PC.
Step 1:
Search for Command Prompt, right-click it, and select Run as administrator.

Copy and paste the following command, then press Enter:

DOS
netsh advfirewall firewall add rule name="LAN Printer Server (Port 9100)" dir=in action=allow protocol=TCP localport=9100

netsh advfirewall firewall add rule name="LAN Printer Server UDP (Port 9101)" dir=in action=allow protocol=UDP localport=9101

Step 2: Change Network Type from "Public" to "Private"If your Wi-Fi or Ethernet connection is set to Public Network, Windows 10/11 blocks all local communication between PCs on the same router.On both Host and Client PCs:Open Windows Settings (Win + I).Go to Network & Internet $\rightarrow$ Wi-Fi (or Ethernet).Click on your active network name.Change the Network profile type from Public to Private.
