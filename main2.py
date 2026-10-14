from __future__ import annotations

import copy
import os
import shutil
import sys
import traceback

from PyQt5.QtWidgets import QApplication, QDialog, QMessageBox

from acquisition_controller import AcquisitionController
from calibration_store import load_calibration
from config import device_config, load_config, resolve_relative_path, save_config
from daq_worker import DaqWorker
from events import EventManager
from mainwindow import TelaPrincipal
from oven_worker import OvenWorker
from pump_worker import PumpWorker
from session_dialog import SessionDialog
from session_manager import SessionRecorder
from simulation_worker import SimulationWorker
from tela_login import Login


def resource_path(relative_path: str) -> str:
    base = getattr(sys, "_MEIPASS", os.path.abspath("."))
    return os.path.join(base, relative_path)


def runtime_path(relative_path: str) -> str:
    if not hasattr(sys, "_MEIPASS"):
        return os.path.abspath(relative_path)
    data_dir = os.path.join(os.path.dirname(os.path.abspath(sys.executable)), "data")
    os.makedirs(data_dir, exist_ok=True)
    target = os.path.join(data_dir, relative_path)
    bundled = resource_path(relative_path)
    if not os.path.exists(target) and os.path.exists(bundled):
        shutil.copy2(bundled, target)
    return target


def show_fatal_error(title: str, error: Exception):
    message = f"{title}\n\n{error}\n\n{traceback.format_exc()}"
    QMessageBox.critical(None, "Erro Critico", message)


