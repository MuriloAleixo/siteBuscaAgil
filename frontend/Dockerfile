# Build context é a raiz do repo (ver docker-compose.yml: build.context: .,
# build.dockerfile: frontend/Dockerfile) — assim dá pra copiar tanto
# frontend/pages/ quanto static/ (que também é usado como referência solta
# fora do Docker, ex.: abrir um .html direto no navegador).
FROM nginx:alpine

COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY frontend/pages/ /usr/share/nginx/html/
COPY static/ /usr/share/nginx/html/static/
