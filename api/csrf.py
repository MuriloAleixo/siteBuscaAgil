"""
api/csrf.py

Proteção CSRF (double-submit cookie), reaproveitando o mesmo esquema que já
existia com o Django: todo GET recebe um cookie "csrftoken" legível por JS
(não-HttpOnly); todo POST precisa mandar esse valor de volta no header
X-CSRFToken. Sem isso, qualquer outro site poderia forjar um POST
autenticado usando o cookie de sessão do usuário, sem ele nem perceber.

static/js/catalog-client.js::getCsrfToken() já lê exatamente esse cookie —
nenhuma mudança necessária no frontend.
"""

from __future__ import annotations

import secrets

from flask import Flask, g, jsonify, request

CSRF_COOKIE_NAME = "csrftoken"
CSRF_HEADER_NAME = "X-CSRFToken"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def init_csrf(app: Flask) -> None:
    @app.before_request
    def _check_csrf():
        g.new_csrf_token = None if request.cookies.get(CSRF_COOKIE_NAME) else secrets.token_urlsafe(32)

        if request.method in SAFE_METHODS:
            return None

        cookie_token = request.cookies.get(CSRF_COOKIE_NAME)
        header_token = request.headers.get(CSRF_HEADER_NAME, "")
        if not cookie_token or header_token != cookie_token:
            return jsonify({"success": False, "error": "Token CSRF ausente ou inválido."}), 403
        return None

    @app.after_request
    def _set_csrf_cookie(response):
        if g.get("new_csrf_token"):
            response.set_cookie(
                CSRF_COOKIE_NAME,
                g.new_csrf_token,
                httponly=False,
                samesite="Lax",
                secure=request.is_secure,
            )
        return response
