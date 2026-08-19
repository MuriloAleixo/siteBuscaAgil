from __future__ import annotations

import json


def busca_agil_user(request):
    """Injeta `busca_agil_user_json` em todo template: um JSON com os dados
    do usuário logado (nome, e-mail, avatar do Google), consumido pelo
    static/js/auth.js pra alimentar getCurrentUser()/isLoggedIn() no
    front-end sem precisar de sessionStorage/mock."""
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return {"busca_agil_user_json": "null"}

    avatar = ""
    social_account = user.socialaccount_set.filter(provider="google").first()
    if social_account:
        avatar = social_account.extra_data.get("picture", "")

    drive_profile = getattr(user, "drive_profile", None)
    storage_used = drive_profile.storage_used_bytes if drive_profile else None
    storage_total = drive_profile.storage_total_bytes if drive_profile else None

    data = {
        "id": user.id,
        "name": user.get_full_name() or user.get_username(),
        "email": user.email,
        "avatar": avatar,
        "plan": "Google Drive",
        "joinedAt": user.date_joined.date().isoformat(),
        "storageUsed": round(storage_used / (1024 ** 3), 2) if storage_used else 0,
        # 15 GB é o padrão de contas Google pessoais gratuitas; fica como
        # fallback quando a API não devolve um limite (contas Workspace
        # ilimitadas, por exemplo).
        "storageTotal": round(storage_total / (1024 ** 3), 2) if storage_total else 15,
    }
    return {"busca_agil_user_json": json.dumps(data, ensure_ascii=False)}
