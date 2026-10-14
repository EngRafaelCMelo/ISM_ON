from __future__ import annotations

import os
import sys
import traceback

from PyQt5.QtCore import QMetaObject, QThread, Qt
from PyQt5.QtWidgets import QApplication, QDialog, QMessageBox

from config import device_config, load_config
from daq_worker import DaqWorker
from mainwindow import TelaPrincipal
from oven_worker import OvenWorker
from pump_worker import PumpWorker
from simulation_worker import SimulationWorker
from tela_login import Login


def resource_path(relative_path: str) -> str:
    base = getattr(sys, "_MEIPASS", os.path.abspath("."))
    return os.path.join(base, relative_path)


def show_fatal_error(title: str, error: Exception):
    message = f"{title}\n\n{error}\n\n{traceback.format_exc()}"
    QMessageBox.critical(None, "Erro Critico", message)


def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    login = Login()
    if login.exec_() != QDialog.Accepted:
        return 0

    try:
        config_path = resource_path("config.json")
        config = load_config(config_path)
        channel_configs = config["channels"]
        channel_names = [channel["name"] for channel in channel_configs]
        simulation_mode = "--simulate" in sys.argv or bool(config.get("simulation", {}).get("enabled", False))
        window = TelaPrincipal(
            channel_names,
            channel_configs=channel_configs,
            calculation_config=config.get("calculations", {}),
        )
        window.set_simulation_mode(simulation_mode)

        daq_thread = QThread()
        daq_worker = SimulationWorker(config_path) if simulation_mode else DaqWorker(config_path)
        daq_worker.moveToThread(daq_thread)
        daq_thread.started.connect(daq_worker.start)
        daq_worker.stopped.connect(daq_thread.quit)
        daq_worker.stopped.connect(lambda: window.set_running(False))
        daq_worker.data.connect(window.update_data)
        daq_worker.error.connect(window.show_error)

        def start_daq():
            if not daq_thread.isRunning():
                daq_thread.start()
            window.set_running(True)

        def stop_daq():
            if daq_thread.isRunning():
                QMetaObject.invokeMethod(daq_worker, "stop", Qt.QueuedConnection)
            window.set_running(False)

        window.btn_start.clicked.connect(start_daq)
        window.btn_stop.clicked.connect(stop_daq)

        pump_cfg = device_config(config, "pump")
        pump = PumpWorker(
            port=pump_cfg["port"],
            baudrate=pump_cfg["baudrate"],
            timeout_s=pump_cfg["timeout_s"],
            stale_after_s=pump_cfg["stale_after_s"],
        )
        pump.flow_received.connect(window.update_pump_flow)
        pump.raw_received.connect(window.update_pump_raw)
        pump.status.connect(window.update_pump_status)
        pump.error.connect(window.update_pump_error)
        window.btn_pump_connect.clicked.connect(pump.start)
        window.btn_pump_disconnect.clicked.connect(pump.stop)

        oven_cfg = device_config(config, "oven")
        oven = OvenWorker(
            port=oven_cfg["port"],
            baudrate=oven_cfg["baudrate"],
            timeout_s=oven_cfg["timeout_s"],
            stale_after_s=oven_cfg["stale_after_s"],
        )
        oven.temp_received.connect(window.update_oven_temp)
        oven.raw_received.connect(window.update_oven_raw)
        oven.status.connect(window.update_oven_status)
        oven.error.connect(window.update_oven_error)
        window.btn_oven_connect.clicked.connect(oven.start)
        window.btn_oven_disconnect.clicked.connect(oven.stop)

        def shutdown():
            if daq_thread.isRunning():
                QMetaObject.invokeMethod(daq_worker, "stop", Qt.QueuedConnection)
                if not daq_thread.wait(3000):
                    daq_thread.quit()
                    daq_thread.wait(1000)
            pump.stop()
            oven.stop()

        app.aboutToQuit.connect(shutdown)
        window.set_running(False)
        window.show()
        app._window = window
        app._daq_thread = daq_thread
        app._daq_worker = daq_worker
        app._pump = pump
        app._oven = oven
        app.setQuitOnLastWindowClosed(True)
        return app.exec_()
    except Exception as error:
        show_fatal_error("Erro ao carregar o sistema principal", error)
        return 1


if __name__ == "__main__":
    sys.exit(main())
