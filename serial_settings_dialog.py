from __future__ import annotations

from typing import Any, Callable, Dict

from PyQt5.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from serial_utils import list_available_ports


class SerialSettingsDialog(QDialog):
    """Configuracao de bomba/estufa; nao abre a porta serial."""

    def __init__(self, parent, config: Dict[str, Any], can_apply: Callable[[], bool]):
        super().__init__(parent)
        self.setWindowTitle("Configuracao de comunicacao")
        self.resize(420, 260)
        self._config = config
        self._can_apply = can_apply
        root = QVBoxLayout(self)
        root.addWidget(QLabel("As portas so podem ser alteradas com os dispositivos desconectados."))
        self.fields: Dict[str, Dict[str, Any]] = {}
        form = QFormLayout()
        root.addLayout(form)
        ports = list_available_ports()
        port_names = [item["device"] for item in ports]
        for name, label in (("pump", "Bomba"), ("oven", "Estufa")):
            device = dict(config.get("devices", {}).get(name, {}))
            port = QComboBox()
            port.setEditable(True)
            port.addItems(port_names)
            if device.get("port") and device["port"] not in port_names:
                port.addItem(str(device["port"]))
            port.setCurrentText(str(device.get("port", "")))
            baud = QSpinBox(); baud.setRange(1, 4_000_000); baud.setValue(int(device.get("baudrate", 9600)))
            timeout = QDoubleSpinBox(); timeout.setRange(0.01, 120.0); timeout.setDecimals(2); timeout.setValue(float(device.get("timeout_s", 1.0)))
            stale = QDoubleSpinBox(); stale.setRange(0.1, 3600.0); stale.setDecimals(2); stale.setValue(float(device.get("stale_after_s", 3.0)))
            self.fields[name] = {"port": port, "baudrate": baud, "timeout_s": timeout, "stale_after_s": stale}
            form.addRow(f"{label} - porta:", port)
            form.addRow(f"{label} - baudrate:", baud)
            form.addRow(f"{label} - timeout (s):", timeout)
            form.addRow(f"{label} - stale (s):", stale)
        refresh = QPushButton("Atualizar portas detectadas")
        refresh.clicked.connect(self.refresh_ports)
        root.addWidget(refresh)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def refresh_ports(self):
        values = {name: fields["port"].currentText() for name, fields in self.fields.items()}
        ports = [item["device"] for item in list_available_ports()]
        for name, fields in self.fields.items():
            combo = fields["port"]
            current = values[name]
            combo.clear(); combo.addItems(ports)
            if current and current not in ports:
                combo.addItem(current)
            combo.setCurrentText(current)

    def _accept(self):
        if not self._can_apply():
            self.setWindowTitle("Desconecte bomba e estufa antes de salvar")
            return
        for name, fields in self.fields.items():
            if not fields["port"].currentText().strip():
                self.setWindowTitle(f"Informe a porta de {name}")
                return
        self.accept()

    def values(self) -> Dict[str, Dict[str, Any]]:
        return {
            name: {
                "port": fields["port"].currentText().strip(),
                "baudrate": fields["baudrate"].value(),
                "timeout_s": fields["timeout_s"].value(),
                "stale_after_s": fields["stale_after_s"].value(),
            }
            for name, fields in self.fields.items()
        }
