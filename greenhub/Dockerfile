FROM python:3

WORKDIR /app

COPY glyphs.txt ./
COPY snippets/ snippets/
COPY greenhub/ greenhub/

ENTRYPOINT ["bash", "/app/greenhub/entrypoint.sh"]
