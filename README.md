<img src="logo/logo_tecnojob.png" alt="tecnojob" width="360">

# tecnojob (Proyecto ATD)

Cruce de **ofertas de empleo IT** con el **precio del alquiler por ciudad**, para ver en qué ciudades compensa más trabajar. Se priorizan datos **oficiales**.

App publicada: https://mlpl-scrapping-7pehhrnd92s5z2hayh6cmu.streamlit.app/

## Cómo ejecutarlo

```bash
pip3 install -r requirements.txt
python3 consola.py      # en la terminal (sin página web)
python3 main.py         # página web (abre el navegador)
```

- `python3 consola.py` abre un menú: **1** consultar (pide puesto y ciudad, muestra todo el resultado en la terminal y lo guarda en `resultado.json`), **2** actualizar los datos de coste de vida (vuelve a ejecutar los scrapers de SERPAVI, INE y Numbeo) y **3** salir.
- Las ofertas (Ticjob, Tecnoempleo) se descargan en cada consulta porque cambian a diario y dependen del puesto. El coste de vida (SERPAVI, INE, Numbeo) apenas cambia y tarda en descargarse, así que se guarda en `datos/` y se actualiza con la opción 2, o solo si falta algún CSV.
- `python3 main.py` arranca Streamlit y abre el navegador (también funciona `streamlit run main.py`).
- En VS Code se pueden lanzar con F5 (configuraciones de `.vscode/launch.json`).

## Qué hace una consulta

Se escribe un puesto y una ciudad y todo el resultado sale en una sola consulta:

1. La ciudad se homogeneiza (`limpieza.py`) y se localiza en SERPAVI: municipio, provincia y comunidad.
2. Se descargan las ofertas de Ticjob y Tecnoempleo (requests + BeautifulSoup). Si una web falla, se usa el último CSV guardado de esa fuente en `datos/` y se muestra un aviso.
3. Se limpian las ofertas: puesto (sinónimos), ubicación y salario. Se descartan las que no publican salario y el resto se pasa a neto mensual (`RETENCION` en `limpieza.py`).
4. Se cruzan con el alquiler (SERPAVI, Numbeo) y el salario oficial (INE).
5. Se calcula lo que queda al mes y el veredicto (compensa, justo o no compensa).
6. Se comparan las ciudades y el resultado se puede guardar en JSON.

## Ficheros

- `consulta.py`: flujo de una consulta (scrapers → limpieza → cruce), sin interfaz.
- `consola.py`: versión de terminal (`input` / `print`).
- `main.py`: versión web (Streamlit). Usa la misma lógica de `consulta.py`.
- `limpieza.py`: `normalizar_ciudad`, `normalizar_ccaa`, `normalizar_puesto`, `parecido_puesto`, `parsear_salario`, `salario_neto_mensual`.
- `scrapers/`: un script por fuente (se pueden ejecutar solos desde esa carpeta).
- `datos/`: CSV de cada fuente (separador `;`, UTF-8).
- `logo/`: logo e icono de tecnojob.
- `diagramas/`: arquitectura del proyecto y flujo de una consulta.

## Fuentes

| Script | Fuente | Datos | Tipo |
|---|---|---|---|
| `ticjob.py` | ticjob.es (HTML) | Ofertas IT por ciudad y puesto, con salario cuando lo publican | Ofertas reales, no oficial |
| `tecnoempleo.py` | tecnoempleo.com (HTML) | Ofertas IT por puesto: título, empresa, ciudad, tecnologías y salario si lo publican | Ofertas reales, no oficial |
| `numbeo_ciudades.py` | numbeo.com (HTML) | Alquiler y salario neto mensual de 14 ciudades españolas | Estimaciones de usuarios, no oficial |
| `ine_salarios.py` | INE, Encuesta Anual de Estructura Salarial (API REST) | Salario medio bruto 2024 por ocupación, sector y comunidad autónoma | Oficial |
| `serpavi_alquiler.py` | Ministerio de Vivienda, SERPAVI 2011-2024 (Excel oficial) | Alquiler mediano en €/mes y €/m² por municipio y provincia | Oficial |

`serpavi_alquiler.py` parte de `serpavi_municipios.csv` y `serpavi_provincias.csv` (hojas del Excel guardadas como CSV) y añade la columna `ccaa` con el mismo nombre que usa el INE, para poder unir alquiler y salarios.

## Descartadas

- We Work Remotely: ofertas remotas sin ciudad.
- Teleport API: ya no funciona.
- Idealista, Indeed, InfoJobs: bloqueadas o no permiten rastreo.
