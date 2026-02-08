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
        self.setWindowTitle('CAN Manager - TECNODJUM')
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
            QMessageBox.warning(self, "Erreur", "Branchez l'adaptateur !")
            return

        # On récupère le code vitesse proprement, ex: "S6"
        txt = self.combo.currentText()
        speed_code = txt.split('(')[1][:2].lower() # donne "s6"

        try:
            # 1. On tue les anciens processus pour libérer le port
            subprocess.run(["sudo", "pkill", "-9", "slcand"])
            time.sleep(0.5)
            
            # 2. On lance slcand comme vous l'avez fait manuellement
            # Note: -o (open), -c (close), -f (status), -s6 (vitesse CAN), -S (vitesse UART)
            cmd = ["sudo", "slcand", "-o", "-c", "-f", f"-{speed_code}", "-S", "3000000", self.device, "can0"]
            subprocess.run(cmd) 
            
            time.sleep(1) # On laisse le temps au noyau de digérer
            
            # 3. On active l'interface
            subprocess.run(["sudo", "ip", "link", "set", "can0", "up"])
            
            # 4. Vérification
            check = subprocess.run(["ls", "/sys/class/net/"], capture_output=True, text=True)
            if "can0" in check.stdout:
                QMessageBox.information(self, "Succès", "can0 est en ligne ! SavvyCAN peut maintenant s'y connecter.")
            else:
                QMessageBox.critical(self, "Erreur", "L'interface can0 n'apparaît toujours pas.")
                
        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Crash: {str(e)}")

    def stop_can(self):
        subprocess.run(["ip", "link", "set", "can0", "down"])
        subprocess.run(["pkill", "slcand"])
        QMessageBox.information(self, "Info", "Interface can0 fermée.")

if __name__ == '__main__':
    app = QApplication(sys.argv)
    ex = CanManager()
    ex.show()
    sys.exit(app.exec())