import sys
import subprocess
import os
import time
import can
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, 
                             QPushButton, QComboBox, QLabel, QTableWidget, 
                             QTableWidgetItem, QHeaderView, QLineEdit, QMessageBox)
from PyQt6.QtCore import QTimer, QThread, pyqtSignal, Qt
from PyQt6.QtGui import QColor

class CanReaderThread(QThread):
    message_received = pyqtSignal(object)
    def __init__(self, interface='can0'):
        super().__init__()
        self.interface = interface
        self.running = False

    def run(self):
        self.running = True
        try:
            bus = can.interface.Bus(channel=self.interface, bustype='socketcan')
            while self.running:
                msg = bus.recv(timeout=0.1)
                if msg: self.message_received.emit(msg)
            bus.shutdown()
        except: self.running = False

class CanManagerV5(QWidget):
    def __init__(self):
        super().__init__()
        self.device = None
        self.is_active = False
        self.can_thread = None
        self.seen_ids = {} # Format: {id_int: [row_index, last_timestamp, last_data]}
        self.initUI()
        
        self.usb_timer = QTimer()
        self.usb_timer.timeout.connect(self.check_usb)
        self.usb_timer.start(1000)

    def initUI(self):
        self.setWindowTitle('CAN Master - TECNODJUM V5')
        self.setMinimumSize(850, 500)
        self.setStyleSheet("background-color: #2b2b2b; color: #ecf0f1;")
        layout = QVBoxLayout()

        # --- Barre de contrôle ---
        ctrl_layout = QHBoxLayout()
        self.status_label = QLabel('🔍 Scan USB...')
        ctrl_layout.addWidget(self.status_label)
        
        self.combo = QComboBox()
        self.combo.addItems(["500k (S6)", "250k (S5)", "100k (S3)", "125k (S4)", "1M (S8)"])
        ctrl_layout.addWidget(self.combo)
        
        self.btn_toggle = QPushButton('🚀 DEMARRER')
        self.btn_toggle.clicked.connect(self.toggle_can)
        self.btn_toggle.setStyleSheet("background-color: #27ae60; font-weight: bold; padding: 5px;")
        ctrl_layout.addWidget(self.btn_toggle)
        layout.addLayout(ctrl_layout)

        # --- Barre d'outils (Filtre & Injecteur) ---
        tools_layout = QHBoxLayout()
        self.filter_input = QLineEdit()
        self.filter_input.setPlaceholderText("Filtrer ID...")
        tools_layout.addWidget(QLabel("Filtre:"))
        tools_layout.addWidget(self.filter_input)
        
        self.send_input = QLineEdit()
        self.send_input.setPlaceholderText("ID#Data (ex: 7DF#0201050000000000)")
        tools_layout.addWidget(QLabel("Envoyer:"))
        tools_layout.addWidget(self.send_input)
        
        self.btn_send = QPushButton("OK")
        self.btn_send.clicked.connect(self.send_frame)
        tools_layout.addWidget(self.btn_send)
        layout.addLayout(tools_layout)

        # --- TABLEAU DYNAMIQUE (La "Tuerie") ---
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["ID (Hex)", "Données (Octets)", "Période (ms)", "Compteur"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setStyleSheet("QTableWidget { background-color: #1e1e1e; color: #00ff00; font-family: 'Monospace'; }")
        layout.addWidget(self.table)

        self.setLayout(layout)

    def check_usb(self):
        ports = [f"/dev/{p}" for p in os.listdir('/dev') if p.startswith('ttyUSB')]
        if ports:
            self.device = ports[0]
            self.status_label.setText(f"✅ USB: {self.device}")
        else:
            self.device = None
            self.status_label.setText("❌ USB non détecté")

    def toggle_can(self):
        if not self.is_active:
            self.start_can()
        else:
            self.stop_can()

    def start_can(self):
        if not self.device: return
        speed_code = self.combo.currentText().split('(')[1][:2].lower()
        try:
            subprocess.run(["sudo", "pkill", "slcand"])
            time.sleep(0.1)
            subprocess.run(["sudo", "slcand", "-o", "-c", "-f", f"-{speed_code}", "-S", "115200", self.device, "can0"])
            time.sleep(0.5)
            subprocess.run(["sudo", "ip", "link", "set", "can0", "up"])
            
            self.can_thread = CanReaderThread('can0')
            self.can_thread.message_received.connect(self.update_table)
            self.can_thread.start()
            
            self.is_active = True
            self.btn_toggle.setText("🛑 ARRÊTER")
            self.btn_toggle.setStyleSheet("background-color: #c0392b;")
        except Exception as e: QMessageBox.critical(self, "Erreur", str(e))

    def stop_can(self):
        if self.can_thread: self.can_thread.running = False
        subprocess.run(["sudo", "ip", "link", "set", "can0", "down"])
        self.is_active = False
        self.btn_toggle.setText("🚀 DEMARRER")
        self.btn_toggle.setStyleSheet("background-color: #27ae60;")
        self.table.setRowCount(0)
        self.seen_ids = {}

    def send_frame(self):
        if not self.is_active: return
        try:
            line = self.send_input.text()
            if "#" in line: subprocess.run(["sudo", "cansend", "can0", line])
        except: pass

    def update_table(self, msg):
        msg_id = msg.arbitration_id
        msg_id_hex = f"{msg_id:03X}"
        
        # Filtre
        f_text = self.filter_input.text().strip().upper()
        if f_text and f_text not in msg_id_hex: return

        data_hex = ' '.join([f"{b:02X}" for b in msg.data])
        now = time.time()

        if msg_id not in self.seen_ids:
            # Nouvel ID : Ajout d'une ligne
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(msg_id_hex))
            self.table.setItem(row, 1, QTableWidgetItem(data_hex))
            self.table.setItem(row, 2, QTableWidgetItem("0"))
            self.table.setItem(row, 3, QTableWidgetItem("1"))
            self.seen_ids[msg_id] = [row, now, data_hex, 1]
        else:
            # ID existant : Mise à jour
            row, last_time, last_data, count = self.seen_ids[msg_id]
            period = int((now - last_time) * 1000)
            new_count = count + 1
            
            # Mise à jour des cellules
            self.table.item(row, 2).setText(str(period))
            self.table.item(row, 3).setText(str(new_count))
            
            data_item = self.table.item(row, 1)
            data_item.setText(data_hex)
            
            # --- EFFET VISUEL (Highlight) ---
            if data_hex != last_data:
                data_item.setBackground(QColor(255, 0, 0, 150)) # Rouge transparent
                # On remet le fond normal après 150ms
                QTimer.singleShot(150, lambda i=data_item: i.setBackground(QColor(0,0,0,0)))
            
            # Sauvegarde du nouvel état
            self.seen_ids[msg_id] = [row, now, data_hex, new_count]

if __name__ == '__main__':
    app = QApplication(sys.argv)
    ex = CanManagerV5()
    ex.show()
    sys.exit(app.exec())