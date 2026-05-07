import logging
import os
import re
from datetime import datetime
from typing import List, Optional

import cv2
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

import database
import face_service
from liveness_service import detectar_liveness

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("facial-auth")

SIMILARITY_THRESHOLD = float(os.environ.get("SIMILARITY_THRESHOLD", "0.70"))
AUDIT_FOLDER = os.environ.get("AUDIT_FOLDER", "/app/auditoria")
FACES_FOLDER = os.environ.get("FACES_FOLDER", "/app/rostos_cadastrados")

os.makedirs(AUDIT_FOLDER, exist_ok=True)
os.makedirs(FACES_FOLDER, exist_ok=True)

app = FastAPI(title="Facial Auth API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _startup() -> None:
    database.init_db()
    logger.info("Banco inicializado. Limiar de similaridade: %.2f", SIMILARITY_THRESHOLD)
    logger.info(
        "Modelo: %s | Detector: %s",
        face_service.DEEPFACE_MODEL,
        face_service.DEEPFACE_DETECTOR,
    )


class CadastrarRequest(BaseModel):
    nome: str = Field(..., min_length=1, max_length=100)
    foto: str = Field(..., description="Imagem em base64 (com ou sem prefixo data URL)")


class CadastrarResponse(BaseModel):
    sucesso: bool
    nome: str
    mensagem: str


class VerificarRequest(BaseModel):
    frames: List[str] = Field(
        ...,
        min_length=1,
        description="Lista de frames base64 capturados durante o desafio de piscar",
    )


class VerificarResponse(BaseModel):
    acesso: bool
    similaridade: float
    usuario: Optional[str] = None
    mensagem: str
    piscadas: int = 0


def _slugify(nome: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", nome.strip()).strip("_").lower()
    return slug or "usuario"


def _timestamp() -> str:
    return datetime.utcnow().strftime("%Y%m%dT%H%M%S%f")


@app.get("/")
def root() -> dict:
    return {
        "service": "facial-auth",
        "modelo": face_service.DEEPFACE_MODEL,
        "detector": face_service.DEEPFACE_DETECTOR,
        "threshold": SIMILARITY_THRESHOLD,
    }


@app.get("/usuarios")
def usuarios() -> dict:
    lista = database.listar_usuarios()
    return {"total": len(lista), "usuarios": lista}


@app.post("/cadastrar", response_model=CadastrarResponse)
def cadastrar(req: CadastrarRequest) -> CadastrarResponse:
    inicio = datetime.utcnow().isoformat()
    logger.info("[%s] Cadastro solicitado para nome='%s'", inicio, req.nome)

    try:
        img = face_service.base64_to_image(req.foto)
    except face_service.FaceError as exc:
        logger.warning("Cadastro falhou (decodificação): %s", exc)
        raise HTTPException(status_code=400, detail=str(exc))

    try:
        encoding = face_service.extrair_encoding(img)
    except face_service.NoFaceFound as exc:
        logger.warning("Cadastro falhou (nenhum rosto): %s", exc)
        raise HTTPException(status_code=422, detail=str(exc))
    except face_service.MultipleFacesFound as exc:
        logger.warning("Cadastro falhou (múltiplos rostos): %s", exc)
        raise HTTPException(status_code=422, detail=str(exc))
    except face_service.FaceError as exc:
        logger.error("Cadastro falhou (DeepFace): %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))

    slug = _slugify(req.nome)
    img_path = os.path.join(FACES_FOLDER, f"{slug}_{_timestamp()}.jpg")
    cv2.imwrite(img_path, img)

    database.salvar_usuario(req.nome, encoding, img_path)
    logger.info("Cadastro concluído para '%s' em %s", req.nome, img_path)

    return CadastrarResponse(
        sucesso=True,
        nome=req.nome,
        mensagem="Usuário cadastrado com sucesso.",
    )


@app.post("/verificar", response_model=VerificarResponse)
def verificar(req: VerificarRequest) -> VerificarResponse:
    inicio = datetime.utcnow()
    logger.info(
        "[%s] Verificação solicitada com %d frames", inicio.isoformat(), len(req.frames)
    )

    if not req.frames:
        raise HTTPException(status_code=400, detail="Nenhum frame recebido.")

    try:
        imagens = [face_service.base64_to_image(f) for f in req.frames]
    except face_service.FaceError as exc:
        logger.warning("Verificação falhou (decodificação): %s", exc)
        raise HTTPException(status_code=400, detail=str(exc))

    audit_name = f"verificacao_{_timestamp()}.jpg"
    audit_path = os.path.join(AUDIT_FOLDER, audit_name)
    cv2.imwrite(audit_path, imagens[-1])
    logger.info("Imagem de auditoria salva: %s", audit_path)

    liveness = detectar_liveness(imagens)
    logger.info(
        "Liveness: passou=%s piscadas=%d movimento=%.4f motivo=%s",
        liveness.passou,
        liveness.piscadas,
        liveness.movimento_cabeca,
        liveness.motivo,
    )

    if not liveness.passou:
        return VerificarResponse(
            acesso=False,
            similaridade=0.0,
            usuario=None,
            mensagem=liveness.motivo or "Liveness falhou.",
            piscadas=liveness.piscadas,
        )

    try:
        encoding = face_service.extrair_encoding(imagens[-1])
    except face_service.NoFaceFound:
        ultimo_erro: Optional[Exception] = None
        encoding = None
        for img in reversed(imagens[:-1]):
            try:
                encoding = face_service.extrair_encoding(img)
                break
            except face_service.FaceError as exc:
                ultimo_erro = exc
                continue
        if encoding is None:
            mensagem = (
                str(ultimo_erro)
                if ultimo_erro
                else "Nenhum rosto válido encontrado nos frames."
            )
            logger.warning("Verificação falhou (sem rosto): %s", mensagem)
            return VerificarResponse(
                acesso=False,
                similaridade=0.0,
                usuario=None,
                mensagem=mensagem,
                piscadas=liveness.piscadas,
            )
    except face_service.MultipleFacesFound as exc:
        logger.warning("Verificação falhou (múltiplos rostos): %s", exc)
        return VerificarResponse(
            acesso=False,
            similaridade=0.0,
            usuario=None,
            mensagem=str(exc),
            piscadas=liveness.piscadas,
        )
    except face_service.FaceError as exc:
        logger.error("Verificação falhou (DeepFace): %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))

    base = database.carregar_encodings()
    if not base:
        logger.info("Nenhum usuário cadastrado para comparar.")
        return VerificarResponse(
            acesso=False,
            similaridade=0.0,
            usuario=None,
            mensagem="Nenhum usuário cadastrado no sistema.",
            piscadas=liveness.piscadas,
        )

    nome, score = face_service.melhor_correspondencia(encoding, base)
    acesso = score >= SIMILARITY_THRESHOLD

    duracao_ms = (datetime.utcnow() - inicio).total_seconds() * 1000
    logger.info(
        "Resultado: acesso=%s usuario=%s similaridade=%.4f (threshold=%.2f) tempo=%.0fms",
        acesso,
        nome,
        score,
        SIMILARITY_THRESHOLD,
        duracao_ms,
    )

    if acesso:
        mensagem = f"Acesso liberado para {nome}."
    else:
        mensagem = (
            f"Acesso negado. Similaridade {score:.2%} abaixo do limite "
            f"{SIMILARITY_THRESHOLD:.2%}."
        )

    return VerificarResponse(
        acesso=acesso,
        similaridade=score,
        usuario=nome if acesso else None,
        mensagem=mensagem,
        piscadas=liveness.piscadas,
    )
