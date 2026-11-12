# removerfundo_final_corrigido2.py
import os
import sys
import re
import argparse
import traceback
import getpass
from pathlib import Path
from PIL import Image, ImageOps
import numpy as np
import torch
from torchvision.transforms import functional as F
from transformers import AutoModelForImageSegmentation

# --------------------------
# suporte heif
# --------------------------
try:
    import pillow_heif
    pillow_heif.register_heif_opener()
except Exception:
    pass

# ---------------------------
# Config
# ---------------------------
MODEL_INPUT_SIZE = (1024, 1024)  # tamanho de entrada do modelo
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
ERROS_LOG = "errors.log"
IMAGE_EXTS = {'.png', '.jpg', '.jpeg', '.bmp', '.tiff', '.webp', '.heic', '.heif', '.jfif'}
OUTPUT_ROOT_NAME = "Fundo Removido"

# ---------------------------
# Argumentos CLI
# ---------------------------
parser = argparse.ArgumentParser(description="Remover fundo com BRIA RMBG-2.0")
parser.add_argument("--force", action="store_true", help="Forçar reprocessamento mesmo de arquivos já processados")
parser.add_argument("--base", type=str, default=None, help="Pasta base para procurar imagens (override)")
parser.add_argument("--hf-model", type=str, default="briaai/RMBG-2.0", help="Model ID no Hugging Face (ex.: briaai/RMBG-2.0)")
parser.add_argument("--hf-token", type=str, default=None, help="Token do Hugging Face (ou use HF_TOKEN/HUGGINGFACE_TOKEN)")
parser.add_argument("--save-hf-token", action="store_true", help="Salvar token no Windows Credential Manager (requer pacote 'keyring')")
parser.add_argument("--no-save-hf-token", action="store_true", help="Não salvar token no Windows Credential Manager")
args = parser.parse_args()
FORCE_REPROCESS = args.force
PASTA_BASE_FORCADA = args.base
HF_MODEL_ID = args.hf_model

# ---------------------------
# Hugging Face token (prefer env var)
# ---------------------------
def get_huggingface_token():
    token = args.hf_token or os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_TOKEN")
    if token:
        if args.save_hf_token and (not args.no_save_hf_token):
            try:
                import keyring  # type: ignore

                keyring.set_password("huggingface", "token", token)
                print("✅ Token salvo no Windows Credential Manager (service='huggingface', user='token').")
            except Exception as e:
                print(f"⚠️ Não foi possível salvar o token via keyring: {e}")
        return token

    try:
        import keyring  # type: ignore

        token = keyring.get_password("huggingface", "token")
        if token:
            return token
    except Exception:
        token = None

    token = getpass.getpass("Hugging Face token (input oculto): ").strip()
    if not token:
        return None

    if not args.no_save_hf_token:
        try:
            import keyring  # type: ignore

            keyring.set_password("huggingface", "token", token)
            print("✅ Token salvo no Windows Credential Manager (service='huggingface', user='token').")
        except Exception as e:
            print(f"⚠️ Não foi possível salvar o token via keyring: {e}")

    return token

HUGGINGFACE_TOKEN = get_huggingface_token()

# ---------------------------
# Carregar modelo
# ---------------------------
print(f"🔁 Carregando modelo {HF_MODEL_ID}...")
try:
    # Evita inicialização em 'meta' (low_cpu_mem_usage), que quebra alguns modelos com código remoto
    # (ex.: uso de `.item()` durante o __init__).
    kwargs = {"trust_remote_code": True, "low_cpu_mem_usage": False}
    if HUGGINGFACE_TOKEN:
        kwargs["token"] = HUGGINGFACE_TOKEN
    model = AutoModelForImageSegmentation.from_pretrained(HF_MODEL_ID, **kwargs)
    model.to(DEVICE)
    model.eval()
    print(f"✅ Modelo carregado em {DEVICE}")
except Exception as e:
    msg = str(e)
    print(f"❌ Erro ao carregar o modelo {HF_MODEL_ID}:")
    print(e)
    if ("gated repo" in msg.lower()) or ("401" in msg) or ("restricted" in msg.lower()):
        print("\nEsse modelo parece ser restrito (gated). Para resolver:")
        print("1) Peça/aceite acesso na página do modelo no Hugging Face.")
        print("2) Crie um token 'Read' em https://huggingface.co/settings/tokens")
        print("3) Informe o token por variável de ambiente, argumento, ou salve via keyring:")
        print("   PowerShell (sessão atual):  $env:HF_TOKEN='hf_...'; py -3.12 removerfundo6.0.py")
        print("   Ou:                         py -3.12 removerfundo6.0.py --hf-token hf_...")
        print("   Ou (1x, salvar):            py -3.12 -m pip install -U keyring")
        print("                              py -3.12 removerfundo6.0.py --save-hf-token")
    sys.exit(1)

