import csv
import os
import re
import time

import requests
from bs4 import BeautifulSoup

# Carpeta datos/ (funciona tanto si se ejecuta desde scrapers/ como desde main.py)
DATOS = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'datos')

# Cabeceras como en la L1 (el servidor puede devolver otra cosa si no hay User-Agent)
cabeceras = {'User-Agent': 'Mozilla/5.0', 'Accept-Language': 'en'}

# Lo que queremos de cada ciudad: texto de la fila de la tabla -> nombre de la columna
conceptos = {
    '1 Bedroom Apartment in City Centre': 'alquiler_1hab_centro',
    '1 Bedroom Apartment Outside of City Centre': 'alquiler_1hab_afueras',
    '3 Bedroom Apartment in City Centre': 'alquiler_3hab_centro',
    '3 Bedroom Apartment Outside of City Centre': 'alquiler_3hab_afueras',
    'Average Monthly Net Salary (After Tax)': 'salario_neto_mensual',
    'Meal, Inexpensive Restaurant': 'menu_restaurante',
    'Monthly Pass (Regular Price)': 'abono_transporte',
}


def getHtml(url):
    # Descarga una pagina. Si falla devuelve None para que el programa no se pare
    try:
        respuesta = requests.get(url, headers=cabeceras, timeout=30)
        respuesta.raise_for_status()
        return respuesta.text
    except requests.exceptions.RequestException as e:
        print(e)
        return None


def getNumero(texto):
    # De "€1,337.70 1,000.00 - 2,000.00" nos quedamos con el primer numero
    m = re.search(r'[\d,]+\.?\d*', texto.replace('€', ''))
    if m is None:
        return ''
    return float(m.group(0).replace(',', ''))


def scrapear():
    # 1. Pagina de Espana: tabla con todas las ciudades
    html = getHtml('https://www.numbeo.com/cost-of-living/country_result.jsp?country=Spain')
    if html is None:
        raise RuntimeError('numbeo.com no responde')
    soup = BeautifulSoup(html, 'html.parser')
    tabla = soup.find('table', id='t2')
    if tabla is None:
        raise RuntimeError('numbeo.com ha cambiado la tabla de ciudades')
    filas_tabla = tabla.find_all('tr')

    filas = []
    for fila in filas_tabla[1:]:
        enlace = fila.find('a')
        celdas = fila.find_all('td')
        if enlace is None or len(celdas) < 4:
            continue
        ciudad = enlace.get_text(strip=True)
        url_ciudad = enlace['href']
        indice_vida = celdas[2].get_text(strip=True)
        indice_alquiler = celdas[3].get_text(strip=True)
        print(ciudad)

        # 2. Pagina de cada ciudad: buscamos las filas que nos interesan
        html_ciudad = getHtml(url_ciudad)
        if html_ciudad is None:
            continue
        soup_ciudad = BeautifulSoup(html_ciudad, 'html.parser')
        datos = {}
        for tr in soup_ciudad.select('table.data_wide_table tr'):
            columnas = tr.find_all('td')
            if len(columnas) < 2:
                continue
            nombre = columnas[0].get_text(' ', strip=True)
            if nombre in conceptos:
                datos[conceptos[nombre]] = getNumero(columnas[1].get_text(strip=True))

        fila_csv = [ciudad, indice_vida, indice_alquiler]
        for columna in conceptos.values():
            fila_csv.append(datos.get(columna, ''))
        fila_csv.append(url_ciudad)
        filas.append(fila_csv)
        time.sleep(3)   # pausa entre peticiones
    return filas


def guardar(filas, ruta=os.path.join(DATOS, 'numbeo_ciudades.csv')):
    with open(ruta, 'w', newline='', encoding='utf-8-sig') as f:
        escritor = csv.writer(f, delimiter=';')
        escritor.writerow(['ciudad', 'indice_coste_vida', 'indice_alquiler']
                          + list(conceptos.values()) + ['url'])
        escritor.writerows(filas)


if __name__ == '__main__':
    filas = scrapear()
    guardar(filas)
    print(len(filas), 'ciudades guardadas')
