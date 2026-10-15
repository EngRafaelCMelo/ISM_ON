"""Carregamento e validacao da configuracao do equipamento."""

from __future__ import annotations

import json
import math
import os
import shutil
import tempfile
from datetime import datetime, timezone
from typing import Any, Dict

from units import PRESSURE_TO_PA


def load_config(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as file:
        data = json.load(file)
    validate_config(data)
    return data


def save_config(path: str, config: Dict[str, Any], create_backup: bool = True) -> None:
    """Valida e grava a configuracao sem deixar arquivo parcialmente escrito."""
    validate_config(config)
    directory = os.path.dirname(os.path.abspath(path)) or "."
    os.makedirs(directory, exist_ok=True)
    if create_backup and os.path.exists(path):
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        shutil.copy2(path, f"{path}.{stamp}.bak")
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=directory,
            prefix=".config-", suffix=".tmp", delete=False
        ) as file:
            temporary = file.name
            json.dump(config, file, indent=2, ensure_ascii=False)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, path)
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)


def validate_config(config: Dict[str, Any]) -> None:
    if not isinstance(config, dict):
        raise ValueError("Configuracao deve ser um objeto JSON.")

    rate = config.get("sample_rate_hz", 10)
    if not isinstance(rate, (int, float)) or not math.isfinite(float(rate)) or float(rate) <= 0:
        raise ValueError("sample_rate_hz deve ser finito e maior que zero.")

    channels = config.get("channels")
    if not isinstance(channels, list) or not channels:
        raise ValueError("A configuracao deve conter ao menos um canal.")

    names = set()
    for channel in channels:
        if not isinstance(channel, dict):
            raise ValueError("Cada canal deve ser um objeto JSON.")
        name = channel.get("name")
        physical = channel.get("physical")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Cada canal deve possuir um nome.")
        if name in names:
            raise ValueError(f"Canal duplicado: {name}.")
        names.add(name)
        if not isinstance(physical, str) or not physical.strip():
            raise ValueError(f"Canal {name} sem canal fisico valido.")
        try:
            lrv = float(channel["lrv"])
            urv = float(channel["urv"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"Faixa invalida no canal {name}.") from exc
        if not math.isfinite(lrv) or not math.isfinite(urv) or urv <= lrv:
            raise ValueError(f"URV deve ser maior que LRV no canal {name}.")
        unit = str(channel.get("unit", "bar")).lower()
        if unit not in PRESSURE_TO_PA:
            raise ValueError(f"Unidade de pressao invalida no canal {name}: {unit}.")

    calculation = config.get("calculations", {})
    if not isinstance(calculation, dict):
        raise ValueError("calculations deve ser um objeto JSON.")
    permeability = calculation.get("permeability", {})
    if not isinstance(permeability, dict):
        raise ValueError("calculations.permeability deve ser um objeto JSON.")
    for key in ("upstream_channel", "downstream_channel", "differential_channel"):
        value = permeability.get(key)
        if value is not None and value not in names:
            raise ValueError(f"{key} referencia canal inexistente: {value}.")
    fluid_model = permeability.get("fluid_model", "incompressible_liquid")
    if fluid_model not in {"incompressible_liquid", "gas_pulse_decay"}:
        raise ValueError(f"Modelo de fluido nao suportado: {fluid_model}.")

    limits = config.get("limits_mA", {})
    if not isinstance(limits, dict):
        raise ValueError("limits_mA deve ser um objeto JSON.")
    for key in ("open_loop_low_mA", "overrange_high_mA"):
        value = limits.get(key)
        if value is not None and (not math.isfinite(float(value))):
            raise ValueError(f"Limite invalido: {key}.")

    devices = config.get("devices", {})
    if not isinstance(devices, dict):
        raise ValueError("devices deve ser um objeto JSON.")
    for device_name in ("pump", "oven"):
        device = devices.get(device_name, {})
        if not isinstance(device, dict):
            raise ValueError(f"Configuracao invalida para {device_name}.")
        if "baudrate" in device:
            try:
                baudrate = int(device["baudrate"])
            except (TypeError, ValueError) as exc:
                raise ValueError(f"baudrate invalido para {device_name}.") from exc
            if baudrate <= 0:
                raise ValueError(f"baudrate invalido para {device_name}.")
        if "port" in device and not str(device["port"]).strip():
            raise ValueError(f"porta invalida para {device_name}.")
        for timeout_key in ("timeout_s", "stale_after_s"):
            if timeout_key in device:
                try:
                    timeout_value = float(device[timeout_key])
                except (TypeError, ValueError) as exc:
                    raise ValueError(f"{timeout_key} invalido para {device_name}.") from exc
                if not math.isfinite(timeout_value) or timeout_value <= 0:
                    raise ValueError(f"{timeout_key} invalido para {device_name}.")

    for section_name in ("auth", "calibration", "sessions", "plot", "events"):
        section = config.get(section_name, {})
        if not isinstance(section, dict):
            raise ValueError(f"{section_name} deve ser um objeto JSON.")
    plot = config.get("plot", {})
    if "max_history_s" in plot and (not math.isfinite(float(plot["max_history_s"])) or float(plot["max_history_s"]) <= 0):
        raise ValueError("plot.max_history_s deve ser finito e maior que zero.")

    parameters = config.get("parameters", {})
    if not isinstance(parameters, dict):
        raise ValueError("parameters deve ser um objeto JSON.")
    positive_parameters = (
        "diameter_m", "length_m", "viscosity_pa_s",
        "vref_cm3", "vcell_cm3", "vu_cm3", "vd_cm3",
    )
    for key in positive_parameters:
        if key in parameters:
            try:
                value = float(parameters[key])
            except (TypeError, ValueError) as exc:
                raise ValueError(f"Parametro invalido: {key}.") from exc
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"Parametro deve ser maior que zero: {key}.")
    for key in ("flow_m3s_manual", "temperature_c_manual"):
        if key in parameters:
            try:
                value = float(parameters[key])
            except (TypeError, ValueError) as exc:
                raise ValueError(f"Parametro invalido: {key}.") from exc
            if not math.isfinite(value) or (key == "flow_m3s_manual" and value < 0):
                raise ValueError(f"Parametro invalido: {key}.")
    model = parameters.get("test_model")
    if model is not None and model not in {"incompressible_liquid", "gas_pulse_decay"}:
        raise ValueError(f"Modelo de ensaio nao suportado: {model}.")


def device_config(config: Dict[str, Any], name: str) -> Dict[str, Any]:
    defaults = {
        "port": "COM5" if name == "pump" else "COM6",
        "baudrate": 9600,
        "timeout_s": 1.0,
        "stale_after_s": 3.0,
    }
    defaults.update(config.get("devices", {}).get(name, {}))
    return defaults


def resolve_relative_path(base_path: str, configured_path: str) -> str:
    if os.path.isabs(configured_path):
        return configured_path
    return os.path.join(os.path.dirname(os.path.abspath(base_path)), configured_path)
