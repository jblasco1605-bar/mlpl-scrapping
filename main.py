"""mlpl scrapping: ¿compensa trabajar de X en la ciudad Y?

Aplicacion web hecha con Streamlit. Se puede arrancar de dos formas:
    - Boton Play de VS Code / Spyder (python main.py): el propio fichero lanza Streamlit.
    - Terminal: streamlit run main.py

Flujo de una consulta:
    1. El usuario escribe un puesto y una ciudad.
    2. Se localiza la ciudad en SERPAVI (municipio, provincia y comunidad).
    3. Se descargan las ofertas de Ticjob y Tecnoempleo (scrapers/). Si una web falla,
       se usa el ultimo CSV guardado en datos/.
    4. Se limpian las ofertas con limpieza.py (puesto, ubicacion y salario).
    5. Se cruzan con el alquiler (SERPAVI, Numbeo) y el salario oficial (INE).
"""
import json
import os
import sys

import pandas as pd
import streamlit as st

import limpieza

# Los scrapers estan en la carpeta scrapers/ y los usamos como modulos
CARPETA = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(CARPETA, 'scrapers'))
import tecnoempleo  # noqa: E402
import ticjob       # noqa: E402

DATOS = os.path.join(CARPETA, 'datos')
COLUMNAS = ticjob.cabecera + ['skills']


# ---------------------------------------------------------------------------
# Arranque con el boton Play (python main.py)
# ---------------------------------------------------------------------------
# Streamlit necesita su propio servidor. Si ejecutamos el fichero con Python
# "normal", lo relanzamos con "streamlit run" (que abre el navegador).
if __name__ == '__main__':
    from streamlit import runtime
    if not runtime.exists():
        import subprocess
        subprocess.run([sys.executable, '-m', 'streamlit', 'run', __file__])
        sys.exit()


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
    # Numeramos las ciudades para que el grafico salga ordenado de mejor a peor
    ranking['Ciudad'] = [f'{i + 1:02d}. {c}' for i, c in enumerate(ranking['Ciudad'])]
    return ranking


# ---------------------------------------------------------------------------
# Pagina web
# ---------------------------------------------------------------------------
st.set_page_config(page_title='mlpl scrapping', page_icon='💼', layout='wide')
st.title('💼 mlpl scrapping')
st.write('¿Compensa trabajar aquí? Busca ofertas en **Ticjob** y **Tecnoempleo** y compara el '
         'sueldo neto con el alquiler de la ciudad (**SERPAVI**, **Numbeo** e **INE**).')

col1, col2 = st.columns(2)
puesto = col1.text_input('Puesto de trabajo', placeholder='Programador Python, Data Scientist...')
ciudad_escrita = col2.text_input('Ciudad española', placeholder='Madrid, Valencia, Sevilla...')
buscar = st.button('🔎 Buscar', type='primary')

if buscar and (puesto.strip() == '' or ciudad_escrita.strip() == ''):
    st.error('Escribe un puesto y una ciudad.')