def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(True)
    config_path = runtime_path("config.json")
    try:
        config = load_config(config_path)
    except Exception as error:
        show_fatal_error("Erro na configuracao", error)
        return 1

    data_root = os.path.dirname(os.path.abspath(config_path))
    users_path = resolve_relative_path(config_path, str(config.get("auth", {}).get("users_path", "users.json")))
    login = Login(users_path)
    if login.exec_() != QDialog.Accepted:
        return 0
    user = login.authenticated_user or {"username": "", "role": "operator"}

    try:
        channel_configs = config["channels"]
        channel_names = [channel["name"] for channel in channel_configs]
        simulation_mode = "--simulate" in sys.argv or bool(config.get("simulation", {}).get("enabled", False))
        calibration_path = resolve_relative_path(config_path, str(config.get("calibration", {}).get("path", "calibration.json")))
        window = TelaPrincipal(
            channel_names,
            channel_configs=channel_configs,
            calculation_config=config.get("calculations", {}),
            calibration_path=calibration_path,
            config_path=config_path,
            config_data=config,
            username=user.get("username", ""),
            user_role=user.get("role", "operator"),
        )
        window.set_simulation_mode(simulation_mode)

        events = EventManager()
        recorder = SessionRecorder(resolve_relative_path(config_path, str(config.get("sessions", {}).get("folder", "ensaios"))))

        def handle_event(event):
            window.show_event(event)
            recorder.record_event(event.source, event.severity, event.message, event.code)

        events.subscribe(handle_event)

        controller = AcquisitionController(
            lambda: SimulationWorker(config_path) if simulation_mode else DaqWorker(config_path), window
        )
        controller.state_changed.connect(window.set_operation_state)
        controller.data.connect(window.update_data)
        controller.error.connect(window.show_error)
        controller.error.connect(lambda message: events.emit("DAQ", "ERROR", message, "DAQ_ERROR"))
        controller.worker_started.connect(lambda: events.emit("DAQ", "INFO", "Worker confirmou aquisicao", "DAQ_STARTED"))
        controller.worker_stopped.connect(lambda: events.emit("DAQ", "INFO", "Worker encerrou aquisicao", "DAQ_STOPPED"))
        window.start_requested.connect(controller.start)
        window.stop_requested.connect(controller.stop)

        reported_sensor_states = {}

        def handle_data(payload):
            window.update_data(payload)
            if recorder.active:
                recorder.record(payload, window.derived_snapshot())
            for name, item in (payload.get("channels") or {}).items():
                state = str(item.get("status", "INVALID"))
                if state != "OK" and reported_sensor_states.get(name) != state:
                    severity = "ALARM" if state in {"OPEN_LOOP", "OVERRANGE"} else "WARNING"
                    events.emit("DAQ", severity, f"Canal {name}: {state}", f"SENSOR_{state}")
                reported_sensor_states[name] = state

        controller.data.disconnect(window.update_data)
        controller.data.connect(handle_data)

        pump_cfg = device_config(config, "pump")
        pump = PumpWorker(**pump_cfg)
        pump.flow_received.connect(window.update_pump_flow)
        pump.raw_received.connect(window.update_pump_raw)
        pump.status.connect(window.update_pump_status)
        pump.state.connect(window.update_pump_state)
        pump.error.connect(window.update_pump_error)
        pump.error.connect(lambda message: events.emit("PUMP", "ERROR", message, "PUMP_ERROR"))
        window.btn_pump_connect.clicked.connect(pump.start)
        window.btn_pump_disconnect.clicked.connect(pump.stop)

        oven_cfg = device_config(config, "oven")
        oven = OvenWorker(**oven_cfg)
        oven.temp_received.connect(window.update_oven_temp)
        oven.raw_received.connect(window.update_oven_raw)
        oven.status.connect(window.update_oven_status)
        oven.state.connect(window.update_oven_state)
        oven.error.connect(window.update_oven_error)
        oven.error.connect(lambda message: events.emit("OVEN", "ERROR", message, "OVEN_ERROR"))
        window.btn_oven_connect.clicked.connect(oven.start)
        window.btn_oven_disconnect.clicked.connect(oven.stop)

        def serial_settings(values):
            if values == "check":
                return not pump.isRunning() and not oven.isRunning()
            if pump.isRunning() or oven.isRunning():
                events.emit("CONFIG", "WARNING", "Desconecte os dispositivos antes de alterar portas", "SERIAL_BUSY")
                return False
            updated = copy.deepcopy(config)
            updated.setdefault("devices", {}).update(values)
            save_config(config_path, updated)
            pump.configure(**values["pump"])
            oven.configure(**values["oven"])
            config.clear(); config.update(updated)
            window.config_data = config
            events.emit("CONFIG", "INFO", "Configuracao serial salva", "SERIAL_CONFIG_SAVED")
            return True

        window.set_serial_settings_callback(serial_settings)

        def start_session():
            if controller.state.value != "RUNNING":
                QMessageBox.warning(window, "Ensaio", "Inicie e confirme a aquisicao antes de registrar um ensaio.")
                return
            dialog = SessionDialog(window, user.get("username", ""))
            if dialog.exec_() != QDialog.Accepted:
                return
            values = dialog.values()
            try:
                path = recorder.start(
                    **values,
                    parameters=window.parameter_snapshot(),
                    sensor_config=copy.deepcopy(config.get("channels", [])),
                    calibration=load_calibration(calibration_path),
                    source="SIMULATED" if simulation_mode else "REAL",
                    simulated=simulation_mode,
                )
                window.set_session_active(True, path)
                events.emit("SESSION", "INFO", f"Ensaio registrado em {path}", "SESSION_STARTED")
            except Exception as error:
                events.emit("SESSION", "ERROR", f"Falha ao iniciar ensaio: {error}", "SESSION_START_ERROR")
                QMessageBox.critical(window, "Ensaio", str(error))

        def stop_session():
            path = recorder.stop()
            window.set_session_active(False, path)
            if path:
                events.emit("SESSION", "INFO", f"Ensaio encerrado em {path}", "SESSION_STOPPED")

        window.start_session_requested.connect(start_session)
        window.stop_session_requested.connect(stop_session)

        def on_operation_state(state):
            if state in {"STOPPED", "ERROR"} and recorder.active:
                stop_session()

        controller.state_changed.connect(on_operation_state)

        def shutdown():
            if recorder.active:
                stop_session()
            controller.close()
            pump.stop()
            oven.stop()

        app.aboutToQuit.connect(shutdown)
        window.set_operation_state(controller.state)
        window.show()
        app._window = window
        app._acquisition_controller = controller
        app._pump = pump
        app._oven = oven
        app._session_recorder = recorder
        return app.exec_()
    except Exception as error:
        show_fatal_error("Erro ao carregar o sistema principal", error)
        return 1


if __name__ == "__main__":
    sys.exit(main())
