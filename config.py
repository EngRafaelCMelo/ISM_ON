"""Carregamento e validacao da configuracao do equipamento."""

from __future__ import annotations

import json
import math
import os
from typing import Any, Dict

from units import PRESSURE_TO_PA


def load_config(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as file:
        data = json.load(file)
    validate_config(data)
    return data


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
        if "baudrate" in device and int(device["baudrate"]) <= 0:
            raise ValueError(f"baudrate invalido para {device_name}.")
        for timeout_key in ("timeout_s", "stale_after_s"):
            if timeout_key in device and float(device[timeout_key]) <= 0:
                raise ValueError(f"{timeout_key} invalido para {device_name}.")


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
