import csv
import os

import requests

# Carpeta datos/ (funciona tanto si se ejecuta desde scrapers/ como desde main.py)
DATOS = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'datos')

# Tablas de la Encuesta Anual de Estructura Salarial del INE
tablas = {
    'ine_salario_ocupacion': 28186,
    'ine_salario_sector': 28185,
    'ine_salario_ccaa': 28191,
}


def descargar():
    # Descarga las tres tablas y las guarda en datos/. Devuelve cuantas ha guardado
    guardadas = 0
    for nombre in tablas:
        url = 'https://servicios.ine.es/wstempus/js/ES/DATOS_TABLA/' + str(tablas[nombre])
        # nult=1: ultimo periodo; det=2 y tip=M: incluir los metadatos de cada serie
        parametros = {'nult': 1, 'det': 2, 'tip': 'M'}
        try:
            respuesta = requests.get(url, params=parametros, timeout=60)
            respuesta.raise_for_status()
            series = respuesta.json()
        except requests.exceptions.RequestException as e:
            print(e)
            continue

        filas = []
        columnas = []
        for serie in series:
            # Cada serie tiene metadatos (sexo, comunidad, ocupacion...) y un valor
            fila = {}
            for meta in serie['MetaData']:
                fila[meta['Variable']['Nombre']] = meta['Nombre']
            for dato in serie['Data']:
                if dato['Valor'] is None:
                    continue
                fila['anio'] = dato['Anyo']
                fila['valor'] = dato['Valor']
                filas.append(dict(fila))
            for clave in fila:
                if clave not in columnas:
                    columnas.append(clave)

        ruta = os.path.join(DATOS, nombre + '.csv')
        with open(ruta, 'w', newline='', encoding='utf-8-sig') as f:
            escritor = csv.DictWriter(f, fieldnames=columnas, delimiter=';')
            escritor.writeheader()
            escritor.writerows(filas)
        print(nombre, len(filas), 'filas')
        guardadas = guardadas + 1
    if guardadas == 0:
        raise RuntimeError('la API del INE no responde')
    return guardadas


if __name__ == '__main__':
    descargar()
