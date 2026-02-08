import sys
import subprocess
import os
import time
from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout, QPushButton, QComboBox, QLabel, QMessageBox
from PyQt6.QtCore import QTimer

class CanManager(QWidget):
    def __init__(self):
        super().__init__()
        self.device = None
        self.initUI()
        self.timer = QTimer()
        self.timer.timeout.connect(self.check_usb)
        self.timer.start(2000)

    def initUI(self):
        self.setWindowTitle('CAN Manager - ThinkPad')
        self.setMinimumSize(400, 250)
        layout = QVBoxLayout()
        
        self.status_label = QLabel('🔍 Recherche du CH341...')
        layout.addWidget(self.status_label)
        
        self.combo = QComboBox()
        self.combo.addItems(["100k (S3)", "125k (S4)", "250k (S5)", "500k (S6)", "1M (S8)"])
        layout.addWidget(self.combo)
        
        self.btn_connect = QPushButton('🚀 Activer CAN')
        self.btn_connect.clicked.connect(self.start_can)
        self.btn_connect.setStyleSheet("background-color: #2ecc71; color: white; font-weight: bold; padding: 10px;")
        layout.addWidget(self.btn_connect)

        self.btn_stop = QPushButton('🛑 Arrêter CAN')
        self.btn_stop.clicked.connect(self.stop_can)
        layout.addWidget(self.btn_stop)
        
        self.setLayout(layout)

    def check_usb(self):
        ports = [f"/dev/{p}" for p in os.listdir('/dev') if p.startswith('ttyUSB')]
        if ports:
            self.device = ports[0]
            self.status_label.setText(f"✅ Adaptateur trouvé : {self.device}")
        else:
            self.status_label.setText("❌ Aucun adaptateur détecté")
            self.device = None

    def start_can(self):
        if not self.device:
            QMessageBox.warning(self, "Erreur", "Branchez l'adaptateur d'abord !")
            return

        speed = self.combo.currentText().split('(')[1][:2]
        try:
            # Nettoyage
            subprocess.run(["pkill", "-9", "slcand"])
            time.sleep(0.5)
            
            # Lancement de slcand (Attention à l'ordre des arguments)
            cmd_slcan = ["slcand", "-o", "-c", "-f", f"-{speed}", "-s", speed, "-S", "3000000", self.device, "can0"]
            subprocess.Popen(cmd_slcan) # Popen pour laisser le démon tourner
            
            time.sleep(1) # Attente cruciale pour que can0 apparaisse
            
            # Activation de l'interface
            subprocess.run(["ip", "link", "set", "can0", "up"])
            
            # Vérification finale
            res = subprocess.run(["ip", "link", "show", "can0"], capture_output=True)
            if b"UP" in res.stdout:
                QMessageBox.information(self, "Succès", "Interface can0 est UP et prête !")
            else:
                QMessageBox.critical(self, "Erreur", "L'interface can0 n'a pas pu démarrer.")
        except Exception as e:
            QMessageBox.critical(self, "Erreur", str(e))

    def stop_can(self):
        subprocess.run(["ip", "link", "set", "can0", "down"])
        subprocess.run(["pkill", "slcand"])
        QMessageBox.information(self, "Info", "Interface can0 fermée.")

if __name__ == '__main__':
    app = QApplication(sys.argv)
    ex = CanManager()
    ex.show()
    sys.exit(app.exec())