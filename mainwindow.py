from __future__ import annotations

import math
import os
import re
import sys
import time
import copy
from collections import deque
from typing import Any, Dict, List, Optional

import numpy as np
import pyqtgraph as pg
from PyQt5 import uic
from PyQt5.QtCore import QDate, QTime, QTimer, pyqtSignal
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QAction, QMainWindow, QMessageBox

from calc import differential_pressures, permeability_darcy
from operation_state import OperationState
from config import save_config
from units import pressure_from_pa, pressure_to_pa


def resource_path(relative_path: str) -> str:
    base = getattr(sys, "_MEIPASS", os.path.abspath("."))
    return os.path.join(base, relative_path)


class TelaPrincipal(QMainWindow):
    """Janela principal; workers e persistencia permanecem fora da UI."""

    start_requested = pyqtSignal()
    stop_requested = pyqtSignal()
    start_session_requested = pyqtSignal()
    stop_session_requested = pyqtSignal()

    def __init__(
        self,
        channel_names: List[str],
        channel_configs: Optional[List[Dict[str, Any]]] = None,
        calculation_config: Optional[Dict[str, Any]] = None,
        calibration_path: str = "calibration.json",
        config_path: str = "config.json",
        config_data: Optional[Dict[str, Any]] = None,
        username: str = "",
        user_role: str = "operator",
    ):
        super().__init__()
        uic.loadUi(resource_path("mainwindow.ui"), self)
        self.setWindowTitle("Sistema Coreflooding - Supervisorio")
        logo_path = resource_path("Imagens/logo_ism_transp.png")
        if os.path.exists(logo_path):
            self.setWindowIcon(QIcon(logo_path))
        self.Paginas.setCurrentIndex(0)

        self.channel_names = list(channel_names)
        self.channel_configs = list(channel_configs or [])
        self.channel_units = {
            item.get("name"): item.get("unit", "bar")
            for item in self.channel_configs if item.get("name")
        }
        for name in self.channel_names:
            self.channel_units.setdefault(name, "bar")
        self.calculation_config = dict(calculation_config or {})
        permeability_config = self.calculation_config.get("permeability", self.calculation_config)
        self.upstream_channel = permeability_config.get("upstream_channel")
        self.downstream_channel = permeability_config.get("downstream_channel")
        self.differential_channel = permeability_config.get("differential_channel") or (
            "DP" if "DP" in self.channel_names else None
        )
        self.fluid_model = permeability_config.get("fluid_model", "incompressible_liquid")
        self.data_stale_after_s = float(self.calculation_config.get("data_stale_after_s", 2.0))
        self.calibration_path = calibration_path
        self.config_path = config_path
        self.config_data = config_data or {}
        self.username = username
        self.user_role = user_role
        self.simulation_mode = False
        self.operation_state = OperationState.STOPPED
        self.session_active = False
        self.session_path: Optional[str] = None

        self.channel_widgets = {
            "P1": self.P1, "P2": self.P2, "P3": self.P3, "P4": self.P4, "DP": self.DP,
        }
        self.value_labels = [self.channel_widgets.get(name) for name in self.channel_names]
        self.latest_eng_corr: Dict[str, Optional[float]] = {}
        self.latest_eng_raw: Dict[str, Optional[float]] = {}
        self.channel_status: Dict[str, str] = {}
        self.latest_ts_ms: Optional[int] = None
        self.session_plot_start_ms: Optional[int] = None

        self.current_dp_measured_pa: Optional[float] = None
        self.current_dp_calculated_pa: Optional[float] = None
        self.current_dp_display_unit = self.channel_units.get(self.differential_channel or "DP", "bar")
        self.current_pump_flow_m3s: Optional[float] = None
        self.current_pump_raw = "-"
        self.current_pump_status = "DISCONNECTED"
        self.current_pump_message = "Bomba desconectada"
        self.current_pump_ts_ms: Optional[int] = None
        self.current_oven_temp_c: Optional[float] = None
        self.current_oven_raw = "-"
        self.current_oven_status = "DISCONNECTED"
        self.current_oven_message = "Estufa desconectada"
        self.current_oven_ts_ms: Optional[int] = None

        self._params_dialog = None
        self.last_porosity_percent: Optional[float] = None
        self.last_permeability_mD: Optional[float] = None
        self._initialize_parameter_widgets()

        plot_cfg = self.config_data.get("plot", {}) if isinstance(self.config_data, dict) else {}
        self.max_history_s = float(plot_cfg.get("max_history_s", 3600.0))
        rate = float(self.config_data.get("sample_rate_hz", 10.0)) if self.config_data else 10.0
        self.max_points = max(100, int(self.max_history_s * rate))
        self.t = deque(maxlen=self.max_points)
        self.y = {name: deque(maxlen=self.max_points) for name in self.channel_names}
        self.dp_measured = deque(maxlen=self.max_points)
        self.dp_calculated = deque(maxlen=self.max_points)
        self.k_t = deque(maxlen=self.max_points)
        self.k_y = deque(maxlen=self.max_points)
        self.temp_t = deque(maxlen=self.max_points)
        self.temp_y = deque(maxlen=self.max_points)

        self._setup_menus()
        self._setup_plots()
        self.timer_relogio = QTimer(self)
        self.timer_relogio.timeout.connect(self.atualizar_data_hora)
        self.timer_relogio.start(1000)
        self.timer_device_age = QTimer(self)
        self.timer_device_age.timeout.connect(self._refresh_device_labels)
        self.timer_device_age.start(500)
        self.atualizar_data_hora()

        self.btn_operacao.clicked.connect(self.ir_para_operacao)
        self.btn_graficos.clicked.connect(self.ir_para_graficos)
        self.btn_start.clicked.connect(self.start_requested.emit)
        self.btn_stop.clicked.connect(self.stop_requested.emit)
        self.pushButton_calcularporosidade_2.clicked.connect(self._toggle_session)
        self.tempo_analise.currentTextChanged.connect(self._refresh_all_plots)
        self.set_operation_state(OperationState.STOPPED)

    def _setup_menus(self):
        menu = self.menuBar().addMenu("Operacao")
        self.action_calibration = QAction("Calibracao de sensores", self)
        self.action_parameters = QAction("Parametros do ensaio", self)
        self.action_serial = QAction("Comunicacao serial", self)
        menu.addAction(self.action_calibration)
        menu.addAction(self.action_parameters)
        menu.addAction(self.action_serial)
        self.action_calibration.triggered.connect(self.open_calibration)
        self.action_parameters.triggered.connect(self.open_parameters)
        self.action_serial.triggered.connect(self.open_serial_settings)

    def _setup_plots(self):
        colors = ["b", "r", "g", "m", "c", "y"]
        for text in ("5min", "15min", "1h", "Ensaio completo"):
            if self.tempo_analise.findText(text) < 0:
                self.tempo_analise.addItem(text)
        self.widget_plot_pressao.setBackground("w")
        self.widget_plot_pressao.showGrid(x=True, y=True, alpha=0.3)
        self.widget_plot_pressao.setLabel("left", "Pressao")
        self.widget_plot_pressao.setLabel("bottom", "Tempo decorrido", units="s")
        self.widget_plot_pressao.addLegend(offset=(10, 10))
        self.pressure_curves = {}
        color_index = 0
        for name in self.channel_names:
            if name == self.differential_channel:
                continue
            self.pressure_curves[name] = self.widget_plot_pressao.plot(
                [], [], pen=pg.mkPen(color=colors[color_index % len(colors)], width=2), name=name
            )
            color_index += 1
        self.curves = list(self.pressure_curves.values())

        self.widget_plot_pressao_dp.setBackground("w")
        self.widget_plot_pressao_dp.showGrid(x=True, y=True, alpha=0.3)
        self.widget_plot_pressao_dp.setLabel("left", "Pressao diferencial", units=self.current_dp_display_unit)
        self.widget_plot_pressao_dp.setLabel("bottom", "Tempo decorrido", units="s")
        self.widget_plot_pressao_dp.addLegend(offset=(10, 10))
        self.curva_dp_measured = self.widget_plot_pressao_dp.plot([], [], pen=pg.mkPen("k", width=2), name="DP medido")
        self.curva_dp_calculated = self.widget_plot_pressao_dp.plot([], [], pen=pg.mkPen("r", width=2), name="DP calculado")

        self.widget_plot_temp.setBackground("w")
        self.widget_plot_temp.showGrid(x=True, y=True, alpha=0.3)
        self.widget_plot_temp.setLabel("left", "Temperatura", units="C")
        self.widget_plot_temp.setLabel("bottom", "Tempo decorrido", units="s")
        self.curva_temp = self.widget_plot_temp.plot([], [], pen=pg.mkPen("k", width=2), name="Temperatura")

        self.widget_plot_k.setBackground("w")
        self.widget_plot_k.showGrid(x=True, y=True, alpha=0.3)
        self.widget_plot_k.setLabel("left", "Permeabilidade", units="mD")
        self.widget_plot_k.setLabel("bottom", "Tempo decorrido", units="s")
        self.curva_k = self.widget_plot_k.plot([], [], pen=pg.mkPen("k", width=2), name="Permeabilidade")

    def atualizar_data_hora(self):
        self.lbl_data.setText(QDate.currentDate().toString("dd/MM/yyyy"))
        self.lbl_hora.setText(QTime.currentTime().toString("HH:mm:ss"))

    def ir_para_operacao(self):
        self.Paginas.setCurrentIndex(0)

    def ir_para_graficos(self):
        self.Paginas.setCurrentIndex(1)

    def set_operation_state(self, state: str | OperationState):
        previous = self.operation_state
        self.operation_state = OperationState(state)
        if self.operation_state == OperationState.RUNNING and previous != OperationState.RUNNING:
            self.clear_history()
        self.btn_start.setEnabled(self.operation_state in (OperationState.STOPPED, OperationState.ERROR))
        self.btn_stop.setEnabled(self.operation_state in (
            OperationState.STARTING, OperationState.RUNNING, OperationState.STOPPING, OperationState.ERROR
        ))
        labels = {
            OperationState.STOPPED: "Parado", OperationState.STARTING: "Iniciando...",
            OperationState.RUNNING: "Rodando", OperationState.STOPPING: "Parando...",
            OperationState.ERROR: "Erro - recuperacao necessaria",
        }
        prefix = "SIMULACAO - " if self.simulation_mode else ""
        self.lbl_conn.setText(prefix + "Status: " + labels[self.operation_state])
        color = {OperationState.RUNNING: "#0F0", OperationState.ERROR: "#F90"}.get(self.operation_state, "black")
        text_color = "#000" if self.operation_state in (OperationState.RUNNING, OperationState.ERROR) else "white"
        self.lbl_conn.setStyleSheet(f"color: {text_color}; font-weight: bold; background-color: {color}; padding: 2px;")

    def set_running(self, running: bool):
        self.set_operation_state(OperationState.RUNNING if running else OperationState.STOPPED)

    def iniciar_daq(self):
        self.start_requested.emit()

    def parar_daq(self):
        self.stop_requested.emit()

    def set_simulation_mode(self, enabled: bool):
        self.simulation_mode = bool(enabled)
        suffix = " [MODO SIMULACAO]" if self.simulation_mode else ""
        self.setWindowTitle("Sistema Coreflooding - Supervisorio" + suffix)
        self.set_operation_state(OperationState.STOPPED)

    def show_error(self, message: str):
        self._invalidate_current_data()
        self.statusbar.showMessage(str(message), 10000)
        QMessageBox.critical(self, "Erro", str(message))

    def _invalidate_current_data(self):
        """Clear current readings after a source failure; history remains intact."""
        self.latest_ts_ms = None
        for name in self.channel_names:
            self.latest_eng_raw[name] = None
            self.latest_eng_corr[name] = None
            self.channel_status[name] = "INVALID"
            widget = self.channel_widgets.get(name)
            if widget is not None:
                widget.setText("OFFLINE")
        self.current_dp_measured_pa = None
        self.current_dp_calculated_pa = None
        self.dpcalc.setText("--")
        self.DP.setText("OFFLINE")
        self.lbl_pmean.setText("--")
        self.lbl_sigma_eff.setText("--")

    def show_event(self, event):
        self.statusbar.showMessage(f"[{event.severity}] {event.source}: {event.message}", 15000)

    def _is_admin(self) -> bool:
        if self.user_role == "admin":
            return True
        QMessageBox.warning(self, "Permissao", "Esta operacao exige perfil administrador.")
        return False

    def open_calibration(self):
        if not self._is_admin():
            return
        if self.operation_state != OperationState.STOPPED:
            QMessageBox.warning(self, "Aquisicao ativa", "Pare a aquisicao antes de alterar a calibracao.")
            return
        from calibration_dialog import CalibrationDialog
        parameters = self.parameter_snapshot()
        dialog = CalibrationDialog(
            self,
            self.channel_names,
            self.get_raw_by_name,
            self.get_corr_by_name,
            self.calibration_path,
            initial_volumes=parameters,
            on_volumes_saved=lambda values: self.apply_parameters(values),
        )
        dialog.exec_()

    def open_parameters(self):
        if not self._is_admin():
            return
        if self.operation_state != OperationState.STOPPED:
            QMessageBox.warning(self, "Aquisicao ativa", "Pare a aquisicao antes de alterar os parametros.")
            return
        from params_dialog import ParamsDialog
        dialog = ParamsDialog(
            self, self.get_pressure_bar_by_name, self._apply_calculation_results,
            self.upstream_channel or "", self.downstream_channel or "", self.parameter_snapshot()
        )
        self._params_dialog = dialog
        if dialog.exec_() == dialog.Accepted:
            try:
                self.apply_parameters(dialog.values())
            except (ValueError, OSError) as exc:
                QMessageBox.critical(self, "Parametros", str(exc))
        self._params_dialog = None

    def open_serial_settings(self):
        if not self._is_admin():
            return
        from serial_settings_dialog import SerialSettingsDialog
        callback = getattr(self, "serial_settings_callback", None)
        dialog = SerialSettingsDialog(self, self.config_data, lambda: bool(callback and callback("check")))
        if dialog.exec_() == dialog.Accepted and callback:
            callback(dialog.values())

    def set_serial_settings_callback(self, callback):
        self.serial_settings_callback = callback

    def parameter_snapshot(self) -> Dict[str, Any]:
        try:
            viscosity = float(self.input_mu.value())
        except (AttributeError, TypeError, ValueError):
            viscosity = 0.0
        return {
            "diameter_m": float(self.input_d.value()), "length_m": float(self.input_L.value()),
            "viscosity_pa_s": viscosity, "flow_m3s_manual": float(self.input_q.value()),
            "temperature_c_manual": float(self.input_temp_manual.value()),
            "vref_cm3": float(self.config_data.get("parameters", {}).get("vref_cm3", 10.0)),
            "vcell_cm3": float(self.config_data.get("parameters", {}).get("vcell_cm3", 20.0)),
            "vu_cm3": float(self.config_data.get("parameters", {}).get("vu_cm3", 10.0)),
            "vd_cm3": float(self.config_data.get("parameters", {}).get("vd_cm3", 10.0)),
            "upstream_channel": self.upstream_channel, "downstream_channel": self.downstream_channel,
            "differential_channel": self.differential_channel, "fluid_model": self.fluid_model,
            "test_model": self.fluid_model,
        }

    def apply_parameters(self, values: Dict[str, Any]):
        # Primeiro monta e valida um candidato. Assim uma configuracao
        # invalida nao deixa a UI parcialmente atualizada.
        updated = copy.deepcopy(self.config_data)
        parameters = updated.setdefault("parameters", {})
        for key in (
            "diameter_m", "length_m", "viscosity_pa_s", "flow_m3s_manual",
            "temperature_c_manual", "vref_cm3", "vcell_cm3", "vu_cm3", "vd_cm3",
        ):
            if key in values:
                parameters[key] = float(values[key])
        candidate_upstream = values.get("upstream_channel", self.upstream_channel)
        candidate_downstream = values.get("downstream_channel", self.downstream_channel)
        candidate_model = str(values.get("test_model", self.fluid_model))
        parameters["test_model"] = candidate_model
        permeability = updated.setdefault("calculations", {}).setdefault("permeability", {})
        permeability["upstream_channel"] = candidate_upstream
        permeability["downstream_channel"] = candidate_downstream
        permeability["differential_channel"] = self.differential_channel
        permeability["fluid_model"] = candidate_model
        save_config(self.config_path, updated)

        for key, widget in (("diameter_m", self.input_d), ("length_m", self.input_L),
                            ("flow_m3s_manual", self.input_q), ("temperature_c_manual", self.input_temp_manual)):
            if key in values:
                widget.setValue(float(values[key]))
        if "viscosity_pa_s" in values:
            self.input_mu.setValue(float(values["viscosity_pa_s"]))
        self.upstream_channel = candidate_upstream
        self.downstream_channel = candidate_downstream
        self.fluid_model = candidate_model
        self.config_data.clear()
        self.config_data.update(updated)
        self.calculation_config = copy.deepcopy(updated.get("calculations", {}))

    def _initialize_parameter_widgets(self):
        parameters = self.config_data.get("parameters", {}) if isinstance(self.config_data, dict) else {}
        defaults = {
            "diameter_m": 0.0254, "length_m": 0.05, "viscosity_pa_s": 0.001,
            "flow_m3s_manual": 0.0, "temperature_c_manual": 25.0,
        }
        defaults.update({key: value for key, value in parameters.items() if key in defaults})
        for key, widget in (
            ("diameter_m", self.input_d), ("length_m", self.input_L),
            ("viscosity_pa_s", self.input_mu), ("flow_m3s_manual", self.input_q),
            ("temperature_c_manual", self.input_temp_manual),
        ):
            try:
                widget.setValue(float(defaults[key]))
            except (TypeError, ValueError):
                pass

    def _apply_calculation_results(self, **results):
        if results.get("phi_percent") is not None:
            self.last_porosity_percent = float(results["phi_percent"])
        if results.get("k_mD") is not None:
            self.last_permeability_mD = float(results["k_mD"])

    def _toggle_session(self):
        (self.stop_session_requested if self.session_active else self.start_session_requested).emit()

    def set_session_active(self, active: bool, path: Optional[str] = None):
        self.session_active = bool(active)
        self.session_path = path
        self.pushButton_calcularporosidade_2.setText("Encerrar Ensaio" if active else "Iniciar Experimento")
        self.checkBox.setEnabled(not active)

    def update_pump_flow(self, value_m3s: float):
        try:
            value_m3s = float(value_m3s)
        except (TypeError, ValueError):
            return
        if math.isfinite(value_m3s) and value_m3s >= 0:
            self.current_pump_flow_m3s = value_m3s
            self.current_pump_ts_ms = int(time.time() * 1000)
            if self.flow_source.currentIndex() == 1:
                self.input_q.setValue(value_m3s)

    def update_pump_raw(self, text: str):
        self.current_pump_raw = str(text); self._refresh_device_labels()

    def update_pump_status(self, text: str):
        self.current_pump_message = str(text); self._refresh_device_labels()

    def update_pump_state(self, text: str):
        self.current_pump_status = str(text); self._refresh_device_labels()

    def update_pump_error(self, text: str):
        self.current_pump_status = "ERROR"; self.current_pump_message = str(text)
        self.current_pump_raw = str(text); self._refresh_device_labels()

    def update_oven_temp(self, value_c: float):
        try:
            value_c = float(value_c)
        except (TypeError, ValueError):
            return
        if math.isfinite(value_c):
            self.current_oven_temp_c = value_c
            self.current_oven_ts_ms = int(time.time() * 1000)
            if self.temp_source.currentIndex() == 1:
                self.lbl_temp.setText(f"{value_c:.2f} C")

    def update_oven_raw(self, text: str):
        self.current_oven_raw = str(text); self._refresh_device_labels()

    def update_oven_status(self, text: str):
        self.current_oven_message = str(text); self._refresh_device_labels()

    def update_oven_state(self, text: str):
        self.current_oven_status = str(text); self._refresh_device_labels()

    def update_oven_error(self, text: str):
        self.current_oven_status = "ERROR"; self.current_oven_message = str(text)
        self.current_oven_raw = str(text); self._refresh_device_labels()

    def _age_text(self, timestamp_ms: Optional[int]) -> str:
        if timestamp_ms is None:
            return "nunca"
        return f"ha {max(0.0, time.time() - timestamp_ms / 1000.0):.1f}s"

    def _refresh_device_labels(self):
        self.lbl_pump_status.setText(f"Estado: {self.current_pump_status}\n{self.current_pump_message}\nUltima leitura: {self._age_text(self.current_pump_ts_ms)}")
        self.lbl_pump_raw.setText(f"Ultima mensagem: {self.current_pump_raw}")
        self.lbl_oven_status.setText(f"Estado: {self.current_oven_status}\n{self.current_oven_message}\nUltima leitura: {self._age_text(self.current_oven_ts_ms)}")
        self.llbl_oven_raw.setText(f"Ultima mensagem: {self.current_oven_raw}")

    def _is_fresh(self, timestamp_ms: Optional[int]) -> bool:
        return timestamp_ms is not None and (time.time() * 1000 - timestamp_ms) <= self.data_stale_after_s * 1000

    def get_current_temperature(self):
        if self.temp_source.currentIndex() == 0:
            return float(self.input_temp_manual.value())
        return self.current_oven_temp_c if self._is_fresh(self.current_oven_ts_ms) else None

    def get_current_flow(self):
        if self.flow_source.currentIndex() == 0:
            return float(self.input_q.value())
        return self.current_pump_flow_m3s if self._is_fresh(self.current_pump_ts_ms) else None

    def _set_k_unavailable(self):
        self.lbl_k.setText("-- mD")

    def _selected_dp_pa(self) -> Optional[float]:
        return self.current_dp_measured_pa if self.dp_source.currentIndex() == 0 else self.current_dp_calculated_pa

    def calculate_permeability_realtime(self):
        try:
            if not self._is_fresh(self.latest_ts_ms):
                self._set_k_unavailable(); return None
            q = self.get_current_flow(); mu = float(self.input_mu.value())
            length_m = float(self.input_L.value()); diameter_m = float(self.input_d.value())
            dp_pa = self._selected_dp_pa()
            if dp_pa is None or q is None or not all(math.isfinite(float(x)) for x in (q, mu, length_m, diameter_m, dp_pa)):
                raise ValueError("Vazao, Delta P e parametros geometricos devem ser validos.")
            result = permeability_darcy(q, mu, length_m, diameter_m, dp_pa, self.fluid_model)
            if not math.isfinite(result["k_mD"]):
                raise ValueError("Permeabilidade calculada nao e finita.")
            self.lbl_k.setText(f"{result['k_mD']:.2f} mD")
            return result["k_mD"]
        except (KeyError, TypeError, ValueError):
            self._set_k_unavailable(); return None

    def _payload_channels(self, payload: dict) -> dict[str, dict[str, Any]]:
        channels = payload.get("channels")
        if isinstance(channels, dict):
            return channels
        raw = payload.get("eng_raw", []); corrected = payload.get("eng", []); statuses = payload.get("status", [])
        return {name: {"eng_raw": raw[i] if i < len(raw) else None,
                       "eng": corrected[i] if i < len(corrected) else None,
                       "status": statuses[i] if i < len(statuses) else "INVALID"}
                for i, name in enumerate(self.channel_names)}

    @staticmethod
    def _finite(value) -> Optional[float]:
        try:
            value = float(value)
        except (TypeError, ValueError):
            return None
        return value if math.isfinite(value) else None

    def _time_window_s(self) -> Optional[float]:
        text = self.tempo_analise.currentText().lower().strip()
        if "ensaio" in text or "completo" in text:
            return None
        text = text.replace(" ", "")
        text = text.replace("segundos", "s").replace("segundo", "s")
        text = text.replace("minutos", "min").replace("minuto", "min")
        text = text.replace("horas", "h").replace("hora", "h")
        match = re.match(r"([0-9]+(?:\.[0-9]+)?)(s|min|h)$", text)
        if match:
            return float(match.group(1)) * {"s": 1, "min": 60, "h": 3600}[match.group(2)]
        return None

    def _set_curve(self, curve, x_values, y_values):
        x = np.asarray(list(x_values), dtype=float); y = np.asarray(list(y_values), dtype=float)
        if not len(x):
            curve.setData([], []); return
        window = self._time_window_s()
        if window is not None:
            mask = x >= max(0.0, x[-1] - window); x, y = x[mask], y[mask]
        if len(x) > 2000:
            indexes = np.linspace(0, len(x) - 1, 2000).astype(int); x, y = x[indexes], y[indexes]
        curve.setData(x, y)

    def _refresh_all_plots(self):
        for name, curve in self.pressure_curves.items(): self._set_curve(curve, self.t, self.y[name])
        self._set_curve(self.curva_dp_measured, self.t, self.dp_measured)
        self._set_curve(self.curva_dp_calculated, self.t, self.dp_calculated)
        self._set_curve(self.curva_temp, self.temp_t, self.temp_y)
        self._set_curve(self.curva_k, self.k_t, self.k_y)

    def clear_history(self):
        self.session_plot_start_ms = None
        for values in (self.t, self.dp_measured, self.dp_calculated, self.k_t, self.k_y, self.temp_t, self.temp_y): values.clear()
        for values in self.y.values(): values.clear()
        self._refresh_all_plots()

    def update_data(self, payload):
        channels = self._payload_channels(payload)
        timestamp = payload.get("timestamp_ms")
        try:
            timestamp_float = float(timestamp)
            self.latest_ts_ms = int(timestamp_float) if math.isfinite(timestamp_float) else None
        except (TypeError, ValueError):
            self.latest_ts_ms = None
        if self.latest_ts_ms is None:
            # Workers always provide a source timestamp. Keep malformed
            # external payloads from crashing the UI, but do not pretend that
            # the fallback is an acquisition timestamp.
            self.latest_ts_ms = int(time.time() * 1000)
        if self.session_plot_start_ms is None: self.session_plot_start_ms = self.latest_ts_ms
        elapsed_s = max(0.0, (self.latest_ts_ms - self.session_plot_start_ms) / 1000.0)
        for name in self.channel_names:
            item = channels.get(name, {}); raw = self._finite(item.get("eng_raw")); corrected = self._finite(item.get("eng"))
            status = str(item.get("status", "INVALID"))
            self.latest_eng_raw[name] = raw; self.latest_eng_corr[name] = corrected if status == "OK" else None; self.channel_status[name] = status
        self.t.append(elapsed_s)
        for name, widget in zip(self.channel_names, self.value_labels):
            if widget is None: continue
            value = self.latest_eng_corr.get(name); status = self.channel_status.get(name, "INVALID")
            if value is None:
                widget.setText("OFFLINE"); widget.setObjectName("TagBad")
            else:
                widget.setText(f"{value:.2f} {self.channel_units.get(name, '')}".strip()); widget.setObjectName("TagOK" if status == "OK" else "TagWarn")
            widget.style().unpolish(widget); widget.style().polish(widget)

        unit = self.channel_units.get(self.upstream_channel or self.differential_channel or "DP", "bar")
        self.current_dp_display_unit = unit
        self.widget_plot_pressao_dp.setLabel("left", "Pressao diferencial", units=unit)
        upstream = self.latest_eng_corr.get(self.upstream_channel); downstream = self.latest_eng_corr.get(self.downstream_channel)
        measured = self.latest_eng_corr.get(self.differential_channel)
        measured_status = self.channel_status.get(self.differential_channel, "INVALID")
        dp_values = differential_pressures(
            measured, self.channel_units.get(self.differential_channel, unit),
            upstream, self.channel_units.get(self.upstream_channel, unit),
            downstream, self.channel_units.get(self.downstream_channel, unit),
            measured_status=measured_status,
            upstream_status=self.channel_status.get(self.upstream_channel, "INVALID"),
            downstream_status=self.channel_status.get(self.downstream_channel, "INVALID"),
        )
        self.current_dp_measured_pa = dp_values["measured_pa"]
        self.current_dp_calculated_pa = dp_values["calculated_pa"]
        if self.current_dp_calculated_pa is not None:
            upstream_pa = pressure_to_pa(upstream, self.channel_units.get(self.upstream_channel, unit))
            downstream_pa = pressure_to_pa(downstream, self.channel_units.get(self.downstream_channel, unit))
            dp_display = pressure_from_pa(self.current_dp_calculated_pa, unit)
            self.dpcalc.setText(f"{dp_display:.2f} {unit}")
            self.lbl_pmean.setText(f"{pressure_from_pa((upstream_pa + downstream_pa) / 2.0, unit):.2f} {unit}")
            self.lbl_sigma_eff.setText(f"{pressure_from_pa(self.current_dp_calculated_pa / 2.0, unit):.2f} {unit}")
        else:
            self.dpcalc.setText("--"); self.lbl_pmean.setText("--"); self.lbl_sigma_eff.setText("--")
        self.DP.setText(f"{measured:.2f} {self.channel_units.get(self.differential_channel, unit)}" if self.current_dp_measured_pa is not None else "OFFLINE")
        self.dp_measured.append(pressure_from_pa(self.current_dp_measured_pa, unit) if self.current_dp_measured_pa is not None else np.nan)
        self.dp_calculated.append(pressure_from_pa(self.current_dp_calculated_pa, unit) if self.current_dp_calculated_pa is not None else np.nan)

        temperature = self.get_current_temperature(); self.temp_t.append(elapsed_s); self.temp_y.append(temperature if temperature is not None else np.nan)
        if temperature is not None: self.lbl_temp.setText(f"{temperature:.2f} C")
        k_value = self.calculate_permeability_realtime(); self.k_t.append(elapsed_s); self.k_y.append(k_value if k_value is not None else np.nan)
        if self._params_dialog is not None:
            self._params_dialog.feed_decay_sample(self.latest_ts_ms)
        for name in self.pressure_curves:
            value = self.latest_eng_corr.get(name); self.y[name].append(value if value is not None else np.nan)
        self._refresh_all_plots()

    def derived_snapshot(self) -> Dict[str, Any]:
        return {
            "dp_measured": pressure_from_pa(self.current_dp_measured_pa, self.current_dp_display_unit) if self.current_dp_measured_pa is not None else None,
            "dp_calculated": pressure_from_pa(self.current_dp_calculated_pa, self.current_dp_display_unit) if self.current_dp_calculated_pa is not None else None,
            "dp_unit": self.current_dp_display_unit,
            "flow_m3s": self.get_current_flow(), "temperature_c": self.get_current_temperature(),
            "permeability_mD": float(self.k_y[-1]) if self.k_y and np.isfinite(self.k_y[-1]) else None,
        }

    def get_raw_by_name(self, name: str):
        if self.channel_status.get(name) != "OK" or not self._is_fresh(self.latest_ts_ms):
            return None
        value = self.latest_eng_raw.get(name)
        if value is None:
            return None
        unit = self.channel_units.get(name, "bar")
        return pressure_from_pa(pressure_to_pa(value, unit), "bar")

    def get_corr_by_name(self, name: str):
        if self.channel_status.get(name) != "OK" or not self._is_fresh(self.latest_ts_ms):
            return None
        value = self.latest_eng_corr.get(name)
        if value is None:
            return None
        unit = self.channel_units.get(name, "bar")
        return pressure_from_pa(pressure_to_pa(value, unit), "bar")

    def get_pressure_bar_by_name(self, name: str):
        """Return a current valid channel value in bar for scientific dialogs."""
        return self.get_corr_by_name(name)
