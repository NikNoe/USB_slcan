import sys
import subprocess
import os
from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout, QPushButton, QComboBox, QLabel, QMessageBox
from PyQt6.QtCore import QTimer

class CanManager(QWidget):
    def __init__(self):
        super().__init__()
        self.initUI()
        
        # Timer pour scanner l'USB toutes les 2 secondes
        self.timer = QTimer()
        self.timer.timeout.connect(self.check_usb)
        self.timer.start(2000)

    def initUI(self):
        self.setWindowTitle('USB-CAN Manager (CH341)')
        self.setGeometry(300, 300, 350, 200)
        
        layout = QVBoxLayout()
        
        self.status_label = QLabel('Statut : En attente du périphérique...')
        layout.addWidget(self.status_label)
        
        self.combo = QComboBox()
        self.combo.addItems(["100k (S3)", "250k (S5)", "500k (S6)", "1M (S8)"])
        self.combo.setEnabled(False)
        layout.addWidget(self.combo)
        
        self.btn_connect = QPushButton('Activer CAN')
        self.btn_connect.setEnabled(False)
        self.btn_connect.clicked.connect(self.start_can)
        layout.addWidget(self.btn_connect)

        self.btn_stop = QPushButton('Arrêter CAN')
        self.btn_stop.clicked.connect(self.stop_can)
        layout.addWidget(self.btn_stop)
        
        self.setLayout(layout)

    def check_usb(self):
        # Cherche si /dev/ttyUSB* existe
        ports = [f"/dev/{p}" for p in os.listdir('/dev') if p.startswith('ttyUSB')]
        if ports:
            self.device = ports[0]
            self.status_label.setText(f"Connecté sur : {self.device}")
            self.combo.setEnabled(True)
            self.btn_connect.setEnabled(True)
        else:
            self.status_label.setText("Statut : Aucun adaptateur détecté")
            self.combo.setEnabled(False)
            self.btn_connect.setEnabled(False)

    def start_can(self):
        speed = self.combo.currentText().split('(')[1][:2] # Récupère S3, S5, S6...
        try:
            # On nettoie avant de lancer
            subprocess.run(["sudo", "pkill", "slcand"])
            # Lancement de slcand
            subprocess.run(["sudo", "slcand", "-o", f"-s{speed}", "-t", "hw", "-S", "3000000", self.device, "can0"])
            subprocess.run(["sudo", "ip", "link", "set", "can0", "up"])
            QMessageBox.information(self, "Succès", "Interface can0 activée !")
        except Exception as e:
            QMessageBox.critical(self, "Erreur", str(e))

    def stop_can(self):
        subprocess.run(["sudo", "ip", "link", "set", "can0", "down"])
        subprocess.run(["sudo", "pkill", "slcand"])
        QMessageBox.information(self, "Info", "Interface arrêtée.")

if __name__ == '__main__':
    app = QApplication(sys.argv)
    ex = CanManager()
    ex.show()
    sys.exit(app.exec())