"""Conversoes de unidades usadas pelo supervisorio.

O processamento cientifico usa SI internamente. A interface e a configuracao
podem continuar usando unidades de engenharia, desde que informem a unidade.
"""

from __future__ import annotations

import math
from typing import Mapping


PRESSURE_TO_PA: Mapping[str, float] = {
    "pa": 1.0,
    "kpa": 1e3,
    "mpa": 1e6,
    "bar": 1e5,
    "psi": 6894.757293168,
}

FLOW_TO_M3_S: Mapping[str, float] = {
    "m3/s": 1.0,
    "m3s": 1.0,
    "l/s": 1e-3,
    "l/min": 1e-3 / 60.0,
    "ml/min": 1e-6 / 60.0,
}


def _normalise(unit: str) -> str:
    if not isinstance(unit, str) or not unit.strip():
        raise ValueError("Unidade deve ser uma string nao vazia.")
    return unit.strip().lower().replace(" ", "")


def _finite(value: float, name: str = "valor") -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} deve ser numerico.") from exc
    if not math.isfinite(result):
        raise ValueError(f"{name} deve ser finito.")
    return result


def pressure_to_pa(value: float, unit: str) -> float:
    """Converte uma pressao para Pa."""
    key = _normalise(unit)
    if key not in PRESSURE_TO_PA:
        raise ValueError(f"Unidade de pressao nao suportada: {unit!r}.")
    return _finite(value, "pressao") * PRESSURE_TO_PA[key]


def pressure_from_pa(value_pa: float, unit: str) -> float:
    """Converte uma pressao em Pa para a unidade solicitada."""
    key = _normalise(unit)
    if key not in PRESSURE_TO_PA:
        raise ValueError(f"Unidade de pressao nao suportada: {unit!r}.")
    return _finite(value_pa, "pressao em Pa") / PRESSURE_TO_PA[key]


def convert_pressure(value: float, from_unit: str, to_unit: str) -> float:
    return pressure_from_pa(pressure_to_pa(value, from_unit), to_unit)


def flow_to_m3s(value: float, unit: str) -> float:
    """Converte vazao para m3/s."""
    key = _normalise(unit)
    if key not in FLOW_TO_M3_S:
        raise ValueError(f"Unidade de vazao nao suportada: {unit!r}.")
    return _finite(value, "vazao") * FLOW_TO_M3_S[key]


def mA_to_engineering(mA: float, lrv: float, urv: float) -> float:
    """Converte o sinal 4-20 mA para a faixa configurada."""
    current = _finite(mA, "corrente")
    low = _finite(lrv, "LRV")
    high = _finite(urv, "URV")
    if high <= low:
        raise ValueError("URV deve ser maior que LRV.")
    return low + ((current - 4.0) / 16.0) * (high - low)


def require_positive(value: float, name: str) -> float:
    result = _finite(value, name)
    if result <= 0:
        raise ValueError(f"{name} deve ser maior que zero.")
    return result
