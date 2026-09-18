# FaceGate

> Autenticação por reconhecimento facial com **liveness detection** — 100% local, em Docker.

![CI](https://github.com/WellCod/face-gate/actions/workflows/ci.yml/badge.svg)
![python](https://img.shields.io/badge/python-3.10-blue)
![docker](https://img.shields.io/badge/docker--compose-ready-blue)
![license](https://img.shields.io/badge/license-MIT-green)

---

## O problema

Reconhecimento facial sozinho não autentica ninguém: uma foto no celular passa.
O que separa uma prova de identidade de um filtro de rede social é a **detecção
de vivacidade** — provar que há uma pessoa ali, agora.

E há um segundo problema, menos discutido: rosto é **dado biométrico**. Serviço
de reconhecimento em nuvem significa mandar o rosto de alguém para um terceiro,
com tudo que isso implica de retenção, jurisdição e vazamento. O FaceGate não
manda: **nenhum frame sai da máquina**.

---

## Como funciona

**Vivacidade pelo piscar.** O backend recebe uma sequência de frames e calcula o
**EAR** (*Eye Aspect Ratio*) quadro a quadro, com o FaceMesh do MediaPipe. O EAR
é a razão entre a abertura vertical e a largura do olho — cai perto de zero com
o olho fechado e fica em torno de 0,3 com ele aberto.

Uma piscada é contada quando o EAR **cai abaixo de 0,21 e volta a subir acima de
0,25**. Os dois limites são diferentes de propósito: com um único corte, ruído
de landmark em volta do valor faria o contador disparar sozinho. A folga entre
eles é histerese, o mesmo princípio de um termostato.

Como alternativa, movimento relevante de cabeça também vale — variação relativa
da posição do nariz acima de `0.04`.

**Identidade por embedding.** O rosto vira um vetor com **ArcFace** (via
DeepFace), detectado por **RetinaFace**, com fallback automático para o detector
do OpenCV quando a detecção falha. A comparação com os rostos cadastrados é por
**similaridade de cosseno**, e o acesso é liberado quando ela fica acima de
`SIMILARITY_THRESHOLD`.

**Persistência.** Encodings em SQLite, num volume nomeado. Pesos do modelo
cacheados em outro volume, para a primeira execução não se repetir. As pastas
`auditoria/` e `rostos_cadastrados/` são bind mounts — ficam na sua máquina.

**Rastro.** Cada tentativa gera log com timestamp, similaridade obtida,
threshold aplicado, piscadas contadas e duração. Decisão de acesso sem registro
não é auditável.

---

## Stack

| | |
|---|---|
| **Backend** | Python 3.10 · FastAPI |
| **Reconhecimento** | DeepFace com ArcFace (modelo) e RetinaFace (detector) |
| **Vivacidade** | MediaPipe FaceMesh |
| **Frontend** | HTML e JavaScript sem framework, servido por Nginx |
| **Persistência** | SQLite em volume Docker |

---

## Testes

A suíte cobre o que é determinístico: o cálculo do EAR, os limites de
histerese, os casos degenerados e a ida e volta dos encodings pelo SQLite.

```bash
pip install -r backend/requirements-test.txt
cd backend && python -m pytest -q
```

O reconhecimento facial em si fica de fora: depende de pesos de ~250 MB
baixados em runtime, e um teste que baixa 250 MB não roda em CI de PR.

---

## Pré-requisitos

- [Docker](https://www.docker.com/get-started/) (24+)
- [Docker Compose](https://docs.docker.com/compose/install/) (v2+)

> Observação: a primeira build baixa pesos do ArcFace/RetinaFace (~250 MB).
> Os pesos ficam cacheados em um volume Docker para builds subsequentes.

---

## Configuração

```bash
git clone https://github.com/WellCod/face-gate.git
cd face-gate
cp .env.example .env   # opcional: o app sobe com defaults se não existir
```

Edite o `.env` se quiser ajustar o limiar ou o modelo.

### Variáveis disponíveis (`.env`)

| Variável                | Descrição                                                              | Default       |
|-------------------------|------------------------------------------------------------------------|---------------|
| `SIMILARITY_THRESHOLD`  | Similaridade mínima (cosseno) para liberar acesso (0.0 a 1.0)          | `0.70`        |
| `DEEPFACE_MODEL`        | Modelo de reconhecimento (ArcFace, Facenet512, VGG-Face, etc.)         | `ArcFace`     |
| `DEEPFACE_DETECTOR`     | Detector facial (retinaface, mtcnn, opencv, etc.)                      | `retinaface`  |
| `AUDIT_FOLDER`          | Pasta de auditoria das tentativas de verificação                       | `auditoria`   |
| `FACES_FOLDER`          | Pasta dos rostos cadastrados                                           | `rostos_cadastrados` |

---

## Subindo a aplicação

```bash
docker compose up --build
```

Para rodar em background:

```bash
docker compose up --build -d
```

Para parar:

```bash
docker compose down
```

---

## Acessos

- **Frontend (UI de teste):** http://localhost:3000
- **Backend (API):** http://localhost:8000
- **Documentação interativa (Swagger):** http://localhost:8000/docs

---

## Fluxo completo de teste

1. Abra **http://localhost:3000** no navegador (Chrome/Edge/Firefox).
2. Clique em **"Iniciar câmera"** e autorize o acesso à webcam.
3. **Cadastrar um rosto:**
   - Digite seu nome no campo "Nome do usuário".
   - Posicione bem o rosto na câmera.
   - Clique em **"Cadastrar rosto"**.
   - Aguarde a confirmação `Cadastro realizado.`
4. **Verificar acesso:**
   - Clique em **"Verificar acesso (piscar)"**.
   - Durante os ~3 segundos de captura, **pisque pelo menos uma vez**.
   - O sistema retorna o nome reconhecido e a similaridade.
5. Para listar todos os usuários, clique em **"Atualizar lista"** no painel direito.

> Cada tentativa de verificação salva uma imagem em `./auditoria/` com timestamp.
> Cada cadastro salva o rosto de referência em `./rostos_cadastrados/`.
> Os logs do backend (com timestamp por tentativa) aparecem no terminal onde o `docker-compose` está rodando.

---

## API · Endpoints

### `GET /`
Retorna metadados do serviço (modelo, detector, threshold).

### `GET /usuarios`
Lista os usuários cadastrados.

**Response:**
```json
{
  "total": 1,
  "usuarios": [
    {
      "id": 1,
      "nome": "Maria",
      "criado_em": "2026-04-30T14:00:00",
      "imagem_path": "/app/rostos_cadastrados/maria_20260430T140000.jpg"
    }
  ]
}
```

### `POST /cadastrar`
Cadastra um novo rosto (ou atualiza, se o nome já existir).

**Body:**
```json
{
  "nome": "Maria",
  "foto": "data:image/jpeg;base64,/9j/4AAQ..."
}
```

**Response (200):**
```json
{
  "sucesso": true,
  "nome": "Maria",
  "mensagem": "Usuário cadastrado com sucesso."
}
```

**Erros possíveis:**
- `400` — base64 inválido.
- `422` — nenhum rosto detectado **ou** múltiplos rostos detectados.

### `POST /verificar`
Executa **liveness** + **reconhecimento facial**.

**Body:**
```json
{
  "frames": [
    "data:image/jpeg;base64,...",
    "data:image/jpeg;base64,...",
    "..."
  ]
}
```

> Envie uma sequência de frames (mínimo 3) capturados durante o desafio de piscar.
> O frontend já faz isso automaticamente: captura por ~3,5 s a cada 180 ms.

**Response (200):**
```json
{
  "acesso": true,
  "similaridade": 0.8421,
  "usuario": "Maria",
  "mensagem": "Acesso liberado para Maria.",
  "piscadas": 1
}
```

**Possíveis cenários no campo `mensagem`:**
- `Acesso liberado para <nome>.` (similaridade ≥ threshold)
- `Acesso negado. Similaridade XX% abaixo do limite YY%.`
- `Liveness falhou: nenhuma piscada ou movimento de cabeça detectado.`
- `Não foi possível localizar o rosto em frames suficientes.`
- `Mais de um rosto detectado na imagem.`

---

## Estrutura

```
face-gate/
├── .github/workflows/
│   └── ci.yml               # testes + scan de segredos
├── backend/
│   ├── main.py              # Endpoints FastAPI
│   ├── database.py          # SQLite (usuários e encodings)
│   ├── face_service.py      # DeepFace (ArcFace + RetinaFace)
│   ├── liveness_service.py  # MediaPipe (FaceMesh + EAR)
│   ├── tests/               # EAR, histerese e persistência
│   ├── requirements.txt
│   ├── requirements-test.txt
│   ├── pytest.ini
│   └── Dockerfile
├── frontend/
│   ├── index.html           # UI com webcam (HTML + JS puro)
│   ├── nginx.conf
│   └── Dockerfile
├── rostos_cadastrados/      # Imagens de cadastro (volume)
├── auditoria/               # Imagens de cada verificação (volume)
├── docker-compose.yml
├── .env.example
└── README.md
```

---

## Solução de problemas

- **A câmera não liga no navegador:** o `getUserMedia` exige HTTPS ou `localhost`. Use `http://localhost:3000` (não `127.0.0.1` em alguns navegadores).
- **A primeira verificação demora alguns segundos:** os pesos do ArcFace/RetinaFace são baixados e carregados na memória apenas na primeira execução. Depois ficam em cache.
- **`Liveness falhou`:** garanta boa iluminação e pisque com naturalidade durante o período de captura.
- **`Mais de um rosto detectado`:** mantenha apenas uma pessoa no enquadramento.

---

## Licença

[MIT](LICENSE) · projeto de estudo, sem garantias. As fotos de auditoria e os encodings ficam apenas no seu volume Docker local.

