# Proyecto ATD

Cruce de datos de **salarios por tipo de trabajo** con **precios de alquiler por ciudad**, para ver en qué ciudades compensa más trabajar. Se priorizan datos **oficiales**.

## mlpl scrapping

```bash
pip3 install -r requirements.txt
python3 consola.py      # en la terminal (sin página web)
python3 main.py         # página web (abre el navegador)
```

`python3 consola.py` pide puesto y ciudad, muestra todo el resultado en la terminal y lo guarda en `resultado.json`. `python3 main.py` arranca Streamlit y abre el navegador (también funciona `streamlit run main.py`). En VS Code también se pueden lanzar con F5 (configuraciones de `.vscode/launch.json`).

Se escribe un puesto y una ciudad y todo el resultado sale en una sola consulta. La app busca ofertas en Ticjob y Tecnoempleo (requests + BeautifulSoup), se queda con las del puesto y la zona que publican salario, las pasa a neto mensual (`RETENCION` en `limpieza.py`) y las compara con el alquiler de SERPAVI y Numbeo y el salario del INE. Si una web falla, se usa el último CSV de esa fuente en `datos/` y se muestra un aviso. El resultado se puede descargar en JSON. `scrapers/tecnoempleo_selenium.py` es una versión de Tecnoempleo con Selenium que se ejecuta por separado.

En la nube (Streamlit Community Cloud): repositorio de GitHub → share.streamlit.io → *Create app* → archivo `main.py`. Instala lo de `requirements.txt` y usa el tema de `.streamlit/config.toml`. Allí no hay Chrome, así que Tecnoempleo funciona solo con requests (si falla, usa `datos/tecnoempleo.csv`).

- `consulta.py`: flujo de una consulta (scrapers → limpieza → cruce con SERPAVI, Numbeo e INE), sin interfaz.
- `consola.py`: versión de terminal (`input` / `print`).
- `main.py`: versión web (Streamlit). Usa la misma lógica de `consulta.py`.
- `limpieza.py`: `normalizar_ciudad`, `normalizar_ccaa`, `normalizar_puesto`, `parecido_puesto`, `parsear_salario`, `salario_neto_mensual`.

## Estructura

- `scrapers/` – un script por fuente.
- `datos/` – CSV resultantes (separador `;`, UTF-8).

## Fuentes

| Script | Fuente | Datos | Tipo |
|---|---|---|---|
| `ine_salarios.py` | INE, Encuesta Anual de Estructura Salarial (API REST) | Salario medio bruto 2024 por ocupación, sector y comunidad autónoma | Oficial |
| `numbeo_ciudades.py` | numbeo.com (HTML) | Alquiler, salario neto mensual, menú y abono transporte de 14 ciudades españolas | Estimaciones de usuarios, no oficial |
| `ticjob.py` | ticjob.es (HTML) | Ofertas IT por ciudad con salario cuando lo publican | Ofertas reales, no oficial |
| `tecnoempleo.py` | tecnoempleo.com (HTML, requests + BeautifulSoup) | Ofertas IT por puesto: título, empresa, ciudad, tecnologías y salario si lo publican | Ofertas reales, no oficial |
| `tecnoempleo_selenium.py` | tecnoempleo.com (Selenium) | Respaldo del anterior si la web bloquea a requests; usa el mismo código de BeautifulSoup | Ofertas reales, no oficial |
| `serpavi_alquiler.py` | Ministerio de Vivienda, SERPAVI 2011-2024 (Excel oficial, descargable en mivau.gob.es/vivienda/alquila-bien-es-tu-derecho/serpavi) | Alquiler mediano en €/m² y €/mes (con percentiles 25 y 75) por municipio y provincia, 2011-2024 | Oficial |

Para unir con los salarios del INE: `serpavi_alquiler_*.csv` trae la columna `ccaa` con el mismo nombre que `ine_salario_ccaa.csv`. Parte de `serpavi_municipios.csv` y `serpavi_provincias.csv` (hojas del Excel guardadas como CSV). Ejecutar los scripts desde la carpeta `scrapers/`.

## Descartadas

- We Work Remotely: ofertas remotas sin ciudad.
- Teleport API: ya no funciona.
- Idealista, Indeed, InfoJobs: bloqueadas o no permiten rastreo.
