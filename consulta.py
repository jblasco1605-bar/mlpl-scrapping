"""Logica de una consulta de mlpl scrapping (sin interfaz).

La usan las dos formas de ejecutar el proyecto:
    - consola.py: en la terminal (input / print).
    - main.py:    pagina web con Streamlit.

Flujo de una consulta (funcion hacerConsulta):
    1. Se homogeneiza la ciudad y se localiza en SERPAVI (municipio, provincia y comunidad).
    2. Se descargan las ofertas de Ticjob y Tecnoempleo (scrapers/). Si una web falla,
       se usa el ultimo CSV guardado en datos/.
    3. Se limpian las ofertas con limpieza.py (puesto, ubicacion y salario).
    4. Se cruzan con el alquiler (SERPAVI, Numbeo) y el salario oficial (INE).
    5. Se calcula lo que queda al mes y el veredicto.
    6. Se compara con otras ciudades.
"""
import os
import sys

import pandas as pd

import limpieza

# Los scrapers estan en la carpeta scrapers/ y los usamos como modulos
CARPETA = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(CARPETA, 'scrapers'))
import tecnoempleo  # noqa: E402
import ticjob       # noqa: E402

DATOS = os.path.join(CARPETA, 'datos')
COLUMNAS = ticjob.cabecera + ['skills']


# ---------------------------------------------------------------------------
# Lectura de los CSV de coste de vida (SERPAVI, Numbeo, INE)
# ---------------------------------------------------------------------------
def leerCsv(nombre):
    # Lee un CSV de datos/ como texto. Si no existe devuelve None
    ruta = os.path.join(DATOS, nombre)
    if not os.path.exists(ruta):
        return None
    return pd.read_csv(ruta, sep=';', encoding='utf-8-sig', dtype=str, keep_default_na=False)


def numero(texto):
    # "1337.7" -> 1337.7 ; "" o texto -> None
    try:
        valor = float(texto)
        return valor if valor > 0 else None
    except (TypeError, ValueError):
        return None


def euros(valor):
    if valor is None:
        return '—'
    return f'{valor:,.0f} €'.replace(',', '.')


def cargarSerpavi():
    # Alquiler de pisos por municipio y provincia, con el nombre homogeneizado
    muni = leerCsv('serpavi_alquiler_municipios.csv')
    prov = leerCsv('serpavi_alquiler_provincias.csv')
    muni = muni[muni['tipologia'] == 'colectiva (pisos)'].copy()
    prov = prov[prov['tipologia'] == 'colectiva (pisos)'].copy()
    muni['ciudad_norm'] = muni['NMUN'].map(limpieza.normalizar_ciudad)
    prov['provincia_norm'] = prov['provincia'].map(limpieza.normalizar_ciudad)
    return muni, prov


def cargarNumbeo():
    numbeo = leerCsv('numbeo_ciudades.csv')
    numbeo['ciudad_norm'] = numbeo['ciudad'].map(limpieza.normalizar_ciudad)
    return numbeo


def cargarIne():
    # Nos quedamos con el salario medio bruto de cada comunidad (ambos sexos)
    ine = leerCsv('ine_salario_ccaa.csv')
    columna = 'Comunidades y Ciudades Autónomas'
    ine = ine[(ine['Sexo'] == 'Ambos sexos') & (ine['Medidas estadísticas'] == 'Media')
              & (ine[columna] != '')]
    salarios = {}
    for _, fila in ine.iterrows():
        salarios[fila[columna]] = float(fila['valor'])
    return salarios


# ---------------------------------------------------------------------------
# Cruce geografico: ciudad -> municipio, provincia y comunidad
# ---------------------------------------------------------------------------
def nombreBonito(nombre):
    # "Alicante/Alacant" -> "Alicante" ; "Palmas de Gran Canaria, Las" -> "Las Palmas de Gran Canaria"
    nombre = nombre.split('/')[0]
    if ', ' in nombre:
        partes = nombre.split(', ')
        nombre = partes[1] + ' ' + partes[0]
    return nombre


def localizar(ciudad, muni, prov):
    """Busca la ciudad (ya normalizada) en SERPAVI. Devuelve un diccionario o None."""
    filas = muni[muni['ciudad_norm'] == ciudad]
    if len(filas) > 0:
        fila = filas.iloc[0]
        filas = filas[filas['CUMUN'] == fila['CUMUN']]   # por si dos municipios se llaman igual
        return {'ciudad': ciudad, 'nombre': nombreBonito(fila['NMUN']),
                'provincia': limpieza.normalizar_ciudad(fila['provincia']),
                'ccaa': fila['ccaa'], 'alquileres': filas}
    filas = prov[prov['provincia_norm'] == ciudad]
    if len(filas) > 0:
        fila = filas.iloc[0]
        return {'ciudad': ciudad, 'nombre': nombreBonito(fila['provincia']),
                'provincia': ciudad, 'ccaa': fila['ccaa'], 'alquileres': filas}
    return None


