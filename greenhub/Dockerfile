FROM python:3

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY fonts/ fonts/
COPY snippets/ snippets/
COPY greenhub/ greenhub/

ENV PORT=80
EXPOSE 80

CMD ["python", "/app/greenhub/webapp.py"]