# ---------------------------
# Helpers para path
# ---------------------------
def is_windows():
    return os.name == 'nt'

def to_extended_path(p: Path) -> Path:
    s = str(p)
    if not is_windows():
        return p
    if s.startswith('\\\\?\\'):
        return Path(s)
    if s.startswith('\\\\'):
        without = s.lstrip('\\')
        return Path('\\\\?\\UNC\\' + without)
    return Path('\\\\?\\' + s)

def probe_path(path: Path):
    try:
        exists = path.exists()
    except Exception as e:
        return False, f"exists() levantou: {e}"
    if not exists:
        return False, "exists() -> False"
    try:
        listing = os.listdir(str(path))
        return True, f"exists True; os.listdir() retornou {len(listing)} entradas"
    except Exception as e:
        return False, f"os.listdir() falhou com: {e}"

def is_image_file(path: Path):
    return path.suffix.lower() in IMAGE_EXTS

def normalize_name_for_compare(s: str):
    """Normaliza nomes: lowercase, strip, remove trailing _<num> sufixos."""
    s = s.strip().lower()
    s = re.sub(r'(_\d+)$', '', s)
    return s

# ---------------------------
# Remoção de fundo
# ---------------------------
def remove_bg_rmbg2_from_pil(imagem_pil):
    # Corrigir orientação EXIF
    imagem_pil = ImageOps.exif_transpose(imagem_pil)
    image_rgb = imagem_pil.convert("RGB")
    orig_w, orig_h = image_rgb.size

    # Redimensionar mantendo proporção e adicionar padding para 1024x1024
    target_w, target_h = MODEL_INPUT_SIZE
    scale = min(target_w/orig_w, target_h/orig_h)
    new_size = (int(orig_w*scale), int(orig_h*scale))
    resized_rgb = image_rgb.resize(new_size, Image.BILINEAR)

    # Criar imagem 1024x1024 com padding preto
    padded_rgb = Image.new("RGB", MODEL_INPUT_SIZE, (0,0,0))
    top_left = ((target_w - new_size[0])//2, (target_h - new_size[1])//2)
    padded_rgb.paste(resized_rgb, top_left)

    # Transformar para tensor e normalizar
    input_tensor = F.to_tensor(padded_rgb)
    input_tensor = F.normalize(input_tensor, [0.485,0.456,0.406], [0.229,0.224,0.225]).unsqueeze(0).to(DEVICE)

    # Inferência
    with torch.no_grad():
        outputs = model(input_tensor)
        preds = outputs[-1].sigmoid().cpu()

    pred = preds[0]
    if pred.ndim == 3 and pred.shape[0] == 1:
        pred = pred.squeeze(0)

    # Máscara: cortar padding e redimensionar para tamanho original
    mask_np = (pred.numpy() * 255.0).clip(0,255).astype(np.uint8)
    mask_pil = Image.fromarray(mask_np, mode='L')
    left, top = top_left
    mask_cropped = mask_pil.crop((left, top, left+new_size[0], top+new_size[1]))
    mask_resized = mask_cropped.resize((orig_w, orig_h), resample=Image.BILINEAR)

    # Aplicar alpha
    image_rgba = image_rgb.copy()
    image_rgba.putalpha(mask_resized)
    return image_rgba

# ---------------------------
# Coletar processados
# ---------------------------
def coletar_processados(pasta_saida_root: Path):
    processados = set()
    if not pasta_saida_root.exists():
        return processados
    try:
        for p in pasta_saida_root.rglob('*'):
            if not p.is_file():
                continue
            stem = p.stem
            if stem.startswith("sem_fundo_"):
                original = stem[len("sem_fundo_"):]
                original_norm = normalize_name_for_compare(original)
                if original_norm:
                    processados.add(original_norm)
    except Exception:
        try:
            for p in pasta_saida_root.iterdir():
                if p.is_file() and p.stem.startswith("sem_fundo_"):
                    original = p.stem[len("sem_fundo_"):]
                    processados.add(normalize_name_for_compare(original))
        except Exception:
            pass
    return processados

# ---------------------------
# Processamento individual (salva)
# ---------------------------
def processar_imagem_salvar(caminho_imagem: Path, pasta_saida: Path):
    nome_saida = f"sem_fundo_{caminho_imagem.stem}.png"
    caminho_saida_ext = to_extended_path(pasta_saida / nome_saida)
    try:
        imagem_original = Image.open(str(to_extended_path(caminho_imagem)))
        imagem_original = ImageOps.exif_transpose(imagem_original)
        imagem_resultante = remove_bg_rmbg2_from_pil(imagem_original)
        pasta_saida.mkdir(parents=True, exist_ok=True)
        imagem_resultante.save(str(caminho_saida_ext), 'PNG')
        print(f"✔ {caminho_imagem.name} → {caminho_saida_ext}")
        return True
    except Exception as e:
        with open(ERROS_LOG, "a", encoding="utf-8") as f:
            f.write(f"Erro ao processar: {caminho_imagem}\n{traceback.format_exc()}\n\n")
        print(f"❌ Erro ao processar {caminho_imagem}: {e}")
        return False

# ---------------------------
# Coleta de imagens
# ---------------------------
def coletar_imagens_exceto_saida(pasta_raiz: Path, output_dir_name: str):
    imagens = []
    try:
        for raiz, dirs, arquivos in os.walk(str(pasta_raiz)):
            dirs[:] = [d for d in dirs if d.lower() != output_dir_name.lower()]
            for a in arquivos:
                pa = Path(raiz) / a
                if is_image_file(pa):
                    imagens.append(pa)
    except Exception:
        try:
            for p in pasta_raiz.rglob('*'):
                if p.is_file() and is_image_file(p) and OUTPUT_ROOT_NAME not in [part for part in p.parts]:
                    imagens.append(p)
        except Exception:
            pass
    return imagens

# ---------------------------
# Processamento em pastas
# ---------------------------
def remover_fundo_em_pastas(pasta_raiz: Path, force: bool = False):
    ok, diag = probe_path(pasta_raiz)
    print(f"\n🔎 Diagnóstico da pasta: {pasta_raiz}\n  -> {diag}\n")
    if not ok:
        return

    pasta_exec = Path.cwd()
    pasta_saida_root = pasta_exec / OUTPUT_ROOT_NAME
    processados = coletar_processados(pasta_saida_root)
    print(f"ℹ️ Encontrados {len(processados)} arquivos já processados (na pasta '{OUTPUT_ROOT_NAME}').")

    imagens = coletar_imagens_exceto_saida(pasta_raiz, OUTPUT_ROOT_NAME)
    if not imagens:
        print("⚠ Nenhuma imagem encontrada (fora da pasta de saída).")
        return

    imagens.sort()
    total = len(imagens)
    processed = 0
    failed = 0

    try:
        for idx, img_path in enumerate(imagens, start=1):
            nome_original_norm = normalize_name_for_compare(img_path.stem)
            if not force and nome_original_norm in processados:
                print(f"↪ Ignorado (já processado): {img_path.name}")
                continue

            try:
                rel = img_path.relative_to(pasta_raiz)
                rel_parent = rel.parent
            except Exception:
                try:
                    rel_str = os.path.relpath(str(img_path), str(pasta_raiz))
                    rel_parent = Path(rel_str).parent
                except Exception:
                    rel_parent = Path('.')

            pasta_saida = pasta_exec / OUTPUT_ROOT_NAME / rel_parent
            caminho_saida_ext = to_extended_path(pasta_saida / f"sem_fundo_{img_path.stem}.png")
            try:
                if not force and caminho_saida_ext.exists():
                    processados.add(nome_original_norm)
                    print(f"↪ Ignorado (saída já existe): {caminho_saida_ext.name}")
                    continue
            except Exception:
                pass

            print(f"\n➡️ [{idx}/{total}] Processando: {img_path.name}")
            ok = processar_imagem_salvar(img_path, pasta_saida)
            if ok:
                processed += 1
                processados.add(nome_original_norm)
            else:
                failed += 1

    except KeyboardInterrupt:
        print("\n⏹ Interrompido pelo usuário (KeyboardInterrupt). Saindo...")

    print(f"\n✅ Concluído. Processadas: {processed}. Falhas: {failed}. (Ver {ERROS_LOG} para detalhes)")

# ---------------------------
# Execução principal
# ---------------------------
if __name__ == "__main__":
    if PASTA_BASE_FORCADA:
        base_candidate = Path(PASTA_BASE_FORCADA)
        if base_candidate.exists():
            pasta_base = base_candidate
        else:
            print(f"⚠ A pasta passada por --base não existe: {PASTA_BASE_FORCADA}. Usando diretório actual.")
            pasta_base = Path.cwd()
    else:
        pasta_base = Path.cwd()

    print(f"\n📁 Diretório base: {pasta_base}\n")
    remover_fundo_em_pastas(pasta_base, force=FORCE_REPROCESS)

    try:
        if sys.stdin and sys.stdin.isatty():
            input("\nPressione Enter para sair...")
    except Exception:
        pass