def alquilerActual(lugar):
    """Alquiler mediano del ultimo año con datos (SERPAVI)."""
    filas = lugar['alquileres']
    filas = filas[filas['eur_mes_mediana'] != ''].sort_values('anio')
    if len(filas) == 0:
        return None, None
    ultima = filas.iloc[-1]
    return float(ultima['eur_mes_mediana']), ultima['anio']


def evolucionAlquiler(lugar):
    """Tabla año -> alquiler mediano (SERPAVI) de la ciudad."""
    filas = lugar['alquileres'][lugar['alquileres']['eur_mes_mediana'] != ''].sort_values('anio')
    return pd.DataFrame({'Año': filas['anio'],
                         'Alquiler (€/mes)': filas['eur_mes_mediana'].astype(float)})


# ---------------------------------------------------------------------------
# Ofertas de empleo: scraping con respaldo en CSV
# ---------------------------------------------------------------------------
def buscarEnFuente(nombre, funcion, argumentos, fichero_csv):
    """Lanza un scraper. Si falla, carga el ultimo CSV guardado de esa fuente.

    Devuelve (DataFrame de ofertas, aviso o None).
    """
    try:
        filas = funcion(*argumentos)
        ofertas = pd.DataFrame(filas, columns=ticjob.cabecera if nombre == 'Ticjob'
                               else tecnoempleo.cabecera).astype(str)
        # Guardamos las ofertas nuevas en el CSV de la fuente (sin repetir URLs)
        anteriores = leerCsv(fichero_csv)
        if anteriores is not None:
            juntas = pd.concat([ofertas, anteriores]).drop_duplicates('url')
        else:
            juntas = ofertas
        juntas.to_csv(os.path.join(DATOS, fichero_csv), sep=';', index=False, encoding='utf-8-sig')
        aviso = None
    except Exception as e:
        ofertas = leerCsv(fichero_csv)
        if ofertas is None:
            return pd.DataFrame(columns=COLUMNAS), f'{nombre} ha fallado ({e}) y no hay CSV guardado.'
        aviso = f'{nombre} ha fallado ({e}): se usa el último CSV guardado (datos/{fichero_csv}).'
    ofertas = ofertas.reindex(columns=COLUMNAS).fillna('')
    ofertas['fuente'] = nombre
    return ofertas, aviso


def prepararOfertas(ofertas, puesto, lugar):
    """Limpia cada oferta y se queda con las del puesto, la zona y con salario."""
    filas = []
    sin_salario = 0
    for _, o in ofertas.iterrows():
        # 1. ¿Es del puesto buscado? (sinonimos, faltas de ortografia...)
        if limpieza.parecido_puesto(puesto, o['puesto']) < 1:
            continue
        # 2. ¿Esta en la ciudad, su provincia o su comunidad?
        zona = limpieza.coincidencia_ubicacion(o['ciudad'] + ' | ' + o['puesto'],
                                               lugar['ciudad'], lugar['provincia'], lugar['ccaa'])
        if zona == '':
            continue
        # 3. Salario: numeros ya separados por el scraper o, si no, leidos del texto
        minimo, maximo = numero(o['salario_min']), numero(o['salario_max'])
        if minimo is None and maximo is None:
            minimo, maximo = limpieza.parsear_salario(o['salario_texto'])
        bruto = limpieza.salario_bruto_anual(minimo, maximo)
        if bruto is None:
            sin_salario = sin_salario + 1      # se descarta: no publica salario
            continue
        filas.append({'Fuente': o['fuente'], 'Puesto': o['puesto'], 'Empresa': o['empresa'],
                      'Coincide en': zona, 'Tecnologías': o['skills'],
                      'Bruto anual': round(bruto),
                      'Neto mensual': round(limpieza.salario_neto_mensual(bruto)),
                      'Enlace': o['url']})
    return pd.DataFrame(filas), sin_salario


def compararCiudades(numbeo, muni, prov, salarios_ine):
    """Neto medio INE de la comunidad menos el alquiler SERPAVI, para cada ciudad de Numbeo."""
    filas = []
    for ciudad in numbeo['ciudad_norm']:
        lugar = localizar(ciudad, muni, prov)
        if lugar is None or lugar['ccaa'] not in salarios_ine:
            continue
        alquiler, anio = alquilerActual(lugar)
        if alquiler is None:
            continue
        neto = limpieza.salario_neto_mensual(salarios_ine[lugar['ccaa']])
        filas.append({'Ciudad': lugar['nombre'], 'Neto INE': round(neto),
                      'Alquiler': round(alquiler), 'Te queda': round(neto - alquiler)})
    ranking = pd.DataFrame(filas).sort_values('Te queda', ascending=False)
    # Numeramos las ciudades para que salgan ordenadas de mejor a peor
    ranking['Ciudad'] = [f'{i + 1:02d}. {c}' for i, c in enumerate(ranking['Ciudad'])]
    return ranking


