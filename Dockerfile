# Imagen Docker de la app (se usa para desplegar en Render).
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Por si el alojamiento ejecuta el contenedor sin permisos de root:
# la app necesita poder escribir en datos/ (guarda las ofertas de cada busqueda)
RUN chmod -R 777 /app
ENV HOME=/app

# Render indica el puerto en la variable PORT; si no existe, se usa el 8501
EXPOSE 8501

CMD streamlit run main.py --server.port=${PORT:-8501} --server.address=0.0.0.0 \
    --server.headless=true --server.enableCORS=false --server.enableXsrfProtection=false
