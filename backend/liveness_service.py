from dataclasses import dataclass
from typing import List, Optional

import cv2
import mediapipe as mp
import numpy as np

# Índices de landmarks do FaceMesh para os olhos (modelo de 468 pontos).
LEFT_EYE = [33, 160, 158, 133, 153, 144]
RIGHT_EYE = [362, 385, 387, 263, 373, 380]

EAR_CLOSED_THRESHOLD = 0.21
EAR_OPEN_THRESHOLD = 0.25
HEAD_MOVEMENT_THRESHOLD = 0.04  # variação relativa do nariz no frame


@dataclass
class LivenessResult:
    passou: bool
    piscadas: int
    movimento_cabeca: float
    motivo: Optional[str] = None


def _ear(landmarks, indices, w: int, h: int) -> float:
    pts = np.array(
        [(landmarks[i].x * w, landmarks[i].y * h) for i in indices], dtype=np.float32
    )
    vert1 = np.linalg.norm(pts[1] - pts[5])
    vert2 = np.linalg.norm(pts[2] - pts[4])
    horiz = np.linalg.norm(pts[0] - pts[3])
    if horiz == 0:
        return 0.0
    return (vert1 + vert2) / (2.0 * horiz)


def detectar_liveness(frames: List[np.ndarray]) -> LivenessResult:
    """Recebe lista de frames (BGR) e detecta piscadas/movimento.

    Considera vivo se houver pelo menos 1 piscada OU movimento de cabeça relevante.
    """
    if not frames:
        return LivenessResult(False, 0, 0.0, "Nenhum frame recebido para liveness.")

    if len(frames) < 3:
        return LivenessResult(
            False,
            0,
            0.0,
            "Frames insuficientes para liveness (envie pelo menos 3 frames).",
        )

    mp_face_mesh = mp.solutions.face_mesh
    piscadas = 0
    olho_fechado_anterior = False
    nariz_pontos: List[np.ndarray] = []
    ear_serie: List[float] = []

    with mp_face_mesh.FaceMesh(
        static_image_mode=True,
        max_num_faces=1,
        refine_landmarks=False,
        min_detection_confidence=0.5,
    ) as face_mesh:
        for frame in frames:
            if frame is None:
                continue
            h, w = frame.shape[:2]
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            result = face_mesh.process(rgb)
            if not result.multi_face_landmarks:
                ear_serie.append(-1.0)
                continue
            landmarks = result.multi_face_landmarks[0].landmark

            ear_left = _ear(landmarks, LEFT_EYE, w, h)
            ear_right = _ear(landmarks, RIGHT_EYE, w, h)
            ear = (ear_left + ear_right) / 2.0
            ear_serie.append(ear)

            nariz = landmarks[1]
            nariz_pontos.append(np.array([nariz.x, nariz.y], dtype=np.float32))

            if ear < EAR_CLOSED_THRESHOLD:
                olho_fechado_anterior = True
            elif ear > EAR_OPEN_THRESHOLD and olho_fechado_anterior:
                piscadas += 1
                olho_fechado_anterior = False

    movimento = 0.0
    if len(nariz_pontos) >= 2:
        arr = np.stack(nariz_pontos)
        movimento = float(np.linalg.norm(arr.max(axis=0) - arr.min(axis=0)))

    rostos_validos = sum(1 for e in ear_serie if e > 0)
    if rostos_validos < 2:
        return LivenessResult(
            False,
            piscadas,
            movimento,
            "Não foi possível localizar o rosto em frames suficientes.",
        )

    if piscadas >= 1:
        return LivenessResult(True, piscadas, movimento)

    if movimento >= HEAD_MOVEMENT_THRESHOLD:
        return LivenessResult(True, piscadas, movimento)

    return LivenessResult(
        False,
        piscadas,
        movimento,
        "Liveness falhou: nenhuma piscada ou movimento de cabeça detectado.",
    )
