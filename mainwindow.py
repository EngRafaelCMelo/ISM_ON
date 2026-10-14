from __future__ import annotations

import math
import os
import sys
import time
from collections import deque
from datetime import datetime
from typing import Any, Dict, List, Optional

import numpy as np
import pyqtgraph as pg
from PyQt5 import uic
from PyQt5.QtCore import QDate, QTime, QTimer
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QMainWindow, QMessageBox

from calc import permeability_darcy
from units import pressure_from_pa, pressure_to_pa


def resource_path(relative_path: str) -> str:
    base = getattr(sys, "_MEIPASS", os.path.abspath("."))
    return os.path.join(base, relative_path)


class TelaPrincipal(QMainWindow):
    """Janela principal; hardware e calculos permanecem fora da UI."""

    def __init__(
        self,
        channel_names: List[str],
        channel_configs: Optional[List[Dict[str, Any]]] = None,
        calculation_config: Optional[Dict[str, Any]] = None,
    ):
        super().__init__()
        uic.loadUi(resource_path("mainwindow.ui"), self)
        self.setWindowTitle("Sistema Coreflooding - Supervisorio")
        logo_path = resource_path("Imagens/logo_ism_transp.png")
        if os.path.exists(logo_path):
            self.setWindowIcon(QIcon(logo_path))
        self.Paginas.setCurrentIndex(0)

        self.channel_names = list(channel_names)
        channel_configs = channel_configs or []
        self.channel_units = {
            item.get("name"): item.get("unit", "bar")
            for item in channel_configs
            if item.get("name")
        }
        for name in self.channel_names:
            self.channel_units.setdefault(name, "bar")

        calculation_config = calculation_config or {}
        permeability_config = calculation_config.get("permeability", calculation_config)
        self.upstream_channel = permeability_config.get("upstream_channel")
        self.downstream_channel = permeability_config.get("downstream_channel")
        self.differential_channel = permeability_config.get("differential_channel")
        self.fluid_model = permeability_config.get("fluid_model", "incompressible_liquid")
        self.data_stale_after_s = float(calculation_config.get("data_stale_after_s", 2.0))
        self.simulation_mode = False
        if self.differential_channel is None and "DP" in self.channel_names:
            self.differential_channel = "DP"

        self.channel_widgets = {
            "P1": self.P1,
            "P2": self.P2,
            "P3": self.P3,
            "P4": self.P4,
            "DP": self.DP,
        }
        self.name_to_index = {name: index for index, name in enumerate(self.channel_names)}
        self.value_labels = [self.channel_widgets.get(name) for name in self.channel_names]
        self.status_labels = list(self.value_labels)

        self.latest_eng_corr: Dict[str, Optional[float]] = {}
        self.latest_eng_raw: Dict[str, Optional[float]] = {}
        self.channel_status: Dict[str, str] = {}
        self.latest_ts_ms: Optional[int] = None

        self.current_pump_flow_m3s: Optional[float] = None
        self.current_pump_raw = "-"
        self.current_pump_status = "DISCONNECTED"
        self.current_pump_ts_ms: Optional[int] = None
        self.current_oven_temp_c: Optional[float] = None
        self.current_oven_raw = "-"
        self.current_oven_status = "DISCONNECTED"
        self.current_oven_ts_ms: Optional[int] = None

        self.max_points = 5 * 60 * 10
        self.t = deque(maxlen=self.max_points)
        self.y = {name: deque(maxlen=self.max_points) for name in self.channel_names}
        self.dp_data = deque(maxlen=self.max_points)
        self.k_t = deque(maxlen=self.max_points)
        self.k_y = deque(maxlen=self.max_points)
        self.temp_t = deque(maxlen=self.max_points)
        self.temp_y = deque(maxlen=self.max_points)

        self.configurar_estilo_graficos()
        self.timer_relogio = QTimer(self)
        self.timer_relogio.timeout.connect(self.atualizar_data_hora)
        self.timer_relogio.start(1000)
        self.atualizar_data_hora()

        self.btn_operacao.clicked.connect(self.ir_para_operacao)
        self.btn_graficos.clicked.connect(self.ir_para_graficos)
        self.btn_start.clicked.connect(lambda: self.set_running(True))
        self.btn_stop.clicked.connect(lambda: self.set_running(False))
        self.set_running(False)

    def atualizar_data_hora(self):
        self.lbl_data.setText(QDate.currentDate().toString("dd/MM/yyyy"))
        self.lbl_hora.setText(QTime.currentTime().toString("HH:mm:ss"))

    def configurar_estilo_graficos(self):
        colors = ["b", "r", "g", "m", "c", "y"]
        self.widget_plot_pressao.setBackground("w")
        self.widget_plot_pressao.showGrid(x=True, y=True, alpha=0.3)
        self.widget_plot_pressao.setLabel("left", "Pressao")
        self.widget_plot_pressao.setLabel("bottom", "Amostras")
        self.widget_plot_pressao.addLegend(offset=(10, 10))
        self.pressure_curves = {}
        color_index = 0
        for name in self.channel_names:
            if name == self.differential_channel:
                continue
            curve = self.widget_plot_pressao.plot(
                [], [], pen=pg.mkPen(color=colors[color_index % len(colors)], width=2), name=name
            )
            self.pressure_curves[name] = curve
            color_index += 1
        self.curves = list(self.pressure_curves.values())

        self.widget_plot_pressao_dp.setBackground("w")
        self.widget_plot_pressao_dp.showGrid(x=True, y=True, alpha=0.3)
        self.widget_plot_pressao_dp.setLabel("left", "Pressao Diferencial")
        self.widget_plot_pressao_dp.setLabel("bottom", "Amostras")
        self.widget_plot_pressao_dp.addLegend(offset=(10, 10))
        self.curva_dp = self.widget_plot_pressao_dp.plot([], [], pen=pg.mkPen("k", width=2), name="DP")

        self.widget_plot_temp.setBackground("w")
        self.widget_plot_temp.showGrid(x=True, y=True, alpha=0.3)
        self.widget_plot_temp.setLabel("left", "Temperatura", units="C")
        self.widget_plot_temp.setLabel("bottom", "Amostras")
        self.curva_temp = self.widget_plot_temp.plot([], [], pen=pg.mkPen("k", width=2), name="temp")

        self.widget_plot_k.setBackground("w")
        self.widget_plot_k.showGrid(x=True, y=True, alpha=0.3)
        self.widget_plot_k.setLabel("left", "Permeabilidade", units="mD")
        self.widget_plot_k.setLabel("bottom", "Amostras")
        self.curva_k = self.widget_plot_k.plot([], [], pen=pg.mkPen("k", width=2), name="k")

    def ir_para_operacao(self):
        self.Paginas.setCurrentIndex(0)

    def ir_para_graficos(self):
        self.Paginas.setCurrentIndex(1)

    def set_running(self, running: bool):
        self.btn_start.setEnabled(not running)
        self.btn_stop.setEnabled(running)
        prefix = "SIMULACAO - " if self.simulation_mode else ""
        self.lbl_conn.setText(prefix + ("Status: Rodando" if running else "Status: Parado"))
        self.lbl_conn.setStyleSheet(
            "color: #000; font-weight: bold; background-color: #0F0; padding: 2px;"
            if running
            else "color: white; font-weight: bold; background-color: black; padding: 2px;"
        )

    def iniciar_daq(self):
        self.set_running(True)

    def parar_daq(self):
        self.set_running(False)

    def set_simulation_mode(self, enabled: bool):
        self.simulation_mode = bool(enabled)
        suffix = " [MODO SIMULACAO]" if self.simulation_mode else ""
        self.setWindowTitle("Sistema Coreflooding - Supervisorio" + suffix)
        self.set_running(False)

    def show_error(self, message: str):
        QMessageBox.critical(self, "Erro", message)

    def update_pump_flow(self, value_m3s: float):
        if math.isfinite(value_m3s) and value_m3s >= 0:
            self.current_pump_flow_m3s = value_m3s
            self.current_pump_ts_ms = int(time.time() * 1000)
            if self.flow_source.currentIndex() == 1:
                self.input_q.setValue(value_m3s)

    def update_pump_raw(self, text: str):
        self.current_pump_raw = text
        self.lbl_pump_raw.setText(f"Ultima mensagem: {text}")

    def update_pump_status(self, text: str):
        self.current_pump_status = text
        self.lbl_pump_status.setText(f"Status: {text}")

    def update_pump_error(self, text: str):
        self.current_pump_status = "ERROR"
        self.lbl_pump_status.setText("Status: Erro")
        self.lbl_pump_raw.setText(f"Ultima mensagem: {text}")

    def update_oven_temp(self, value_c: float):
        if math.isfinite(value_c):
            self.current_oven_temp_c = value_c
            self.current_oven_ts_ms = int(time.time() * 1000)
            if self.temp_source.currentIndex() == 1:
                self.lbl_temp.setText(f"{value_c:.2f} C")

    def update_oven_raw(self, text: str):
        self.current_oven_raw = text
        self.lbl_oven_raw.setText(f"Ultima mensagem: {text}")

    def update_oven_status(self, text: str):
        self.current_oven_status = text
        self.lbl_oven_status.setText(f"Status: {text}")

    def update_oven_error(self, text: str):
        self.current_oven_status = "ERROR"
        self.lbl_oven_status.setText("Status: Erro")
        self.lbl_oven_raw.setText(f"Ultima mensagem: {text}")

    def _is_fresh(self, timestamp_ms: Optional[int]) -> bool:
        return timestamp_ms is not None and (time.time() * 1000 - timestamp_ms) <= self.data_stale_after_s * 1000

    def get_current_temperature(self):
        if self.temp_source.currentIndex() == 0:
            return float(self.input_temp_manual.value())
        if not self._is_fresh(self.current_oven_ts_ms):
            return None
        return self.current_oven_temp_c

    def get_current_flow(self):
        if self.flow_source.currentIndex() == 0:
            return float(self.input_q.value())
        if not self._is_fresh(self.current_pump_ts_ms):
            return None
        return self.current_pump_flow_m3s

    def _set_k_unavailable(self):
        self.lbl_k.setText("-- mD")

    def calculate_permeability_realtime(self):
        try:
            if not self._is_fresh(self.latest_ts_ms):
                self._set_k_unavailable()
                return None
            q = self.get_current_flow()
            mu = float(self.input_mu.value())
            length_m = float(self.input_L.value())
            diameter_m = float(self.input_d.value())
            if q is None or not all(math.isfinite(x) for x in (q, mu, length_m, diameter_m)):
                raise ValueError("Vazao e parametros geometricos devem ser validos.")

            if self.dp_source.currentIndex() == 0:
                dp_name = self.differential_channel
                dp = self.latest_eng_corr.get(dp_name) if dp_name else None
                dp_unit = self.channel_units.get(dp_name, "bar") if dp_name else "bar"
                if dp is None:
                    raise ValueError("Canal diferencial sem leitura valida.")
                dp_pa = pressure_to_pa(dp, dp_unit)
            else:
                upstream = self.latest_eng_corr.get(self.upstream_channel)
                downstream = self.latest_eng_corr.get(self.downstream_channel)
                if upstream is None or downstream is None:
                    raise ValueError("Mapeamento de montante/jusante sem leituras validas.")
                dp_pa = pressure_to_pa(upstream, self.channel_units[self.upstream_channel]) - pressure_to_pa(
                    downstream, self.channel_units[self.downstream_channel]
                )

            result = permeability_darcy(q, mu, length_m, diameter_m, dp_pa, self.fluid_model)
            if not math.isfinite(result["k_mD"]):
                raise ValueError("Permeabilidade calculada nao e finita.")
            self.lbl_k.setText(f"{result['k_mD']:.2f} mD")
            return result["k_mD"]
        except (KeyError, TypeError, ValueError):
            self._set_k_unavailable()
            return None

    def _payload_channels(self, payload: dict) -> dict[str, dict[str, Any]]:
        channels = payload.get("channels")
        if isinstance(channels, dict):
            return channels
        raw = payload.get("eng_raw", [])
        corrected = payload.get("eng", [])
        statuses = payload.get("status", [])
        return {
            name: {
                "eng_raw": raw[index] if index < len(raw) else None,
                "eng": corrected[index] if index < len(corrected) else None,
                "status": statuses[index] if index < len(statuses) else "INVALID",
            }
            for index, name in enumerate(self.channel_names)
        }

    def update_data(self, payload):
        channels = self._payload_channels(payload)
        self.latest_ts_ms = int(payload.get("timestamp_ms", time.time() * 1000))
        for name in self.channel_names:
            item = channels.get(name, {})
            raw = item.get("eng_raw")
            corrected = item.get("eng")
            status = str(item.get("status", "INVALID"))
            self.latest_eng_raw[name] = float(raw) if raw is not None and math.isfinite(float(raw)) else None
            self.latest_eng_corr[name] = (
                float(corrected)
                if corrected is not None and math.isfinite(float(corrected)) and status == "OK"
                else None
            )
            self.channel_status[name] = status

        index = self.t[-1] + 1 if self.t else 0
        self.t.append(index)
        for name, widget in zip(self.channel_names, self.value_labels):
            if widget is None:
                continue
            value = self.latest_eng_corr.get(name)
            status = self.channel_status.get(name, "INVALID")
            if value is None:
                widget.setText("OFFLINE")
                widget.setObjectName("TagBad")
            else:
                widget.setText(f"{value:.2f} {self.channel_units.get(name, '')}".strip())
                widget.setObjectName("TagOK" if status == "OK" else "TagWarn")
            widget.style().unpolish(widget)
            widget.style().polish(widget)

        upstream = self.latest_eng_corr.get(self.upstream_channel)
        downstream = self.latest_eng_corr.get(self.downstream_channel)
        if upstream is not None and downstream is not None:
            unit = self.channel_units.get(self.upstream_channel, "bar")
            dp_pa = pressure_to_pa(upstream, unit) - pressure_to_pa(
                downstream, self.channel_units.get(self.downstream_channel, unit)
            )
            dp_display = pressure_from_pa(dp_pa, unit)
            pmean = (pressure_to_pa(upstream, unit) + pressure_to_pa(
                downstream, self.channel_units.get(self.downstream_channel, unit)
            )) / 2.0
            pmean_display = pressure_from_pa(pmean, unit)
            self.dpcalc.setText(f"{dp_display:.2f} {unit}")
            self.lbl_pmean.setText(f"{pmean_display:.2f} {unit}")
            self.lbl_sigma_eff.setText(f"{pressure_from_pa(dp_pa / 2.0, unit):.2f} {unit}")
            self.dp_data.append(dp_display)
        else:
            self.dpcalc.setText("--")
            self.lbl_pmean.setText("--")
            self.lbl_sigma_eff.setText("--")
            self.dp_data.append(np.nan)
        self.curva_dp.setData(list(self.t), list(self.dp_data))

        temperature = self.get_current_temperature()
        if temperature is not None:
            self.lbl_temp.setText(f"{temperature:.2f} C")
            self.temp_t.append(index)
            self.temp_y.append(temperature)
        else:
            self.temp_t.append(index)
            self.temp_y.append(np.nan)
        self.curva_temp.setData(list(self.temp_t), list(self.temp_y))

        k_value = self.calculate_permeability_realtime()
        self.k_t.append(index)
        self.k_y.append(k_value if k_value is not None else np.nan)
        self.curva_k.setData(list(self.k_t), list(self.k_y))

        for name, curve in self.pressure_curves.items():
            value = self.latest_eng_corr.get(name)
            self.y[name].append(value if value is not None else np.nan)
            curve.setData(list(self.t), list(self.y[name]))

    def get_raw_by_name(self, name: str):
        return self.latest_eng_raw.get(name)

    def get_corr_by_name(self, name: str):
        return self.latest_eng_corr.get(name)
