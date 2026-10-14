import os
import sys

from PyQt5 import uic
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QDialog, QMessageBox

from auth import UserStore


def resource_path(relative_path: str) -> str:
    base = getattr(sys, "_MEIPASS", os.path.abspath("."))
    return os.path.join(base, relative_path)


class Login(QDialog):
    def __init__(self, user_store_path="users.json"):
        super().__init__()
        uic.loadUi(resource_path("tela_login.ui"), self)
        self.setWindowTitle("Login do Sistema")
        logo_path = resource_path("Imagens/logo_ism_transp.png")
        if os.path.exists(logo_path):
            self.setWindowIcon(QIcon(logo_path))
        self.btn_login.setAutoDefault(False)
        self.btn_login.setDefault(False)
        self.user_store = UserStore(user_store_path)
        self.authenticated_user = None
        if not self.user_store.has_users():
            self.setWindowTitle("Primeiro acesso - criar administrador")
            self.btn_login.setText("Criar administrador")
        self.txt_user.returnPressed.connect(self.txt_senha.setFocus)
        self.txt_senha.returnPressed.connect(self.fazer_login)
        self.btn_login.clicked.connect(self.fazer_login)

    def fazer_login(self):
        usuario = self.txt_user.text()
        senha = self.txt_senha.text()
        try:
            if not self.user_store.has_users():
                self.user_store.create_user(usuario, senha, "admin")
                self.authenticated_user = {"username": usuario.strip(), "role": "admin"}
                self.accept()
                return
            user = self.user_store.authenticate(usuario, senha)
            if user is not None:
                self.authenticated_user = user
                self.accept()
                return
        except ValueError as error:
            QMessageBox.warning(self, "Primeiro acesso", str(error))
            return
        QMessageBox.warning(self, "Erro", "Usuario ou senha invalidos.")
        self.txt_user.selectAll()
        self.txt_senha.clear()
        self.txt_user.setFocus()
