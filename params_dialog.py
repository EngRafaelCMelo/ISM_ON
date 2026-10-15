from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QTabWidget,
    QWidget, QLineEdit, QPushButton, QLabel, QMessageBox, QDoubleSpinBox, QComboBox
)
from PyQt5.QtCore import Qt

from calc import bulk_volume_cylinder, porosity_from_p1_p2, estimate_alpha_from_decay, permeability_pulse_decay
from units import pressure_to_pa
import numpy as np


def bar_to_pa(bar: float) -> float:
    return pressure_to_pa(bar, "bar")


class ParamsDialog(QDialog):
    """
    Dialog de parâmetros + ações:
    - Capturar P1/P2
    - Calcular porosidade
    - Iniciar/parar aquisição de decay e calcular permeabilidade (pulse-decay)
    """
    def __init__(
        self,
        parent,
        get_pressure_bar_by_name,
        set_results_callback,
        upstream_channel: str = "",
        downstream_channel: str = "",
        parameters=None,
    ):
        super().__init__(parent)

        self.get_pressure_bar_by_name = get_pressure_bar_by_name
        self.set_results_callback = set_results_callback
        self.initial_parameters = dict(parameters or {})

        self.setWindowTitle("Configurar Ensaio (Porosidade / Permeabilidade)")
        self.setModal(True)
        self.resize(640, 420)

        self.decay_running = False
        self.decay_t = []
        self.decay_pu = []
        self.decay_pd = []
        self.decay_t0_ms = None

        root = QVBoxLayout(self)
        tabs = QTabWidget()
        root.addWidget(tabs)

        # ===== TAB 1: Amostra =====
        tab_sample = QWidget()
        tabs.addTab(tab_sample, "Amostra")
        f1 = QFormLayout(tab_sample)

        self.sample_id = QLineEdit("Amostra-001")

        self.flow_m3s_manual = QDoubleSpinBox()
        self.flow_m3s_manual.setRange(0.0, 1e6)
        self.flow_m3s_manual.setDecimals(9)
        self.temperature_c_manual = QDoubleSpinBox()
        self.temperature_c_manual.setRange(-273.15, 1000.0)
        self.temperature_c_manual.setDecimals(3)
        # A single temperature field is shared by manual operation and the
        # scientific parameter snapshot; keep the legacy attribute as an alias.
        self.temp_c = self.temperature_c_manual
        self.test_model = QComboBox()
        self.test_model.addItem("Liquido incompressivel (Darcy)", "incompressible_liquid")
        self.test_model.addItem("Gas / pulse-decay", "gas_pulse_decay")

        self.d_mm = QDoubleSpinBox()
        self.d_mm.setRange(0.1, 500.0)
        self.d_mm.setValue(25.4)
        self.d_mm.setDecimals(3)

        self.L_mm = QDoubleSpinBox()
        self.L_mm.setRange(0.1, 1000.0)
        self.L_mm.setValue(50.0)
        self.L_mm.setDecimals(3)

        f1.addRow("ID da amostra:", self.sample_id)
        f1.addRow("Diâmetro (mm):", self.d_mm)
        f1.addRow("Comprimento (mm):", self.L_mm)
        f1.addRow("Vazão manual (m³/s):", self.flow_m3s_manual)
        f1.addRow("Temperatura manual (°C):", self.temperature_c_manual)
        f1.addRow("Modelo do ensaio:", self.test_model)

        # ===== TAB 2: Porosidade =====
        tab_por = QWidget()
        tabs.addTab(tab_por, "Porosidade")
        f2 = QFormLayout(tab_por)

        self.vref_cm3 = QDoubleSpinBox()
        self.vref_cm3.setRange(0.001, 1e9)
        self.vref_cm3.setValue(10.0)
        self.vref_cm3.setDecimals(3)

        self.vcell_cm3 = QDoubleSpinBox()
        self.vcell_cm3.setRange(0.001, 1e9)
        self.vcell_cm3.setValue(20.0)
        self.vcell_cm3.setDecimals(3)

        self.p1_bar = QDoubleSpinBox()
        self.p1_bar.setRange(0.0, 20000.0)
        self.p1_bar.setDecimals(4)

        self.p2_bar = QDoubleSpinBox()
        self.p2_bar.setRange(0.0, 20000.0)
        self.p2_bar.setDecimals(4)

        btn_row = QHBoxLayout()
        self.btn_cap_p1 = QPushButton("Capturar P1")
        self.btn_cap_p2 = QPushButton("Capturar P2")
        self.btn_calc_phi = QPushButton("Calcular Porosidade")
        btn_row.addWidget(self.btn_cap_p1)
        btn_row.addWidget(self.btn_cap_p2)
        btn_row.addStretch(1)
        btn_row.addWidget(self.btn_calc_phi)

        self.lbl_phi = QLabel("Porosidade: -- %")
        self.lbl_phi.setAlignment(Qt.AlignLeft)
        self.lbl_phi.setStyleSheet("font-weight: 800; font-size: 14px;")

        f2.addRow("Vref (cm³):", self.vref_cm3)
        f2.addRow("Vcell vazio (cm³):", self.vcell_cm3)
        f2.addRow("P1 (bar):", self.p1_bar)
        f2.addRow("P2 (bar):", self.p2_bar)
        f2.addRow(btn_row)
        f2.addRow(self.lbl_phi)

        # ===== TAB 3: Permeabilidade (Pulse-Decay) =====
        tab_perm = QWidget()
        tabs.addTab(tab_perm, "Permeabilidade (Decay)")
        f3 = QFormLayout(tab_perm)

        # viscosidade N2 aproximada a ~25C
        self.mu = QLineEdit("1.78e-5")  # Pa.s

        self.vu_cm3 = QDoubleSpinBox()
        self.vu_cm3.setRange(0.001, 1e9)
        self.vu_cm3.setValue(10.0)
        self.vu_cm3.setDecimals(3)

        self.vd_cm3 = QDoubleSpinBox()
        self.vd_cm3.setRange(0.001, 1e9)
        self.vd_cm3.setValue(10.0)
        self.vd_cm3.setDecimals(3)

        # mapeamento de canais (assumindo nomes do teu config)
        self.up_name = QLineEdit(upstream_channel)
        self.down_name = QLineEdit(downstream_channel)

        self.btn_decay_start = QPushButton("Iniciar Decay (capturar curva)")
        self.btn_decay_stop = QPushButton("Parar Decay e Calcular k")
        self.btn_decay_stop.setEnabled(False)

        btn_row2 = QHBoxLayout()
        btn_row2.addWidget(self.btn_decay_start)
        btn_row2.addWidget(self.btn_decay_stop)

        self.lbl_k = QLabel("Permeabilidade: -- mD")
        self.lbl_k.setAlignment(Qt.AlignLeft)
        self.lbl_k.setStyleSheet("font-weight: 800; font-size: 14px;")

        f3.addRow("μ N₂ (Pa·s):", self.mu)
        f3.addRow("Vu (cm³):", self.vu_cm3)
        f3.addRow("Vd (cm³):", self.vd_cm3)
        f3.addRow("Canal upstream (Pu):", self.up_name)
        f3.addRow("Canal downstream (Pd):", self.down_name)
        f3.addRow(btn_row2)
        f3.addRow(self.lbl_k)

        # Footer
        footer = QHBoxLayout()
        self.btn_close = QPushButton("Fechar")
        footer.addStretch(1)
        footer.addWidget(self.btn_close)
        root.addLayout(footer)

        # Signals
        self.btn_close.clicked.connect(self.accept)
        self.btn_cap_p1.clicked.connect(self.capture_p1)
        self.btn_cap_p2.clicked.connect(self.capture_p2)
        self.btn_calc_phi.clicked.connect(self.calc_porosity)
        self.btn_decay_start.clicked.connect(self.start_decay)
        self.btn_decay_stop.clicked.connect(self.stop_decay_and_calc)
        self.set_parameters(self.initial_parameters)

    # ===== Util =====
    def _cm3_to_m3(self, cm3: float) -> float:
        return cm3 * 1e-6

    def _mm_to_m(self, mm: float) -> float:
        return mm / 1000.0

    def set_parameters(self, values):
        values = values or {}
        if "sample_id" in values:
            self.sample_id.setText(str(values["sample_id"]))
        if "diameter_m" in values:
            self.d_mm.setValue(float(values["diameter_m"]) * 1000.0)
        if "length_m" in values:
            self.L_mm.setValue(float(values["length_m"]) * 1000.0)
        for key, widget in (
            ("vref_cm3", self.vref_cm3), ("vcell_cm3", self.vcell_cm3),
            ("vu_cm3", self.vu_cm3), ("vd_cm3", self.vd_cm3), ("temperature_c", self.temp_c),
        ):
            if key in values:
                widget.setValue(float(values[key]))
        if "viscosity_pa_s" in values:
            self.mu.setText(str(values["viscosity_pa_s"]))
        if "flow_m3s_manual" in values:
            self.flow_m3s_manual.setValue(float(values["flow_m3s_manual"]))
        if "temperature_c_manual" in values:
            self.temperature_c_manual.setValue(float(values["temperature_c_manual"]))
        if "test_model" in values:
            index = self.test_model.findData(values["test_model"])
            if index >= 0:
                self.test_model.setCurrentIndex(index)
        if "upstream_channel" in values:
            self.up_name.setText(str(values["upstream_channel"]))
        if "downstream_channel" in values:
            self.down_name.setText(str(values["downstream_channel"]))

    def values(self):
        try:
            viscosity = float(self.mu.text().strip())
        except ValueError as exc:
            raise ValueError("Viscosidade invalida.") from exc
        return {
            "sample_id": self.sample_id.text().strip(),
            "diameter_m": self._mm_to_m(self.d_mm.value()),
            "length_m": self._mm_to_m(self.L_mm.value()),
            "vref_cm3": self.vref_cm3.value(),
            "vcell_cm3": self.vcell_cm3.value(),
            "vu_cm3": self.vu_cm3.value(),
            "vd_cm3": self.vd_cm3.value(),
            "temperature_c": self.temp_c.value(),
            "temperature_c_manual": self.temperature_c_manual.value(),
            "flow_m3s_manual": self.flow_m3s_manual.value(),
            "viscosity_pa_s": viscosity,
            "upstream_channel": self.up_name.text().strip(),
            "downstream_channel": self.down_name.text().strip(),
            "test_model": self.test_model.currentData(),
        }

    # ===== Porosidade =====
    def capture_p1(self):
        try:
            p = self.get_pressure_bar_by_name("P1")
            if p is None:
                raise ValueError("Sem dado de P1 ainda.")
            self.p1_bar.setValue(float(p))
        except Exception as e:
            QMessageBox.warning(self, "Aviso", f"Falha ao capturar P1: {e}")

    def capture_p2(self):
        try:
            p = self.get_pressure_bar_by_name("P2")
            if p is None:
                raise ValueError("Sem dado de P2 ainda.")
            self.p2_bar.setValue(float(p))
        except Exception as e:
            QMessageBox.warning(self, "Aviso", f"Falha ao capturar P2: {e}")

    def calc_porosity(self):
        try:
            d = self._mm_to_m(self.d_mm.value())
            L = self._mm_to_m(self.L_mm.value())
            vbulk = bulk_volume_cylinder(d, L)

            vref = self._cm3_to_m3(self.vref_cm3.value())
            vcell = self._cm3_to_m3(self.vcell_cm3.value())

            p1 = bar_to_pa(self.p1_bar.value())
            p2 = bar_to_pa(self.p2_bar.value())

            out = porosity_from_p1_p2(p1, p2, vref, vcell, vbulk)
            self.lbl_phi.setText(f"Porosidade: {out['phi_percent']:.2f} %")

            # envia resultado para a tela principal
            self.set_results_callback(phi_percent=out["phi_percent"], k_mD=None)

        except Exception as e:
            QMessageBox.critical(self, "Erro", f"Falha ao calcular porosidade:\n{e}")

    # ===== Decay / Permeabilidade =====
    def start_decay(self):
        self.decay_running = True
        self.decay_t = []
        self.decay_pu = []
        self.decay_pd = []
        self.decay_t0_ms = None

        self.btn_decay_start.setEnabled(False)
        self.btn_decay_stop.setEnabled(True)
        QMessageBox.information(self, "Decay", "Captura iniciada.\nDeixe o sistema decair e depois clique em 'Parar'.")

    def feed_decay_sample(self, t_ms: int):
        """
        Chame isso de fora a cada amostra do DAQ quando decay_running=True.
        """
        if not self.decay_running:
            return

        up = self.up_name.text().strip()
        down = self.down_name.text().strip()
        if not up or not down:
            return

        pu = self.get_pressure_bar_by_name(up)
        pd = self.get_pressure_bar_by_name(down)
        if pu is None or pd is None:
            return

        if self.decay_t0_ms is None:
            self.decay_t0_ms = t_ms

        t_s = (t_ms - self.decay_t0_ms) / 1000.0
        self.decay_t.append(t_s)
        self.decay_pu.append(bar_to_pa(float(pu)))
        self.decay_pd.append(bar_to_pa(float(pd)))

    def stop_decay_and_calc(self):
        try:
            self.decay_running = False
            self.btn_decay_start.setEnabled(True)
            self.btn_decay_stop.setEnabled(False)

            if len(self.decay_t) < 30:
                raise ValueError("Poucos pontos coletados para o decay (tente coletar por mais tempo).")

            t = np.array(self.decay_t, dtype=float)
            pu = np.array(self.decay_pu, dtype=float)
            pd = np.array(self.decay_pd, dtype=float)
            dP = np.abs(pu - pd)

            alpha = estimate_alpha_from_decay(t, dP)

            mu = float(self.mu.text().strip())
            d = self._mm_to_m(self.d_mm.value())
            L = self._mm_to_m(self.L_mm.value())
            A = 3.141592653589793 * (d / 2.0) ** 2

            Vu = self._cm3_to_m3(self.vu_cm3.value())
            Vd = self._cm3_to_m3(self.vd_cm3.value())

            Pm = float(np.mean((pu + pd) / 2.0))
            out = permeability_pulse_decay(alpha, mu, L, A, Pm, Vu, Vd)

            self.lbl_k.setText(f"Permeabilidade: {out['k_mD']:.2f} mD")
            self.set_results_callback(phi_percent=None, k_mD=out["k_mD"])

        except Exception as e:
            QMessageBox.critical(self, "Erro", f"Falha ao calcular permeabilidade (decay):\n{e}")