def veredicto(porcentaje):
    """Segun el % del sueldo que se lleva el alquiler: (tipo, texto)."""
    if porcentaje <= 0.30:
        return 'compensa', f'Compensa: el alquiler se lleva el {porcentaje:.0%} del sueldo.'
    if porcentaje <= 0.45:
        return 'justo', f'Justo: el alquiler se lleva el {porcentaje:.0%} del sueldo.'
    return 'no compensa', f'No compensa vivir solo: el alquiler se lleva el {porcentaje:.0%} del sueldo.'


# ---------------------------------------------------------------------------
# Consulta completa
# ---------------------------------------------------------------------------
def hacerConsulta(puesto, ciudad_escrita, avisar=print):
    """Ejecuta el flujo entero y devuelve un diccionario con todo el resultado.

    'avisar' es la funcion que muestra el progreso (print en la terminal).
    Si la ciudad no existe, devuelve {'error': ...}.
    """
    # --- 1. Localizar la ciudad ---
    muni, prov = cargarSerpavi()
    ciudad = limpieza.normalizar_ciudad(ciudad_escrita)
    lugar = localizar(ciudad, muni, prov)
    if lugar is None:
        return {'error': f'No encuentro «{ciudad_escrita}» entre los municipios de SERPAVI.'}

    # --- 2. Descargar ofertas (una fuente detras de otra) ---
    avisar('Descargando ofertas de Ticjob...')
    de_ticjob, aviso1 = buscarEnFuente('Ticjob', ticjob.buscarOfertas, (puesto, ciudad), 'ticjob.csv')
    avisar('Descargando ofertas de Tecnoempleo...')
    de_tecnoempleo, aviso2 = buscarEnFuente('Tecnoempleo', tecnoempleo.scrapear, (puesto,),
                                            'tecnoempleo.csv')
    todas = pd.concat([de_ticjob, de_tecnoempleo]).drop_duplicates('url')

    # --- 3. Limpiar y filtrar ---
    ofertas, sin_salario = prepararOfertas(todas, puesto, lugar)

    # --- 4. Cruzar con el coste de vida ---
    alquiler, anio = alquilerActual(lugar)
    numbeo = cargarNumbeo()
    salarios_ine = cargarIne()
    fila_numbeo = numbeo[numbeo['ciudad_norm'] == ciudad]
    bruto_ine = salarios_ine.get(lugar['ccaa'])

    if len(ofertas) > 0:
        neto = ofertas['Neto mensual'].mean()
        origen = f'media de {len(ofertas)} ofertas'
    elif bruto_ine:
        neto = limpieza.salario_neto_mensual(bruto_ine)
        origen = 'sin ofertas con salario: media INE'
    else:
        neto, origen = None, 'sin datos'

    # --- 5. Lo que queda al mes y veredicto ---
    te_queda, porcentaje, opinion = None, None, None
    if neto and alquiler:
        te_queda = neto - alquiler
        porcentaje = alquiler / neto
        opinion = veredicto(porcentaje)

    numbeo_ciudad = None
    if len(fila_numbeo) > 0:
        n = fila_numbeo.iloc[0]
        numbeo_ciudad = {'centro': numero(n['alquiler_1hab_centro']),
                         'afueras': numero(n['alquiler_1hab_afueras'])}

    # --- 6. Comparar con otras ciudades ---
    ranking = compararCiudades(numbeo, muni, prov, salarios_ine)

    return {'error': None, 'puesto': puesto, 'lugar': lugar,
            'avisos': [a for a in (aviso1, aviso2) if a],
            'ofertas': ofertas, 'sin_salario': sin_salario,
            'neto': neto, 'origen': origen, 'alquiler': alquiler, 'anio': anio,
            'te_queda': te_queda, 'porcentaje': porcentaje, 'veredicto': opinion,
            'numbeo': numbeo_ciudad, 'bruto_ine': bruto_ine,
            'evolucion': evolucionAlquiler(lugar), 'ranking': ranking}


def resultadoJson(r):
    """Resultado de la consulta como diccionario listo para json.dumps (practica de APIs REST)."""
    return {'puesto': r['puesto'], 'ciudad': r['lugar']['nombre'],
            'provincia': r['lugar']['provincia'], 'comunidad': r['lugar']['ccaa'],
            'neto_mensual': r['neto'], 'alquiler_mensual': r['alquiler'], 'te_queda': r['te_queda'],
            'veredicto': r['veredicto'][0] if r['veredicto'] else None,
            'ofertas': r['ofertas'].to_dict(orient='records'),
            'ranking_ciudades': r['ranking'].to_dict(orient='records')}
