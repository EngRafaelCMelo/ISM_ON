import sys
import os
from PyQt5 import uic
from PyQt5.QtWidgets import QApplication, QMainWindow, QMessageBox, QDialog
from PyQt5.QtGui import QIcon

def resource_path(relative_path: str) -> str:
    base = getattr(sys, "_MEIPASS", os.path.abspath("."))
    return os.path.join(base, relative_path)

class Login(QDialog): 
    def __init__(self):
        super(Login, self).__init__()
        
        caminho_ui = resource_path("tela_login.ui")
        uic.loadUi(caminho_ui, self)
        
        self.setWindowTitle("Login do Sistema")
        nome_logo = "Imagens/logo_ism_transp.png"
        caminho_logo = resource_path(nome_logo)
        if os.path.exists(caminho_logo):
            self.setWindowIcon(QIcon(caminho_logo))
        else:
            print(f"Aviso: Arquivo de logo não encontrado em {caminho_logo}")

        self.btn_login.setAutoDefault(False)
        self.btn_login.setDefault(False)
        self.txt_user.returnPressed.connect(self.txt_senha.setFocus) 
        self.txt_senha.returnPressed.connect(self.fazer_login) 
        self.btn_login.clicked.connect(self.fazer_login)  

    def fazer_login(self):
        usuario = self.txt_user.text()
        senha = self.txt_senha.text()

        if usuario == "admin" and senha == "123":
            self.accept()
        else:
            QMessageBox.warning(self, "Erro", "Usuário ou senha inválidos.")
            self.txt_user.selectAll() 
            self.txt_senha.clear()   
            self.txt_user.setFocus()
