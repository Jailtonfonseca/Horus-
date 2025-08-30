import datetime
import hashlib
import logging
import os
import tempfile
from typing import Optional, Dict, Any

def get_file_content(path: str) -> Optional[str]:
    """Lê o conteúdo de um arquivo."""
    if not os.path.exists(path):
        return None
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return f.read()
    except IOError as e:
        logging.error(f"Erro ao ler o arquivo '{path}': {e}")
        return None

def setup_workspace(workspace_path: str) -> None:
    """Cria o diretório de workspace e subdiretórios necessários."""
    try:
        os.makedirs(os.path.join(workspace_path, "backups"), exist_ok=True)
        logging.info(f"Workspace '{workspace_path}' configurado com sucesso.")
    except OSError as e:
        logging.error(f"Erro ao criar workspace em '{workspace_path}': {e}")
        raise

def create_backup(workspace: str, target_path: str) -> None:
    """Cria um backup versionado de um arquivo."""
    if not os.path.exists(target_path):
        return

    content = get_file_content(target_path)
    if content is None:
        return

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    content_hash = hashlib.sha256(content.encode('utf-8')).hexdigest()[:8]
    backup_dir = os.path.join(workspace, "backups")
    base_name = os.path.basename(target_path).replace('.', '_')
    backup_filename = f"{base_name}__{timestamp}__{content_hash}.bak"
    backup_path = os.path.join(backup_dir, backup_filename)

    try:
        with open(backup_path, 'w', encoding='utf-8') as f:
            f.write(content)
        logging.info(f"Backup de '{target_path}' criado em '{backup_path}'")
    except IOError as e:
        logging.warning(f"Não foi possível criar backup para '{target_path}': {e}")

def apply_changes(workspace: str, change: Dict[str, Any], dry_run: bool) -> bool:
    """Aplica as alterações de arquivo de forma atômica."""
    action = change["action"]
    if action == "noop":
        logging.info("Ação 'noop' recebida. Nenhuma alteração de arquivo será feita.")
        return True

    target_path = os.path.join(workspace, change["target_path"])
    code_to_write = change["code"]

    abs_workspace = os.path.abspath(workspace)
    abs_target_path = os.path.abspath(target_path)

    if not abs_target_path.startswith(abs_workspace):
        logging.error(f"Tentativa de escrita fora do workspace detectada: '{target_path}'. Ação bloqueada.")
        return False

    logging.info(f"Aplicando ação '{action}' em '{target_path}'.")
    if dry_run:
        logging.info(f"[DRY RUN] Ação '{action}' em '{target_path}' não será executada.")
        return True

    create_backup(workspace, target_path)

    try:
        temp_fd, temp_path = tempfile.mkstemp(dir=workspace)

        with os.fdopen(temp_fd, 'w', encoding='utf-8') as temp_f:
            if action == "replace_file":
                temp_f.write(code_to_write)

            elif action == "append":
                original_content = get_file_content(target_path) or ""
                temp_f.write(original_content)
                temp_f.write("\n" + code_to_write)

            elif action == "replace_block":
                marker = change["marker"]
                start_marker = f"# >>> BEGIN:{marker}"
                end_marker = f"# >>> END:{marker}"

                original_content = get_file_content(target_path)
                if not original_content or start_marker not in original_content or end_marker not in original_content:
                    logging.error(f"Marcadores para '{marker}' não encontrados em '{target_path}'. Ação falhou.")
                    os.remove(temp_path)
                    return False

                pre_block = original_content.split(start_marker)[0]
                post_block = original_content.split(end_marker)[1]

                temp_f.write(pre_block)
                temp_f.write(start_marker + "\n")
                temp_f.write(code_to_write)
                temp_f.write("\n" + end_marker)
                temp_f.write(post_block)

        os.replace(temp_path, target_path)
        logging.info(f"Alteração em '{target_path}' aplicada com sucesso.")
        return True

    except Exception as e:
        logging.error(f"Erro ao aplicar alterações em '{target_path}': {e}")
        if 'temp_path' in locals() and os.path.exists(temp_path):
            os.remove(temp_path)
        return False

def update_instructions_file(path: str, message: str):
    """Adiciona uma mensagem ao arquivo de instruções."""
    try:
        with open(path, 'a', encoding='utf-8') as f:
            f.write(f"\n--- {datetime.datetime.now().isoformat()} ---\n")
            f.write(message + "\n")
    except IOError as e:
        logging.warning(f"Não foi possível atualizar o arquivo de instruções '{path}': {e}")
