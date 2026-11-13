import os
import time
from urllib.parse import urljoin

import pandas as pd
import requests
from bs4 import BeautifulSoup

# Carpeta datos/ (funciona tanto si se ejecuta desde scrapers/ como desde main.py)
DATOS = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'datos')

url = "https://www.tecnoempleo.com/ofertas-trabajo/"
cabeceras = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:158.0) Gecko/20100101 Firefox/158.0"
}

# Mismas columnas que ticjob.csv (para juntar las dos fuentes) + las tecnologias
cabecera = ['busqueda', 'puesto', 'empresa', 'ciudad', 'fecha',
            'salario_texto', 'salario_min', 'salario_max', 'url', 'skills']


def getSalarioTexto(oferta):
    # Nos quedamos con el trozo de texto de la oferta que habla de euros
    for trozo in oferta.get_text(" | ", strip=True).split(" | "):
        t = trozo.lower()
        if "€" in t or "eur" in t or "b/a" in t or "brutos" in t:
            return trozo
    return ""


def leerOfertas(soup, busqueda, urls_vistas):
    # Recorre las cajas de ofertas de una pagina y devuelve una fila por oferta
    filas = []
    ofertas = soup.find_all("div", class_="p-3")
    for oferta in ofertas:

        enlace_oferta = oferta.select_one("h3 a")
        if not enlace_oferta:
            continue
        enlace = urljoin(url, enlace_oferta.get("href", ""))
        if enlace in urls_vistas:      # los div.p-3 pueden ir uno dentro de otro
            continue
        urls_vistas.append(enlace)

        nombre_empresa = oferta.select_one("a.text-primary")
        ciudad = oferta.find("b")
        badges = oferta.select("span.hidden-md-down span.badge")

        tecnologias = ", ".join(b.get_text(strip=True) for b in badges)
        titulo = enlace_oferta.get_text(strip=True)

        filas.append([busqueda, titulo,
                      nombre_empresa.get_text(strip=True) if nombre_empresa else "",
                      ciudad.get_text(strip=True) if ciudad else "",
                      "", getSalarioTexto(oferta), "", "", enlace, tecnologias])
        print(f"Se ha descargado {len(filas)} ofertas, la última fue \"{titulo}\"")
    return filas


def getSiguiente(soup, url_actual):
    # Enlace "Siguiente" de la paginacion (None si es la ultima pagina)
    for a in soup.find_all("a", href=True):
        if "siguiente" in a.get_text(strip=True).lower():
            return urljoin(url_actual, a["href"])
    return None


def scrapear(puesto, max_paginas=3):
    # te = termino de busqueda (lo que escribe el usuario en la app)
    filas = []
    urls_vistas = []
    url_pagina = url
    parametros = {"te": puesto}
    for pagina in range(1, max_paginas + 1):
        print("descargando el html de la url", url_pagina)
        respuesta = requests.get(url_pagina, params=parametros, timeout=10, headers=cabeceras)
        if not respuesta.ok:
            if pagina == 1:
                raise RuntimeError(f"Tecnoempleo responde con error HTTP {respuesta.status_code}")
            break
        soup = BeautifulSoup(respuesta.text, "html.parser")
        filas = filas + leerOfertas(soup, puesto, urls_vistas)
        url_pagina = getSiguiente(soup, respuesta.url)
        parametros = None          # el enlace "Siguiente" ya lleva la busqueda
        if url_pagina is None:
            break
        time.sleep(2)              # pausa para no saturar el servidor
    if len(filas) == 0:
        raise RuntimeError("Tecnoempleo no ha devuelto ofertas (sin resultados, bloqueo o cambio en la web)")
    return filas


def guardar(filas, ruta=os.path.join(DATOS, "tecnoempleo.csv")):
    df = pd.DataFrame(filas, columns=cabecera)
    df.to_csv(ruta, sep=";", encoding="utf-8-sig", index=False)


if __name__ == "__main__":
    filas = scrapear("analista de datos")
    guardar(filas)
    print(len(filas), "ofertas guardadas en datos/tecnoempleo.csv")
