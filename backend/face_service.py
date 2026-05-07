import base64
import os
from typing import List, Optional, Tuple

import cv2
import numpy as np
from deepface import DeepFace

DEEPFACE_MODEL = os.environ.get("DEEPFACE_MODEL", "ArcFace")
DEEPFACE_DETECTOR = os.environ.get("DEEPFACE_DETECTOR", "retinaface")


class FaceError(Exception):
    pass


class NoFaceFound(FaceError):
    pass


class MultipleFacesFound(FaceError):
    pass


def base64_to_image(b64: str) -> np.ndarray:
    if "," in b64:
        b64 = b64.split(",", 1)[1]
    try:
        raw = base64.b64decode(b64)
    except Exception as exc:
        raise FaceError(f"Base64 inválido: {exc}") from exc
    arr = np.frombuffer(raw, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise FaceError("Não foi possível decodificar a imagem.")
    return img


def image_to_bytes(img: np.ndarray, ext: str = ".jpg") -> bytes:
    success, buf = cv2.imencode(ext, img)
    if not success:
        raise FaceError("Falha ao codificar imagem.")
    return buf.tobytes()


def _detectar_rostos(img: np.ndarray):
    """Retorna lista de faces detectadas via DeepFace.extract_faces."""
    try:
        faces = DeepFace.extract_faces(
            img_path=img,
            detector_backend=DEEPFACE_DETECTOR,
            enforce_detection=False,
            align=True,
        )
    except Exception as exc:
        raise FaceError(f"Erro ao detectar rosto: {exc}") from exc

    return [f for f in faces if f.get("confidence", 0) > 0.5]


def _detectar_rostos_com_fallback(img: np.ndarray):
    """Tenta com o detector configurado; em caso de erro usa opencv como fallback."""
    try:
        faces = _detectar_rostos(img)
        if faces:
            return faces
    except FaceError:
        pass

    try:
        faces = DeepFace.extract_faces(
            img_path=img,
            detector_backend="opencv",
            enforce_detection=False,
            align=True,
        )
        return [f for f in faces if f.get("confidence", 0) > 0.5]
    except Exception as exc:
        raise FaceError(f"Erro ao detectar rosto (fallback): {exc}") from exc


def extrair_encoding(img: np.ndarray) -> np.ndarray:
    """Extrai o encoding ArcFace do rosto presente na imagem.

    Garante que exista exatamente um rosto.
    """
    faces = _detectar_rostos_com_fallback(img)

    if len(faces) == 0:
        raise NoFaceFound("Nenhum rosto detectado na imagem.")
    if len(faces) > 1:
        raise MultipleFacesFound("Mais de um rosto detectado na imagem.")

    try:
        representation = DeepFace.represent(
            img_path=img,
            model_name=DEEPFACE_MODEL,
            detector_backend=DEEPFACE_DETECTOR,
            enforce_detection=False,
            align=True,
        )
    except Exception:
        representation = DeepFace.represent(
            img_path=img,
            model_name=DEEPFACE_MODEL,
            detector_backend="opencv",
            enforce_detection=False,
            align=True,
        )

    if not representation:
        raise NoFaceFound("Não foi possível extrair encoding do rosto.")

    embedding = representation[0].get("embedding")
    if embedding is None:
        raise NoFaceFound("Encoding não retornado pelo modelo.")

    return np.asarray(embedding, dtype=np.float32)


def similaridade_cosseno(a: np.ndarray, b: np.ndarray) -> float:
    a = a.astype(np.float32)
    b = b.astype(np.float32)
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


def melhor_correspondencia(
    encoding: np.ndarray, base: List[Tuple[str, np.ndarray]]
) -> Tuple[Optional[str], float]:
    melhor_nome: Optional[str] = None
    melhor_score = -1.0
    for nome, vetor in base:
        score = similaridade_cosseno(encoding, vetor)
        if score > melhor_score:
            melhor_score = score
            melhor_nome = nome
    return melhor_nome, max(0.0, melhor_score)
