import sys
import subprocess
import os
import time
import can
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, 
                             QPushButton, QComboBox, QLabel, QTextEdit, 
                             QMessageBox, QLineEdit, QTableWidget, QTableWidgetItem, QHeaderView)
from PyQt6.QtCore import QTimer, QThread, pyqtSignal, Qt

class CanReaderThread(QThread):
    message_received = pyqtSignal(object)
    def __init__(self, interface='can0'):
        super().__init__()
        self.interface = interface
        self.running = False

    def run(self):
        self.running = True
        bus = None
        while self.running:
            try:
                if bus is None:
                    bus = can.interface.Bus(channel=self.interface, bustype='socketcan')
                msg = bus.recv(timeout=0.5)
                if msg: self.message_received.emit(msg)
            except: self.running = False
        if bus: bus.shutdown()

class CanManagerV4(QWidget):
    def __init__(self):
        super().__init__()
        self.device = None
        self.is_active = False
        self.can_thread = None
        self.seen_ids = {} # Stockage : {id: row_index}
        self.initUI()
        
        self.usb_timer = QTimer()
        self.usb_timer.timeout.connect(self.monitor_usb)
        self.usb_timer.start(1000)

    def initUI(self):
        self.setWindowTitle('CAN Monitor Elite - TECNODJUM V4')
        self.setMinimumSize(800, 600)
        layout = QVBoxLayout()

        # --- Header & Connexion ---
        top_layout = QHBoxLayout()
        self.status_label = QLabel('🔍 Attente USB...')
        top_layout.addWidget(self.status_label)
        
        self.combo = QComboBox()
        self.combo.addItems(["500k (S6)", "250k (S5)", "125k (S4)", "100k (S3)", "1M (S8)"])
        top_layout.addWidget(self.combo)
        
        self.btn_activate = QPushButton('🚀 ACTIVER')
        self.btn_activate.clicked.connect(self.toggle_can)
        top_layout.addWidget(self.btn_activate)
        layout.addLayout(top_layout)

        # --- Outils de Diagnostic (Filtre & Injection) ---
        tools_layout = QHBoxLayout()
        self.filter_input = QLineEdit()
        self.filter_input.setPlaceholderText("Filtrer ID (ex: 1A0)")
        tools_layout.addWidget(QLabel("🔍 Filtre:"))
        tools_layout.addWidget(self.filter_input)

        self.send_input = QLineEdit()
        self.send_input.setPlaceholderText("ID#Data (ex: 7DF#0201050000000000)")
        tools_layout.addWidget(QLabel("📤 Injecter:"))
        tools_layout.addWidget(self.send_input)
        
        self.btn_send = QPushButton("ENVOYER")
        self.btn_send.clicked.connect(self.send_custom_can) # La méthode manquante est ici !
        tools_layout.addWidget(self.btn_send)
        layout.addLayout(tools_layout)

        # --- Tableau Scanner (La "Killer Feature") ---
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["ID (Hex)", "Données (Hex)", "Compteur", "Période (ms)"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setStyleSheet("background-color: #1e1e1e; color: #00ff00; gridline-color: #333;")
        layout.addWidget(self.table)

        self.setLayout(layout)

    def monitor_usb(self):
        ports = [f"/dev/{p}" for p in os.listdir('/dev') if p.startswith('ttyUSB')]
        if ports:
            self.device = ports[0]
            self.status_label.setText(f"✅ Connecté: {self.device}")
        else:
            self.device = None
            self.status_label.setText("❌ Déconnecté")

    def toggle_can(self):
        if not self.is_active:
            self.start_can()
        else:
            self.stop_can()

    def start_can(self):
        if not self.device: return
        speed = self.combo.currentText().split('(')[1][:2].lower()
        subprocess.run(["sudo", "pkill", "slcand"])
        time.sleep(0.2)
        subprocess.run(["sudo", "slcand", "-o", "-c", "-f", f"-{speed}", "-S", "115200", self.device, "can0"])
        time.sleep(1)
        subprocess.run(["sudo", "ip", "link", "set", "can0", "up"])
        
        self.can_thread = CanReaderThread('can0')
        self.can_thread.message_received.connect(self.update_table)
        self.can_thread.start()
        self.is_active = True
        self.btn_activate.setText("🛑 ARRÊTER")

    def stop_can(self):
        if self.can_thread: self.can_thread.running = False
        subprocess.run(["sudo", "ip", "link", "set", "can0", "down"])
        self.is_active = False
        self.btn_activate.setText("🚀 ACTIVER")

    def send_custom_can(self):
        """Envoie une trame personnalisée sur le bus"""
        if not self.is_active: return
        try:
            line = self.send_input.text()
            if "#" not in line: return
            subprocess.run(["sudo", "cansend", "can0", line])
        except Exception as e:
            print(f"Erreur envoi: {e}")

    def update_table(self, msg):
        msg_id = f"{msg.arbitration_id:03X}"
        
        # Filtre
        f_text = self.filter_input.text().strip().upper()
        if f_text and f_text not in msg_id: return

        data_hex = ' '.join([f"{b:02X}" for b in msg.data])
        
        if msg_id not in self.seen_ids:
            # Nouvel ID détecté : on crée une ligne
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(msg_id))
            self.table.setItem(row, 1, QTableWidgetItem(data_hex))
            self.table.setItem(row, 2, QTableWidgetItem("1"))
            self.table.setItem(row, 3, QTableWidgetItem("-"))
            self.seen_ids[msg_id] = [row, time.time()]
        else:
            # ID déjà connu : on met à jour la ligne existante
            row, last_time = self.seen_ids[msg_id]
            now = time.time()
            period = int((now - last_time) * 1000)
            
            # Mise à jour des données
            old_data = self.table.item(row, 1).text()
            item_data = self.table.item(row, 1)
            item_data.setText(data_hex)
            
            # Effet visuel : si la donnée change, on met en surbrillance
            if old_data != data_hex:
                item_data.setBackground(Qt.GlobalColor.darkRed)
                QTimer.singleShot(200, lambda: item_data.setBackground(Qt.GlobalColor.transparent))

            # Mise à jour compteur et période
            count = int(self.table.item(row, 2).text()) + 1
            self.table.item(row, 2).setText(str(count))
            self.table.item(row, 3).setText(f"{period}ms")
            self.seen_ids[msg_id][1] = now

if __name__ == '__main__':
    app = QApplication(sys.argv)
    ex = CanManagerV4()
    ex.show()
    sys.exit(app.exec())