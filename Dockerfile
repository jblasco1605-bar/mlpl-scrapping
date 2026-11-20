# Imagen para Hugging Face Spaces (Space de tipo Docker).
# Tambien sirve para cualquier otro alojamiento que acepte Docker.
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Hugging Face ejecuta el contenedor con un usuario sin permisos de root:
# la app necesita poder escribir en datos/ (guarda las ofertas de cada busqueda)
RUN chmod -R 777 /app
ENV HOME=/app

EXPOSE 8501

CMD ["streamlit", "run", "main.py", \
     "--server.port=8501", "--server.address=0.0.0.0", "--server.headless=true", \
     "--server.enableCORS=false", "--server.enableXsrfProtection=false"]
