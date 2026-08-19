from __future__ import annotations

from django.conf import settings
from django.db import models


class DriveProfile(models.Model):
    """
    Referências ao estado do usuário no Google Drive: id da pasta
    "buscaagil_upload" e id do catalog.json dentro dela. Evita ter que
    procurar esses IDs por nome no Drive a cada requisição.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="drive_profile"
    )
    folder_id = models.CharField(max_length=128)
    catalog_file_id = models.CharField(max_length=128, blank=True, default="")
    storage_used_bytes = models.BigIntegerField(null=True, blank=True)
    storage_total_bytes = models.BigIntegerField(null=True, blank=True)
    last_synced_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"DriveProfile({self.user_id})"
