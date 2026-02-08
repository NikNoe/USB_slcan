import sys
import subprocess
import os
import time
import can 
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, 
                             QPushButton, QComboBox, QLabel, QTextEdit, QMessageBox)
from PyQt6.QtCore import QTimer, QThread, pyqtSignal

# --- Thread de lecture CAN pour ne pas bloquer l'interface ---
class CanReaderThread(QThread):
    message_received = pyqtSignal(object)
    error_signal = pyqtSignal(str)

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
                if msg:
                    self.message_received.emit(msg)
            except Exception as e:
                self.error_signal.emit(str(e))
                self.running = False
        if bus:
            bus.shutdown()

class CanManager(QWidget):
    def __init__(self):
        # Chargement des pilotes au démarrage
        subprocess.run(["sudo", "modprobe", "can", "can_raw", "slcan"])
        super().__init__()
        self.device = None
        self.can_thread = None
        self.msg_count = 0
        self.initUI()
        
        # Timers
        self.usb_timer = QTimer()
        self.usb_timer.timeout.connect(self.check_usb)
        self.usb_timer.start(2000)

        self.load_timer = QTimer()
        self.load_timer.timeout.connect(self.update_load)
        self.load_timer.start(1000)

    def initUI(self):
        self.setWindowTitle('CAN Manager - TECNODJUM Pro')
        self.setMinimumSize(500, 400)
        layout = QVBoxLayout()
        
        self.status_label = QLabel('🔍 Recherche du CH341...')
        layout.addWidget(self.status_label)
        
        # Ligne Sélection et Activation
        h_layout = QHBoxLayout()
        self.combo = QComboBox()
        self.combo.addItems(["100k (S3)", "125k (S4)", "250k (S5)", "500k (S6)", "1M (S8)"])
        h_layout.addWidget(self.combo)
        
        self.btn_connect = QPushButton('🚀 Activer CAN')
        self.btn_connect.clicked.connect(self.start_can)
        self.btn_connect.setStyleSheet("background-color: #2ecc71; color: white; font-weight: bold; padding: 8px;")
        h_layout.addWidget(self.btn_connect)
        layout.addLayout(h_layout)

        # Zone Monitoring (LED et Messages/sec)
        mon_layout = QHBoxLayout()
        self.led = QLabel()
        self.led.setFixedSize(15, 15)
        self.led.setStyleSheet("background-color: gray; border-radius: 7px;")
        mon_layout.addWidget(self.led)
        
        self.load_label = QLabel('Trafic: 0 msg/s')
        mon_layout.addWidget(self.load_label)
        layout.addLayout(mon_layout)

        # Log des messages
        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setStyleSheet("background-color: #1e1e1e; color: #00ff00; font-family: monospace;")
        layout.addWidget(self.log_view)

        self.btn_stop = QPushButton('🛑 Arrêter CAN')
        self.btn_stop.clicked.connect(self.stop_can)
        layout.addWidget(self.btn_stop)
        
        self.setLayout(layout)

    def check_usb(self):
        ports = [f"/dev/{p}" for p in os.listdir('/dev') if p.startswith('ttyUSB')]
        if ports:
            self.device = ports[0]
            if "Recherche" in self.status_label.text():
                self.status_label.setText(f"✅ Adaptateur trouvé : {self.device}")
        else:
            self.status_label.setText("❌ Aucun adaptateur détecté")
            self.device = None

    def start_can(self):
        if not self.device:
            QMessageBox.warning(self, "Erreur", "Aucun adaptateur USB détecté !")
            return

        speed = self.combo.currentText().split('(')[1][:2].lower()
        
        try:
            self.log_view.append("🔄 Nettoyage et configuration...")
            subprocess.run(["sudo", "pkill", "-9", "slcand"])
            subprocess.run(["sudo", "ip", "link", "set", "can0", "down"], stderr=subprocess.DEVNULL)
            time.sleep(0.5)
            
            # Utilisation de 115200 baud pour la stabilité série du CH341
            cmd = ["sudo", "slcand", "-o", "-c", "-f", f"-{speed}", "-S", "115200", self.device, "can0"]
            subprocess.Popen(cmd) 
            
            time.sleep(2.0) 
            
            # Activation
            res = subprocess.run(["sudo", "ip", "link", "set", "can0", "up", "txqueuelen", "1000"], capture_output=True)
            
            if res.returncode == 0:
                self.log_view.append("✅ can0 est UP !")
                self.start_monitoring()
            else:
                self.log_view.append("❌ Erreur: L'interface n'a pas pu démarrer.")
                
        except Exception as e:
            self.log_view.append(f"❌ Erreur: {str(e)}")

    def start_monitoring(self):
        if self.can_thread and self.can_thread.isRunning():
            self.can_thread.stop()
        
        self.can_thread = CanReaderThread('can0')
        self.can_thread.message_received.connect(self.process_msg)
        self.can_thread.error_signal.connect(lambda e: self.log_view.append(f"⚠️ Bus Error: {e}"))
        self.can_thread.start()

    def process_msg(self, msg):
        self.msg_count += 1
        # Faire clignoter la LED
        self.led.setStyleSheet("background-color: #00ff00; border-radius: 7px;")
        QTimer.singleShot(100, lambda: self.led.setStyleSheet("background-color: #008800; border-radius: 7px;"))
        
        # Affichage simplifié dans le log
        data_hex = ' '.join([f"{b:02X}" for b in msg.data])
        self.log_view.append(f"ID: {msg.arbitration_id:03X} | Data: {data_hex}")
        
        # Limiter le nombre de lignes pour ne pas ralentir l'app
        cursor = self.log_view.textCursor()
        if self.log_view.document().blockCount() > 50:
            cursor.movePosition(cursor.MoveOperation.Start)
            cursor.select(cursor.SelectionType.BlockUnderCursor)
            cursor.removeSelectedText()
            cursor.deleteChar()

    def update_load(self):
        self.load_label.setText(f"Trafic: {self.msg_count} msg/s")
        self.msg_count = 0

    def stop_can(self):
        if self.can_thread:
            self.can_thread.running = False
        subprocess.run(["sudo", "ip", "link", "set", "can0", "down"])
        subprocess.run(["sudo", "pkill", "slcand"])
        self.log_view.append("🛑 Interface can0 arrêtée.")

if __name__ == '__main__':
    app = QApplication(sys.argv)
    ex = CanManager()
    ex.show()
    sys.exit(app.exec())