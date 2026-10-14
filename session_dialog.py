from PyQt5.QtWidgets import QDialog, QDialogButtonBox, QFormLayout, QLineEdit, QComboBox


class SessionDialog(QDialog):
    def __init__(self, parent=None, operator: str = ""):
        super().__init__(parent)
        self.setWindowTitle("Identificacao do ensaio")
        form = QFormLayout(self)
        self.session_id = QLineEdit()
        self.sample_name = QLineEdit()
        self.operator = QLineEdit(operator)
        self.notes = QLineEdit()
        self.test_type = QComboBox()
        self.test_type.addItems(["Coreflooding", "Porosidade", "Permeabilidade", "Pulse-decay", "Outro"])
        form.addRow("Identificador:", self.session_id)
        form.addRow("Amostra:", self.sample_name)
        form.addRow("Operador:", self.operator)
        form.addRow("Observacoes:", self.notes)
        form.addRow("Tipo:", self.test_type)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def _accept(self):
        if not self.sample_name.text().strip() or not self.operator.text().strip():
            self.setWindowTitle("Informe amostra e operador")
            return
        self.accept()

    def values(self):
        return {
            "session_id": self.session_id.text().strip(),
            "sample_name": self.sample_name.text().strip(),
            "operator": self.operator.text().strip(),
            "notes": self.notes.text().strip(),
            "test_type": self.test_type.currentText(),
        }
