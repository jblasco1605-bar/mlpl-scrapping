import csv
import os
import re
import time
import unicodedata

import requests
from bs4 import BeautifulSoup

# Carpeta datos/ (funciona tanto si se ejecuta desde scrapers/ como desde main.py)
DATOS = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'datos')

# Ciudades que queremos buscar (son las que aparecen en la URL de ticjob)
ciudades = ['madrid', 'barcelona', 'valencia']
paginas = 3

cabecera = ['busqueda', 'puesto', 'empresa', 'ciudad', 'fecha',
            'salario_texto', 'salario_min', 'salario_max', 'url']


def getPagina(url, pagina):
    # Descarga una pagina del listado. Si falla devuelve None
    try:
        respuesta = requests.get(url, params={'page': pagina}, timeout=20)
        respuesta.raise_for_status()
        return respuesta.text
    except requests.exceptions.RequestException as e:
        print(e)
        return None


def getSalario(descripcion):
    # En la descripcion hay una linea tipo "Salario: 25.000 - 29.000 EUR"
    m = re.search(r'Salario:\s*(.+)', descripcion)
    if m is None:
        return '', '', ''
    texto = m.group(1).strip()
    numeros = re.findall(r'\d[\d.]*', texto)
    if len(numeros) < 2:
        return texto, '', ''
    minimo = float(numeros[0].replace('.', ''))
    maximo = float(numeros[1].replace('.', ''))
    if minimo < 1000:       # "36 - 42.000" -> el 36 son miles
        minimo = minimo * 1000
    return texto, minimo, maximo


def getSlug(texto):
    # "Programador Python" -> "programador-python" (como en las URLs de ticjob)
    texto = unicodedata.normalize('NFKD', texto).encode('ascii', 'ignore').decode()
    return re.sub(r'[^a-z0-9]+', '-', texto.lower()).strip('-')


def leerListado(url, paginas, busqueda, urls_vistas):
    # Lee las paginas de un listado. Devuelve las filas y si la web ha respondido
    filas = []
    responde = False
    for pagina in range(1, paginas + 1):
        print(url, pagina)
        html = getPagina(url, pagina)
        if html is None:
            break
        responde = True
        soup = BeautifulSoup(html, 'html.parser')
        ofertas = soup.find_all('div', class_='job-card-wrapper')
        if len(ofertas) == 0:
            break
        for oferta in ofertas:
            titulo = oferta.find('a', class_='job-title')
            empresa = oferta.find('div', class_='job-company-title')
            fecha = oferta.select_one('.date-field p')
            lugar = oferta.select_one('.location-field p')
            descripcion = oferta.find('div', class_='job-description')
            if titulo is None or titulo['href'] in urls_vistas:
                continue
            urls_vistas.append(titulo['href'])
            texto, minimo, maximo = '', '', ''
            if descripcion is not None:
                texto, minimo, maximo = getSalario(descripcion.get_text('\n'))
            filas.append([busqueda, titulo.get_text(strip=True),
                          empresa.get_text(strip=True) if empresa else '',
                          lugar.get_text(strip=True) if lugar else '',
                          fecha.get_text(strip=True) if fecha else '',
                          texto, minimo, maximo, titulo['href']])
        time.sleep(2)   # pausa para no saturar el servidor
    return filas, responde


def buscarOfertas(puesto, ciudad, paginas=3):
    # Ticjob no tiene buscador por texto: las busquedas van en la URL,
    # p. ej. /ofertas-trabajo-it/sevilla o /ofertas-trabajo-it/python-sevilla
    slug_ciudad = getSlug(ciudad)
    slug_puesto = getSlug(puesto)
    listados = [(slug_ciudad, paginas),
                (slug_puesto + '-' + slug_ciudad, 2),
                (slug_puesto, 2)]
    filas = []
    urls_vistas = []
    alguna_responde = False
    for slug, n in listados:
        url = 'https://ticjob.es/esp/ofertas-trabajo-it/' + slug
        nuevas, responde = leerListado(url, n, slug, urls_vistas)
        filas = filas + nuevas
        alguna_responde = alguna_responde or responde
    if not alguna_responde:
        raise RuntimeError('ticjob.es no responde')
    return filas


def guardar(filas, ruta=os.path.join(DATOS, 'ticjob.csv')):
    with open(ruta, 'w', newline='', encoding='utf-8-sig') as f:
        escritor = csv.writer(f, delimiter=';')
        escritor.writerow(cabecera)
        escritor.writerows(filas)


if __name__ == '__main__':
    filas = []
    urls_vistas = []
    for ciudad in ciudades:
        url = 'https://ticjob.es/esp/ofertas-trabajo-it/' + ciudad
        nuevas, responde = leerListado(url, paginas, ciudad, urls_vistas)
        filas = filas + nuevas
    guardar(filas)
    print(len(filas), 'ofertas guardadas')
