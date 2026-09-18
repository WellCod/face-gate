"""EAR — a conta que decide se o olho está aberto ou fechado.

O reconhecimento facial em si depende de pesos baixados em runtime e fica fora
da suíte. O cálculo do EAR não: é geometria pura e é onde mora a decisão.
"""

from types import SimpleNamespace

import pytest

from liveness_service import (
    EAR_CLOSED_THRESHOLD,
    EAR_OPEN_THRESHOLD,
    LEFT_EYE,
    RIGHT_EYE,
    _ear,
    detectar_liveness,
)


def _olho(abertura: float) -> dict:
    """Monta os 6 landmarks de um olho com abertura controlada.

    A largura é 1.0 e cada pálpebra fica a `abertura` do centro, então o EAR
    resultante é exatamente 2 × abertura.
    """
    pontos = [
        (0.00, 0.50),
        (0.25, 0.50 - abertura),
        (0.75, 0.50 - abertura),
        (1.00, 0.50),
        (0.75, 0.50 + abertura),
        (0.25, 0.50 + abertura),
    ]
    return {
        idx: SimpleNamespace(x=x, y=y)
        for idx, (x, y) in zip(LEFT_EYE, pontos)
    }


def test_olho_aberto_fica_acima_do_limite_de_abertura() -> None:
    ear = _ear(_olho(0.15), LEFT_EYE, w=1, h=1)
    assert ear == pytest.approx(0.30, abs=1e-6)
    assert ear > EAR_OPEN_THRESHOLD


def test_olho_fechado_fica_abaixo_do_limite_de_fechamento() -> None:
    ear = _ear(_olho(0.05), LEFT_EYE, w=1, h=1)
    assert ear == pytest.approx(0.10, abs=1e-6)
    assert ear < EAR_CLOSED_THRESHOLD


def test_ear_escala_com_a_resolucao_do_frame() -> None:
    """Dobrar o frame não muda o EAR — é uma razão, não uma distância."""
    olho = _olho(0.15)
    assert _ear(olho, LEFT_EYE, w=640, h=480) == pytest.approx(
        _ear(olho, LEFT_EYE, w=1280, h=960), abs=1e-5
    )


def test_olho_degenerado_nao_divide_por_zero() -> None:
    """Landmarks colapsados num ponto não podem estourar a detecção."""
    colapsado = {idx: SimpleNamespace(x=0.5, y=0.5) for idx in LEFT_EYE}
    assert _ear(colapsado, LEFT_EYE, w=640, h=480) == 0.0


def test_histerese_entre_os_dois_limites() -> None:
    """Fechar exige EAR menor que abrir. Sem essa folga, ruído vira piscada."""
    assert EAR_CLOSED_THRESHOLD < EAR_OPEN_THRESHOLD


def test_indices_dos_olhos_nao_se_sobrepoem() -> None:
    assert len(LEFT_EYE) == len(RIGHT_EYE) == 6
    assert not set(LEFT_EYE) & set(RIGHT_EYE)


def test_sem_frames_recusa_com_motivo() -> None:
    r = detectar_liveness([])
    assert r.passou is False
    assert r.piscadas == 0
    assert r.motivo


def test_frames_de_menos_recusa_com_motivo() -> None:
    """Uma piscada precisa de aberto → fechado → aberto: menos de 3 não dá."""
    import numpy as np

    frames = [np.zeros((48, 48, 3), dtype=np.uint8)] * 2
    r = detectar_liveness(frames)
    assert r.passou is False
    assert r.motivo
