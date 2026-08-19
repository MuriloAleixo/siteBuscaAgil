"""
file_catalog.py

Módulo simples para catalogar arquivos (salvos em nuvem) em um índice JSON,
permitindo busca rápida por tag, categoria ou texto livre.

Uso básico:
    from file_catalog import FileCatalog

    catalog = FileCatalog("catalog.json")

    catalog.add_file(
        filename="contrato_locacao_jan2026.pdf",
        cloud_path="s3://meu-bucket/contratos/contrato_locacao_jan2026.pdf",
        category="contratos",
        tags=["locação", "juridico", "2026"],
        description="Contrato de locação assinado em jan/2026",
    )

    resultados = catalog.search(tags=["juridico"])
    resultados = catalog.search(category="contratos")
    resultados = catalog.search_text("locação")
"""

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path


class FileCatalog:
    def __init__(self, json_path: str):
        self.json_path = Path(json_path)
        self._data = self._load()

    # ---------- persistência ----------

    def _load(self) -> dict:
        default = {"files": {}, "tags_index": {}, "category_index": {}}
        if self.json_path.exists():
            with open(self.json_path, "r", encoding="utf-8") as f:
                raw = f.read().strip()
            if raw:
                data = json.loads(raw)
                # Garante as chaves mesmo se o arquivo estiver truncado/vazio
                # (`{}`) por causa de uma escrita interrompida no meio.
                for key, empty_value in default.items():
                    data.setdefault(key, empty_value)
                return data
        return default

    def _save(self):
        # grava em arquivo temporário e substitui, evita corromper o JSON
        # se o processo cair no meio da escrita
        tmp_path = self.json_path.with_suffix(".tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, self.json_path)

    # ---------- escrita ----------

    def add_file(
        self,
        filename: str,
        cloud_path: str = None,
        category: str = None,
        tags: list[str] = None,
        description: str = "",
        size_bytes: int = None,
        extra_metadata: dict = None,
        file_id: str = None,
    ) -> str:
        """
        Registra um arquivo no catálogo. Retorna o file_id gerado (ou o passado).

        Chame isso no momento em que você salva o arquivo na nuvem —
        depois de fazer o upload, passe o cloud_path (chave/URL retornada
        pelo provedor) e os metadados que você extraiu/definiu.
        """
        tags = [t.strip().lower() for t in (tags or [])]
        category = category.strip().lower() if category else None
        file_id = file_id or f"f_{uuid.uuid4().hex[:8]}"

        self._data["files"][file_id] = {
            "filename": filename,
            "cloud_path": cloud_path,
            "extension": Path(filename).suffix.lower(),
            "size_bytes": size_bytes,
            "category": category,
            "tags": tags,
            "description": description,
            "uploaded_at": datetime.now(timezone.utc).isoformat(),
            "extra_metadata": extra_metadata or {},
        }

        for tag in tags:
            self._data["tags_index"].setdefault(tag, [])
            if file_id not in self._data["tags_index"][tag]:
                self._data["tags_index"][tag].append(file_id)

        if category:
            self._data["category_index"].setdefault(category, [])
            if file_id not in self._data["category_index"][category]:
                self._data["category_index"][category].append(file_id)

        self._save()
        return file_id

    def remove_file(self, file_id: str):
        info = self._data["files"].pop(file_id, None)
        if not info:
            return
        for tag in info.get("tags", []):
            ids = self._data["tags_index"].get(tag, [])
            if file_id in ids:
                ids.remove(file_id)
            if not ids:
                self._data["tags_index"].pop(tag, None)
        category = info.get("category")
        if category:
            ids = self._data["category_index"].get(category, [])
            if file_id in ids:
                ids.remove(file_id)
            if not ids:
                self._data["category_index"].pop(category, None)
        self._save()

    def update_tags(self, file_id: str, tags: list[str]):
        """Substitui as tags de um arquivo já catalogado."""
        info = self._data["files"].get(file_id)
        if not info:
            raise KeyError(f"file_id não encontrado: {file_id}")
        # remove das entradas antigas
        for old_tag in info.get("tags", []):
            ids = self._data["tags_index"].get(old_tag, [])
            if file_id in ids:
                ids.remove(file_id)
        # adiciona nas novas
        new_tags = [t.strip().lower() for t in tags]
        info["tags"] = new_tags
        for tag in new_tags:
            self._data["tags_index"].setdefault(tag, [])
            if file_id not in self._data["tags_index"][tag]:
                self._data["tags_index"][tag].append(file_id)
        self._save()

    def update_cloud_path(self, file_id: str, cloud_path: str):
        """
        Atualiza o cloud_path de um arquivo já catalogado. Use isso depois
        que o upload real pro Google Drive terminar — a classificação
        acontece ANTES do upload, então no momento de catalogar o
        cloud_path ainda não existe.
        """
        info = self._data["files"].get(file_id)
        if not info:
            raise KeyError(f"file_id não encontrado: {file_id}")
        info["cloud_path"] = cloud_path
        self._save()

    # ---------- busca ----------

    def search(self, tags: list[str] = None, category: str = None, match_all: bool = True) -> list[dict]:
        """
        Busca por tags e/ou categoria.
        match_all=True  -> arquivo precisa ter TODAS as tags informadas
        match_all=False -> arquivo precisa ter PELO MENOS UMA das tags
        """
        candidate_ids = None

        if tags:
            tags = [t.strip().lower() for t in tags]
            sets = [set(self._data["tags_index"].get(t, [])) for t in tags]
            if match_all:
                candidate_ids = set.intersection(*sets) if sets else set()
            else:
                candidate_ids = set.union(*sets) if sets else set()

        if category:
            cat_ids = set(self._data["category_index"].get(category.strip().lower(), []))
            candidate_ids = cat_ids if candidate_ids is None else candidate_ids & cat_ids

        if candidate_ids is None:
            candidate_ids = set(self._data["files"].keys())

        return [
            {"file_id": fid, **self._data["files"][fid]}
            for fid in candidate_ids
        ]

    def search_text(self, query: str) -> list[dict]:
        """Busca livre por substring no nome, descrição, tags ou categoria."""
        q = query.strip().lower()
        results = []
        for fid, info in self._data["files"].items():
            haystack = " ".join([
                info.get("filename", ""),
                info.get("description", ""),
                info.get("category") or "",
                " ".join(info.get("tags", [])),
            ]).lower()
            if q in haystack:
                results.append({"file_id": fid, **info})
        return results

    def list_all(self) -> list[dict]:
        return [{"file_id": fid, **info} for fid, info in self._data["files"].items()]

    def list_tags(self) -> list[str]:
        return sorted(self._data["tags_index"].keys())

    def list_categories(self) -> list[str]:
        return sorted(self._data["category_index"].keys())
