# FaceGate

> Autenticação por reconhecimento facial com **liveness detection** (piscar) — 100% local, em Docker.

![status](https://img.shields.io/badge/status-experimental-orange)
![docker](https://img.shields.io/badge/docker--compose-ready-blue)
![python](https://img.shields.io/badge/python-3.10-blue)
![license](https://img.shields.io/badge/license-MIT-green)

Aplicação completa de reconhecimento facial com **liveness detection** rodando 100% localmente via **Docker Compose**. Para subir basta `docker compose up --build`.

- **Backend:** Python 3.10 + FastAPI
- **Reconhecimento facial:** DeepFace com **ArcFace** (modelo) e **RetinaFace** (detector)
- **Liveness:** MediaPipe (FaceMesh) — detecta piscadas e movimento de cabeça
- **Frontend:** HTML + JavaScript puro, servido por **Nginx**
- **Banco:** SQLite (encodings persistidos em volume Docker)

---

## Pré-requisitos

- [Docker](https://www.docker.com/get-started/) (24+)
- [Docker Compose](https://docs.docker.com/compose/install/) (v2+)

> Observação: a primeira build baixa pesos do ArcFace/RetinaFace (~250 MB).
> Os pesos ficam cacheados em um volume Docker para builds subsequentes.

---

## Configuração

```bash
git clone <repo-url>
cd facial-auth
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
docker-compose up --build
```

Para rodar em background:

```bash
docker-compose up --build -d
```

Para parar:

```bash
docker-compose down
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
facial-auth/
├── backend/
│   ├── main.py              # Endpoints FastAPI
│   ├── database.py          # SQLite (usuários e encodings)
│   ├── face_service.py      # DeepFace (ArcFace + RetinaFace)
│   ├── liveness_service.py  # MediaPipe (FaceMesh + EAR)
│   ├── requirements.txt
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

## Detalhes técnicos

- **Liveness:** o backend recebe uma sequência de frames e calcula o **EAR (Eye Aspect Ratio)** quadro a quadro com o FaceMesh do MediaPipe. Conta como piscada quando o EAR cai abaixo de `0.21` e volta a subir acima de `0.25`. Como fallback, também aceita movimento de cabeça relevante (variação de posição do nariz).
- **Reconhecimento:** o backend extrai o embedding com **ArcFace** (DeepFace) usando o detector **RetinaFace**. Em caso de falha, há fallback automático para o detector **OpenCV** (configurado em `face_service.py`).
- **Threshold:** comparação por **similaridade de cosseno** entre o embedding capturado e os embeddings cadastrados; libera acesso se `similaridade ≥ SIMILARITY_THRESHOLD`.
- **Persistência:** SQLite em volume nomeado (`sqlite_data`); pesos do DeepFace cacheados em volume (`deepface_weights`); pastas `auditoria/` e `rostos_cadastrados/` mapeadas como bind mounts.
- **Logs:** cada tentativa imprime no terminal um log com timestamp, contendo similaridade, threshold, piscadas e duração.

---

## Solução de problemas

- **A câmera não liga no navegador:** o `getUserMedia` exige HTTPS ou `localhost`. Use `http://localhost:3000` (não `127.0.0.1` em alguns navegadores).
- **A primeira verificação demora alguns segundos:** os pesos do ArcFace/RetinaFace são baixados e carregados na memória apenas na primeira execução. Depois ficam em cache.
- **`Liveness falhou`:** garanta boa iluminação e pisque com naturalidade durante o período de captura.
- **`Mais de um rosto detectado`:** mantenha apenas uma pessoa no enquadramento.

---

## Licença

[MIT](LICENSE) · projeto de estudo, sem garantias. As fotos de auditoria e os encodings ficam apenas no seu volume Docker local.

