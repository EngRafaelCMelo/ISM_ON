"""Calculos cientificos independentes da interface grafica."""

from __future__ import annotations

import math

import numpy as np

from units import pressure_to_pa


DARCY_M2 = 9.869233e-13
MILLI_DARCY_M2 = 9.869233e-16


def differential_pressures(
    measured_value,
    measured_unit: str,
    upstream_value,
    upstream_unit: str,
    downstream_value,
    downstream_unit: str,
    measured_status: str = "OK",
    upstream_status: str = "OK",
    downstream_status: str = "OK",
) -> dict:
    """Keep transducer DP and Pu-Pd DP as distinct SI values.

    Invalid channels return ``None`` instead of reusing a previous sample.
    The UI can choose either returned value for a downstream calculation.
    """
    measured_pa = None
    if measured_status == "OK" and measured_value is not None:
        measured_pa = pressure_to_pa(measured_value, measured_unit)

    calculated_pa = None
    if (
        upstream_status == "OK" and downstream_status == "OK"
        and upstream_value is not None and downstream_value is not None
    ):
        calculated_pa = (
            pressure_to_pa(upstream_value, upstream_unit)
            - pressure_to_pa(downstream_value, downstream_unit)
        )
    return {"measured_pa": measured_pa, "calculated_pa": calculated_pa}


def bulk_volume_cylinder(d_m: float, L_m: float) -> float:
    if not math.isfinite(float(d_m)) or not math.isfinite(float(L_m)):
        raise ValueError("Diametro e comprimento devem ser finitos.")
    if d_m <= 0 or L_m <= 0:
        raise ValueError("Diametro e comprimento devem ser maiores que zero.")
    return math.pi * (d_m / 2.0) ** 2 * L_m


def porosity_from_p1_p2(
    p1_pa: float,
    p2_pa: float,
    vref_m3: float,
    vcell_empty_m3: float,
    vbulk_m3: float,
) -> dict:
    """Calcula porosidade pelo modelo de expansao de gas ideal isotermica."""
    values = (p1_pa, p2_pa, vref_m3, vcell_empty_m3, vbulk_m3)
    if not all(math.isfinite(float(value)) for value in values):
        raise ValueError("Entradas devem ser numericas e finitas.")
    if p2_pa <= 0:
        raise ValueError("P2 invalida (<=0).")
    if p1_pa <= 0:
        raise ValueError("P1 invalida (<=0).")
    if p1_pa <= p2_pa:
        raise ValueError("Para este modelo, precisa P1 > P2.")
    if vref_m3 <= 0 or vcell_empty_m3 <= 0 or vbulk_m3 <= 0:
        raise ValueError("Volumes devem ser > 0.")

    vvoid = vref_m3 * (p1_pa / p2_pa - 1.0)
    vgrain = vcell_empty_m3 - vvoid
    vpore = vbulk_m3 - vgrain
    phi = vpore / vbulk_m3

    if vgrain < 0 or vpore < 0 or vpore > vbulk_m3:
        raise ValueError("Volumes calculados sao fisicamente inconsistentes.")

    return {
        "Vvoid_m3": float(vvoid),
        "Vgrain_m3": float(vgrain),
        "Vpore_m3": float(vpore),
        "phi": float(phi),
        "phi_percent": float(phi * 100.0),
    }


def estimate_alpha_from_decay(t_s: np.ndarray, dP_pa: np.ndarray) -> float:
    """Ajusta ln(dP) = ln(dP0) - alpha*t."""
    t_s = np.asarray(t_s, dtype=float)
    dP_pa = np.asarray(dP_pa, dtype=float)
    if t_s.shape != dP_pa.shape or t_s.ndim != 1:
        raise ValueError("Tempo e pressao diferencial devem ser vetores do mesmo tamanho.")
    if not np.all(np.isfinite(t_s)) or not np.all(np.isfinite(dP_pa)):
        raise ValueError("Dados do decay devem ser finitos.")
    if len(t_s) < 2 or np.any(np.diff(t_s) < 0):
        raise ValueError("Tempo do decay deve ser crescente.")

    mask = dP_pa > 0
    t = t_s[mask]
    y = np.log(dP_pa[mask])

    if len(t) < 20:
        raise ValueError("Poucos pontos para estimar alpha (minimo ~20).")

    slope, _ = np.polyfit(t, y, 1)
    alpha = -slope
    if not math.isfinite(float(alpha)) or alpha <= 0:
        raise ValueError("Alpha estimado <= 0 (decay ruim ou dados inconsistentes).")
    return float(alpha)


def permeability_pulse_decay(
    alpha_1_s: float,
    mu_pa_s: float,
    L_m: float,
    A_m2: float,
    Pm_pa: float,
    Vu_m3: float,
    Vd_m3: float,
) -> dict:
    """Calcula permeabilidade pelo modelo pulse-decay de gas ideal."""
    values = [alpha_1_s, mu_pa_s, L_m, A_m2, Pm_pa, Vu_m3, Vd_m3]
    if not all(math.isfinite(float(x)) for x in values):
        raise ValueError("Parametros devem ser finitos.")
    if any(x <= 0 for x in values):
        raise ValueError("Parametros precisam ser maiores que zero.")

    denom = A_m2 * Pm_pa * (1.0 / Vu_m3 + 1.0 / Vd_m3)
    k_m2 = alpha_1_s * mu_pa_s * L_m / denom
    k_mD = k_m2 / MILLI_DARCY_M2

    return {"k_m2": float(k_m2), "k_mD": float(k_mD)}


def permeability_darcy(
    q_m3s: float,
    mu_pa_s: float,
    L_m: float,
    diameter_m: float,
    dp_pa: float,
    fluid_model: str = "incompressible_liquid",
) -> dict:
    """Calcula k pela lei de Darcy para liquido incompressivel."""
    if fluid_model != "incompressible_liquid":
        raise ValueError("A lei de Darcy nesta funcao e restrita a liquido incompressivel.")
    values = [q_m3s, mu_pa_s, L_m, diameter_m, dp_pa]
    if not all(math.isfinite(float(x)) for x in values):
        raise ValueError("Parametros de Darcy devem ser finitos.")
    if any(x <= 0 for x in values):
        raise ValueError("Parametros de Darcy devem ser maiores que zero.")
    area_m2 = math.pi * (diameter_m / 2.0) ** 2
    k_m2 = q_m3s * mu_pa_s * L_m / (area_m2 * dp_pa)
    if not math.isfinite(k_m2) or k_m2 < 0:
        raise ValueError("Resultado de permeabilidade invalido.")
    return {"k_m2": float(k_m2), "k_mD": float(k_m2 / MILLI_DARCY_M2)}