elif buscar:
    # --- 1. Localizar la ciudad ---
    muni, prov = cargarSerpavi()
    ciudad = limpieza.normalizar_ciudad(ciudad_escrita)
    lugar = localizar(ciudad, muni, prov)

    if lugar is None:
        st.error(f'No encuentro «{ciudad_escrita}» entre los municipios de SERPAVI.')
    else:
        # --- 2. Descargar ofertas (una fuente detras de otra) ---
        with st.spinner('Descargando ofertas de Ticjob y Tecnoempleo...'):
            de_ticjob, aviso1 = buscarEnFuente('Ticjob', ticjob.buscarOfertas,
                                               (puesto, ciudad), 'ticjob.csv')
            de_tecnoempleo, aviso2 = buscarEnFuente('Tecnoempleo', tecnoempleo.scrapear,
                                                    (puesto,), 'tecnoempleo.csv')
        for aviso in (aviso1, aviso2):
            if aviso:
                st.warning(aviso)
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

        # --- 5. Mostrar el resultado ---
        st.header(f'{puesto} en {lugar["nombre"]}')
        st.caption(f'Provincia de {lugar["provincia"]} · {lugar["ccaa"]} · '
                   f'retención aplicada: {limpieza.RETENCION:.0%}')

        m1, m2, m3, m4 = st.columns(4)
        m1.metric('Ofertas con salario', len(ofertas))
        m2.metric('Neto / mes', euros(neto))
        m3.metric('Alquiler / mes', euros(alquiler))
        if neto and alquiler:
            porcentaje = alquiler / neto
            m4.metric('Te queda / mes', euros(neto - alquiler))
            st.caption(f'Neto: {origen} · Alquiler: mediana SERPAVI {anio} · '
                       f'el alquiler es el {porcentaje:.0%} del sueldo')
            if porcentaje <= 0.30:
                st.success(f'✅ Compensa: el alquiler se lleva el {porcentaje:.0%} del sueldo.')
            elif porcentaje <= 0.45:
                st.warning(f'⚖️ Justo: el alquiler se lleva el {porcentaje:.0%} del sueldo.')
            else:
                st.error(f'❌ No compensa vivir solo: el alquiler se lleva el {porcentaje:.0%} '
                         'del sueldo.')

        st.subheader('Ofertas')
        if len(ofertas) == 0:
            st.info('No hay ofertas de este puesto con salario publicado en la zona. '
                    'Se usa el salario medio del INE como referencia.')
        else:
            grafico = pd.DataFrame({
                'Oferta': [f'{i + 1:02d}. {p[:50]}' for i, p in enumerate(ofertas['Puesto'])],
                'Neto mensual': ofertas['Neto mensual']})
            st.bar_chart(grafico, x='Oferta', y='Neto mensual', horizontal=True)
            st.dataframe(ofertas, hide_index=True,
                         column_config={'Enlace': st.column_config.LinkColumn('Enlace')})
        st.caption(f'{sin_salario} ofertas del puesto descartadas por no publicar salario.')

        st.subheader('Coste de vida')
        c1, c2, c3 = st.columns(3)
        c1.markdown(f'**SERPAVI (oficial)**  \nAlquiler mediano de un piso: {euros(alquiler)}/mes '
                    f'({anio})')
        if len(fila_numbeo) > 0:
            n = fila_numbeo.iloc[0]
            c2.markdown(f'**Numbeo**  \n1 hab. centro: {euros(numero(n["alquiler_1hab_centro"]))}/mes'
                        f'  \n1 hab. afueras: {euros(numero(n["alquiler_1hab_afueras"]))}/mes')
        else:
            c2.markdown('**Numbeo**  \nSin datos de esta ciudad.')
        if bruto_ine:
            c3.markdown(f'**INE (oficial)**  \nSalario medio en {lugar["ccaa"]}: '
                        f'{euros(bruto_ine)} brutos/año')

        st.subheader('Evolución del alquiler (SERPAVI)')
        evolucion = lugar['alquileres'][lugar['alquileres']['eur_mes_mediana'] != '']
        evolucion = pd.DataFrame({'Año': evolucion['anio'],
                                  'Alquiler (€/mes)': evolucion['eur_mes_mediana'].astype(float)})
        st.line_chart(evolucion, x='Año', y='Alquiler (€/mes)')

        st.subheader('¿En qué ciudad compensa más?')
        st.caption('Salario medio del INE de cada comunidad (neto) menos el alquiler de SERPAVI.')
        ranking = compararCiudades(numbeo, muni, prov, salarios_ine)
        st.bar_chart(ranking, x='Ciudad', y='Te queda', horizontal=True)
        st.dataframe(ranking, hide_index=True)

        # --- 6. Resultado completo en JSON (como en la practica de APIs REST) ---
        resultado = {
            'puesto': puesto, 'ciudad': lugar['nombre'], 'provincia': lugar['provincia'],
            'comunidad': lugar['ccaa'], 'neto_mensual': neto, 'alquiler_mensual': alquiler,
            'te_queda': (neto - alquiler) if neto and alquiler else None,
            'ofertas': ofertas.to_dict(orient='records'),
            'ranking_ciudades': ranking.to_dict(orient='records'),
        }
        st.download_button('⬇️ Descargar el resultado en JSON',
                           json.dumps(resultado, indent=4, ensure_ascii=False, default=float),
                           file_name='resultado.json', mime='application/json')
