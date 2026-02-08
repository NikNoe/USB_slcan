import sys
import subprocess
import os
import time
import can
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, 
                             QPushButton, QComboBox, QLabel, QTextEdit, QMessageBox)
from PyQt6.QtCore import QTimer, QThread, pyqtSignal, Qt

# Identifiants CH341 standards
CH341_VID = "1a86"
CH341_PID = "7523"

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
                if msg: self.message_received.emit(msg)
            except:
                self.running = False
        if bus: bus.shutdown()

class CanManagerV3(QWidget):
    def __init__(self):
        super().__init__()
        self.device = None
        self.is_active = False # État souhaité par l'utilisateur
        self.can_thread = None
        self.msg_count = 0
        
        self.initUI()
        
        # Timer de surveillance USB (Plus rapide pour l'auto-reconnexion)
        self.usb_timer = QTimer()
        self.usb_timer.timeout.connect(self.monitor_usb_and_bus)
        self.usb_timer.start(1000)

    def initUI(self):
        self.setWindowTitle('CAN Monitor Pro - TECNODJUM V3')
        self.setMinimumSize(550, 500)
        layout = QVBoxLayout()
        
        # Statut matériel
        self.status_label = QLabel('🔍 En attente du CH341...')
        self.status_label.setStyleSheet("font-weight: bold; color: orange;")
        layout.addWidget(self.status_label)
        
        # État du Bus (Diagnostic)
        self.bus_state_label = QLabel('État Bus: INCONNU')
        self.bus_state_label.setStyleSheet("padding: 5px; background: #333; color: white;")
        layout.addWidget(self.bus_state_label)

        # Contrôles
        h_layout = QHBoxLayout()
        self.combo = QComboBox()
        self.combo.addItems(["500k (S6)", "100k (S3)","250k (S5)", "125k (S4)", "1M (S8)"])
        h_layout.addWidget(self.combo)
        
        self.btn_connect = QPushButton('🚀 ACTIVER')
        self.btn_connect.clicked.connect(self.toggle_activation)
        self.btn_connect.setStyleSheet("background-color: #2ecc71; color: white; font-weight: bold; height: 30px;")
        h_layout.addWidget(self.btn_connect)
        layout.addLayout(h_layout)

        # Monitoring
        mon_layout = QHBoxLayout()
        self.led = QLabel(); self.led.setFixedSize(15, 15)
        self.led.setStyleSheet("background-color: gray; border-radius: 7px;")
        mon_layout.addWidget(self.led)
        self.load_label = QLabel('Trafic: 0 msg/s')
        mon_layout.addWidget(self.load_label)
        layout.addLayout(mon_layout)

        # Logs
        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setStyleSheet("background-color: #1e1e1e; color: #00ff00; font-family: monospace;")
        layout.addWidget(self.log_view)

        # Boutons d'action rapide
        btn_layout = QHBoxLayout()
        self.btn_reset = QPushButton('🔄 Reset Bus (Error Recovery)')
        self.btn_reset.clicked.connect(self.reset_bus)
        btn_layout.addWidget(self.btn_reset)
        
        self.btn_clear = QPushButton('🧹 Effacer Log')
        self.btn_clear.clicked.connect(lambda: self.log_view.clear())
        btn_layout.addWidget(self.btn_clear)
        layout.addLayout(btn_layout)

        self.setLayout(layout)

    def find_ch341(self):
        """Identifie précisément le CH341 via ses IDs USB"""
        try:
            import pyudev
            context = pyudev.Context()
            for device in context.list_devices(subsystem='tty'):
                if 'ID_VENDOR_ID' in device and device.get('ID_VENDOR_ID') == CH341_VID:
                    return device.device_node
        except ImportError:
            # Fallback si pyudev n'est pas installé
            ports = [f"/dev/{p}" for p in os.listdir('/dev') if p.startswith('ttyUSB')]
            return ports[0] if ports else None
        return None

    def monitor_usb_and_bus(self):
        current_dev = self.find_ch341()
        
        # 1. Gestion de la présence USB
        if current_dev:
            self.device = current_dev
            self.status_label.setText(f"✅ CH341 détecté sur {self.device}")
            self.status_label.setStyleSheet("color: #2ecc71;")
            
            # AUTO-RECONNEXION : Si l'utilisateur voulait que ce soit actif mais que ça ne l'est pas
            if self.is_active and not self.is_interface_up():
                self.log_view.append("🔄 Reconnexion automatique en cours...")
                self.start_can_logic()
        else:
            if self.device: # Vient d'être débranché
                self.log_view.append("⚠️ USB Débranché !")
                self.stop_can_logic()
            self.device = None
            self.status_label.setText("❌ CH341 non trouvé")
            self.status_label.setStyleSheet("color: red;")

        # 2. Diagnostic de l'état du Bus
        if self.is_interface_up():
            self.update_bus_status()

    def is_interface_up(self):
        res = subprocess.run(["ip", "link", "show", "can0"], capture_output=True, text=True)
        return "UP" in res.stdout and "LOWER_UP" in res.stdout

    def update_bus_status(self):
        try:
            res = subprocess.run(["ip", "-details", "-statistics", "link", "show", "can0"], 
                                 capture_output=True, text=True)
            output = res.stdout
            if "ERROR-PASSIVE" in output: state = "⚠️ ERROR-PASSIVE"; col = "orange"
            elif "BUS-OFF" in output: state = "🛑 BUS-OFF"; col = "red"
            elif "ERROR-ACTIVE" in output: state = "🟢 ERROR-ACTIVE (Normal)"; col = "#2ecc71"
            else: state = "OK"; col = "white"
            self.bus_state_label.setText(f"État Bus: {state}")
            self.bus_state_label.setStyleSheet(f"background: #222; color: {col}; padding: 5px;")
        except: pass

    def toggle_activation(self):
        if not self.is_active:
            self.is_active = True
            self.start_can_logic()
            self.btn_connect.setText("🛑 DÉSACTIVER")
            self.btn_connect.setStyleSheet("background-color: #e74c3c; color: white; font-weight: bold;")
        else:
            self.is_active = False
            self.stop_can_logic()
            self.btn_connect.setText("🚀 ACTIVER")
            self.btn_connect.setStyleSheet("background-color: #2ecc71; color: white; font-weight: bold;")

    def start_can_logic(self):
        if not self.device: return
        speed = self.combo.currentText().split('(')[1][:2].lower()
        subprocess.run(["sudo", "pkill", "-9", "slcand"])
        time.sleep(0.2)
        subprocess.run(["sudo", "modprobe", "can", "can_raw", "slcan"])
        cmd = ["sudo", "slcand", "-o", "-c", "-f", f"-{speed}", "-S", "115200", self.device, "can0"]
        subprocess.Popen(cmd)
        time.sleep(1.5)
        subprocess.run(["sudo", "ip", "link", "set", "can0", "up", "txqueuelen", "1000"])
        
        # Lancer thread de lecture
        self.can_thread = CanReaderThread('can0')
        self.can_thread.message_received.connect(self.process_msg)
        self.can_thread.start()

    def stop_can_logic(self):
        if self.can_thread: self.can_thread.running = False
        subprocess.run(["sudo", "ip", "link", "set", "can0", "down"], stderr=subprocess.DEVNULL)
        subprocess.run(["sudo", "pkill", "slcand"], stderr=subprocess.DEVNULL)

    def reset_bus(self):
        self.log_view.append("♻️ Réinitialisation du Bus CAN...")
        self.stop_can_logic()
        time.sleep(1)
        if self.is_active: self.start_can_logic()

    def process_msg(self, msg):
        self.msg_count += 1
        self.led.setStyleSheet("background-color: #00ff00; border-radius: 7px;")
        QTimer.singleShot(100, lambda: self.led.setStyleSheet("background-color: #008800; border-radius: 7px;"))
        data_hex = ' '.join([f"{b:02X}" for b in msg.data])
        self.log_view.append(f"ID: {msg.arbitration_id:03X} | {data_hex}")
        if self.log_view.document().blockCount() > 50: self.log_view.clear()

    def update_load(self):
        self.load_label.setText(f"Trafic: {self.msg_count} msg/s")
        self.msg_count = 0

if __name__ == '__main__':
    app = QApplication(sys.argv)
    ex = CanManagerV3()
    ex.show()
    sys.exit(app.exec())