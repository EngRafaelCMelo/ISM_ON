from __future__ import annotations

from typing import Dict, Any, Callable, Optional
from dataclasses import dataclass

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QWidget,
    QTableWidget, QTableWidgetItem, QPushButton, QLabel, QMessageBox,
    QDoubleSpinBox, QFormLayout
)
from PyQt5.QtCore import Qt, QTimer

from calibration_store import load_calibration, save_calibration, ensure_channel


@dataclass
class CalPoint:
    raw: Optional[float] = None
    ref: Optional[float] = None


class CalibrationDialog(QDialog):
    """
    Calibração 2 pontos por canal:
      ref = a*raw + b
    - Captura RAW ao vivo
    - Usuário digita referência (ZERO e SPAN)
    - Calcula e salva a,b
    Também salva volumes do sistema.
    """
    def __init__(
        self,
        parent,
        channel_names,
        get_raw_by_name: Callable[[str], Optional[float]],
        get_corr_by_name: Callable[[str], Optional[float]],
        calibration_path: str = "calibration.json",
    ):
        super().__init__(parent)
        self.setWindowTitle("Modo Calibração")
        self.resize(860, 520)
        self.setModal(True)

        self.channel_names = channel_names
        self.get_raw_by_name = get_raw_by_name
        self.get_corr_by_name = get_corr_by_name
        self.calibration_path = calibration_path

        self.cal = load_calibration(self.calibration_path)
        for n in self.channel_names:
            ensure_channel(self.cal, n)

        # pontos capturados
        self.zero_points: Dict[str, CalPoint] = {n: CalPoint() for n in self.channel_names}
        self.span_points: Dict[str, CalPoint] = {n: CalPoint() for n in self.channel_names}

        root = QVBoxLayout(self)
        tabs = QTabWidget()
        root.addWidget(tabs)

        # ===== Tab 1: Sensores =====
        tab_sensors = QWidget()
        tabs.addTab(tab_sensors, "Sensores (ZERO/SPAN)")
        v1 = QVBoxLayout(tab_sensors)

        self.tbl = QTableWidget(len(self.channel_names), 11)
        self.tbl.setHorizontalHeaderLabels([
            "Canal",
            "RAW (bar)",
            "Corrigido (bar)",
            "a",
            "b",
            "ZERO ref",
            "Capturar ZERO",
            "SPAN ref",
            "Capturar SPAN",
            "Calcular",
            "Salvar"
        ])
        self.tbl.verticalHeader().setVisible(False)
        self.tbl.setAlternatingRowColors(True)
        self.tbl.setSelectionMode(self.tbl.NoSelection)
        self.capture_buttons = {"zero": [], "span": []}

        for r, name in enumerate(self.channel_names):
            self.tbl.setItem(r, 0, QTableWidgetItem(name))
            self.tbl.item(r, 0).setFlags(Qt.ItemIsEnabled)

            # RAW / Corr
            for c in (1, 2):
                it = QTableWidgetItem("--")
                it.setFlags(Qt.ItemIsEnabled)
                it.setTextAlignment(Qt.AlignCenter)
                self.tbl.setItem(r, c, it)

            # a / b (read only)
            a_it = QTableWidgetItem(f"{self.cal['channels'][name]['a']:.6f}")
            b_it = QTableWidgetItem(f"{self.cal['channels'][name]['b']:.6f}")
            for it in (a_it, b_it):
                it.setFlags(Qt.ItemIsEnabled)
                it.setTextAlignment(Qt.AlignCenter)
            self.tbl.setItem(r, 3, a_it)
            self.tbl.setItem(r, 4, b_it)

            # ZERO ref input
            zero_ref = QDoubleSpinBox()
            zero_ref.setRange(-1e9, 1e9)
            zero_ref.setDecimals(4)
            zero_ref.setValue(0.0)
            self.tbl.setCellWidget(r, 5, zero_ref)

            btn_cap_zero = QPushButton("Capturar")
            self.tbl.setCellWidget(r, 6, btn_cap_zero)
            self.capture_buttons["zero"].append(btn_cap_zero)

            # SPAN ref input (VARIÁVEL)
            span_ref = QDoubleSpinBox()
            span_ref.setRange(-1e9, 1e9)
            span_ref.setDecimals(4)
            span_ref.setValue(100.0)
            self.tbl.setCellWidget(r, 7, span_ref)

            btn_cap_span = QPushButton("Capturar")
            self.tbl.setCellWidget(r, 8, btn_cap_span)
            self.capture_buttons["span"].append(btn_cap_span)

            btn_calc = QPushButton("Calcular")
            self.tbl.setCellWidget(r, 9, btn_calc)

            btn_save = QPushButton("Salvar")
            self.tbl.setCellWidget(r, 10, btn_save)

            # callbacks por linha
            btn_cap_zero.clicked.connect(lambda _, rr=r: self.capture_zero(rr))
            btn_cap_span.clicked.connect(lambda _, rr=r: self.capture_span(rr))
            btn_calc.clicked.connect(lambda _, rr=r: self.compute_ab(rr))
            btn_save.clicked.connect(lambda _, rr=r: self.save_line(rr))

        self.tbl.resizeColumnsToContents()
        self.tbl.horizontalHeader().setStretchLastSection(True)

        v1.addWidget(self.tbl)
        self.lbl_updated = QLabel()
        v1.addWidget(self.lbl_updated)

        row2 = QHBoxLayout()
        self.btn_save_all = QPushButton("Salvar Tudo")
        self.btn_reload = QPushButton("Recarregar do arquivo")
        self.btn_close = QPushButton("Fechar")
        row2.addStretch(1)
        row2.addWidget(self.btn_reload)
        row2.addWidget(self.btn_save_all)
        row2.addWidget(self.btn_close)
        v1.addLayout(row2)

        self.btn_close.clicked.connect(self.accept)
        self.btn_save_all.clicked.connect(self.save_all)
        self.btn_reload.clicked.connect(self.reload)

        # ===== Tab 2: Volumes =====
        tab_vol = QWidget()
        tabs.addTab(tab_vol, "Volumes (Equipamento)")
        f2 = QFormLayout(tab_vol)

        self.vref = QDoubleSpinBox(); self.vref.setRange(0.001, 1e9); self.vref.setDecimals(3)
        self.vcell = QDoubleSpinBox(); self.vcell.setRange(0.001, 1e9); self.vcell.setDecimals(3)
        self.vu = QDoubleSpinBox(); self.vu.setRange(0.001, 1e9); self.vu.setDecimals(3)
        self.vd = QDoubleSpinBox(); self.vd.setRange(0.001, 1e9); self.vd.setDecimals(3)

        vols = self.cal.get("volumes", {})
        self.vref.setValue(float(vols.get("Vref_cm3", 10.0)))
        self.vcell.setValue(float(vols.get("Vcell_cm3", 20.0)))
        self.vu.setValue(float(vols.get("Vu_cm3", 10.0)))
        self.vd.setValue(float(vols.get("Vd_cm3", 10.0)))

        f2.addRow("Vref (cm³):", self.vref)
        f2.addRow("Vcell vazio (cm³):", self.vcell)
        f2.addRow("Vu (cm³):", self.vu)
        f2.addRow("Vd (cm³):", self.vd)

        btns_vol = QHBoxLayout()
        self.btn_save_vol = QPushButton("Salvar Volumes")
        btns_vol.addStretch(1)
        btns_vol.addWidget(self.btn_save_vol)
        f2.addRow(btns_vol)

        self.btn_save_vol.clicked.connect(self.save_volumes)

        # ===== Tab 3: Validação =====
        tab_val = QWidget()
        tabs.addTab(tab_val, "Validação")
        v3 = QVBoxLayout(tab_val)

        self.lbl_val = QLabel(
            "• Estabilidade: mede desvio padrão das leituras RAW (últimos ~5s).\n"
            "• Leak test: (simples) use P1 como referência e observe queda por minuto.\n"
            "Obs: para um leak test completo, ideal ter rotina de válvulas/etapas do equipamento."
        )
        self.lbl_val.setWordWrap(True)

        self.btn_check_stab = QPushButton("Checar Estabilidade (RAW)")
        self.btn_check_stab.clicked.connect(self.check_stability)

        v3.addWidget(self.lbl_val)
        v3.addSpacing(10)
        v3.addWidget(self.btn_check_stab)
        v3.addStretch(1)

        # timer para atualizar RAW/Corr na tabela
        self.timer = QTimer(self)
        self.timer.setInterval(250)
        self.timer.timeout.connect(self.refresh_live_values)
        self.timer.start()
        self.refresh_live_values()
        self.refresh_metadata_label()

    def reload(self):
        self.cal = load_calibration(self.calibration_path)
        for n in self.channel_names:
            ensure_channel(self.cal, n)
        self.refresh_ab_columns()
        self.refresh_metadata_label()
        QMessageBox.information(self, "Calibração", "Recarregado do arquivo.")

    def refresh_ab_columns(self):
        for r, name in enumerate(self.channel_names):
            a = float(self.cal["channels"][name].get("a", 1.0))
            b = float(self.cal["channels"][name].get("b", 0.0))
            self.tbl.item(r, 3).setText(f"{a:.6f}")
            self.tbl.item(r, 4).setText(f"{b:.6f}")

    def refresh_metadata_label(self):
        updated = self.cal.get("metadata", {}).get("updated_at_utc", "nunca")
        self.lbl_updated.setText(f"Ultima calibracao: {updated}")

    def refresh_live_values(self):
        for r, name in enumerate(self.channel_names):
            raw = self.get_raw_by_name(name)
            corr = self.get_corr_by_name(name)
            self.tbl.item(r, 1).setText("--" if raw is None else f"{raw:.4f}")
            self.tbl.item(r, 2).setText("--" if corr is None else f"{corr:.4f}")
            self.capture_buttons["zero"][r].setEnabled(raw is not None)
            self.capture_buttons["span"][r].setEnabled(raw is not None)

    def capture_zero(self, row: int):
        name = self.channel_names[row]
        raw = self.get_raw_by_name(name)
        if raw is None:
            QMessageBox.warning(self, "Aviso", f"Sem leitura RAW para {name} ainda.")
            return
        zero_ref: QDoubleSpinBox = self.tbl.cellWidget(row, 5)
        self.zero_points[name] = CalPoint(raw=float(raw), ref=float(zero_ref.value()))
        QMessageBox.information(self, "ZERO capturado", f"{name}\nRAW={raw:.4f} bar\nREF={zero_ref.value():.4f} bar")

    def capture_span(self, row: int):
        name = self.channel_names[row]
        raw = self.get_raw_by_name(name)
        if raw is None:
            QMessageBox.warning(self, "Aviso", f"Sem leitura RAW para {name} ainda.")
            return
        span_ref: QDoubleSpinBox = self.tbl.cellWidget(row, 7)
        self.span_points[name] = CalPoint(raw=float(raw), ref=float(span_ref.value()))
        QMessageBox.information(self, "SPAN capturado", f"{name}\nRAW={raw:.4f} bar\nREF={span_ref.value():.4f} bar")

    def compute_ab(self, row: int):
        name = self.channel_names[row]
        z = self.zero_points[name]
        s = self.span_points[name]

        if z.raw is None or z.ref is None or s.raw is None or s.ref is None:
            QMessageBox.warning(self, "Aviso", f"Capture ZERO e SPAN para {name} antes de calcular.")
            return
        if abs(s.raw - z.raw) < 1e-9:
            QMessageBox.critical(self, "Erro", f"RAW ZERO e RAW SPAN são iguais para {name}.")
            return

        a = (s.ref - z.ref) / (s.raw - z.raw)
        b = z.ref - a * z.raw

        self.cal["channels"][name]["a"] = float(a)
        self.cal["channels"][name]["b"] = float(b)
        self.refresh_ab_columns()

        QMessageBox.information(self, "Calibração calculada", f"{name}\na={a:.6f}\nb={b:.6f}")

    def save_line(self, row: int):
        name = self.channel_names[row]
        if QMessageBox.question(
            self, "Confirmar salvamento", f"Salvar a calibracao de {name}? Um backup sera criado."
        ) != QMessageBox.Yes:
            return
        save_calibration(self.calibration_path, self.cal)
        self.refresh_metadata_label()
        QMessageBox.information(self, "Salvo", f"Calibração salva para {name} (arquivo).")

    def save_all(self):
        if QMessageBox.question(
            self, "Confirmar salvamento", "Salvar todas as calibracoes? Um backup sera criado."
        ) != QMessageBox.Yes:
            return
        save_calibration(self.calibration_path, self.cal)
        self.refresh_metadata_label()
        QMessageBox.information(self, "Salvo", "Calibração completa salva (arquivo).")

    def save_volumes(self):
        if QMessageBox.question(
            self, "Confirmar salvamento", "Salvar os volumes? Um backup sera criado."
        ) != QMessageBox.Yes:
            return
        self.cal.setdefault("volumes", {})
        self.cal["volumes"]["Vref_cm3"] = float(self.vref.value())
        self.cal["volumes"]["Vcell_cm3"] = float(self.vcell.value())
        self.cal["volumes"]["Vu_cm3"] = float(self.vu.value())
        self.cal["volumes"]["Vd_cm3"] = float(self.vd.value())
        save_calibration(self.calibration_path, self.cal)
        self.refresh_metadata_label()
        QMessageBox.information(self, "Volumes", "Volumes salvos em calibration.json")

    def check_stability(self):
        # Checagem rápida: pega algumas amostras rápidas no tempo (RAW)
        # (Sem histórico aqui — é um check instantâneo)
        values = []
        for name in self.channel_names:
            raw = self.get_raw_by_name(name)
            if raw is not None:
                values.append((name, float(raw)))

        if not values:
            QMessageBox.warning(self, "Validação", "Sem leituras RAW no momento.")
            return

        msg = "Leituras RAW atuais (bar):\n\n" + "\n".join([f"{n}: {v:.5f}" for n, v in values])
        QMessageBox.information(self, "Validação - RAW", msg)
