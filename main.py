"""mlpl scrapping: ¿compensa trabajar de X en la ciudad Y?

Ejecutar desde la carpeta del proyecto:
    streamlit run main.py
"""
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import altair as alt
import pandas as pd
import streamlit as st
from rapidfuzz import process

import limpieza

# Los scrapers estan en scrapers/ y los importamos como modulos
CARPETA = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(CARPETA, 'scrapers'))
import ine_salarios      # noqa: E402
import numbeo_ciudades   # noqa: E402
import tecnoempleo       # noqa: E402
import ticjob            # noqa: E402

DATOS = os.path.join(CARPETA, 'datos')

# Segundos maximos que esperamos a las webs de ofertas antes de usar el CSV guardado
TIEMPO_MAXIMO_OFERTAS = 90
# Segundos maximos para volver a descargar el coste de vida (Numbeo tarda ~1 min)
TIEMPO_MAXIMO_COSTE_VIDA = 240

# Columnas comunes de las ofertas (las de Ticjob + las tecnologias de Tecnoempleo)
COLUMNAS_OFERTAS = ticjob.cabecera + ['skills']


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------
def euros(valor):
    if valor is None or pd.isna(valor):
        return '—'
    return f'{valor:,.0f} €'.replace(',', '.')


def leer_csv(nombre):
    ruta = os.path.join(DATOS, nombre)
    if not os.path.exists(ruta):
        return None
    return pd.read_csv(ruta, sep=';', encoding='utf-8-sig', dtype=str, keep_default_na=False)


def con_limite(funcion, segundos, *args):
    # Ejecuta funcion(*args); si tarda mas de 'segundos' lanza TimeoutError
    ejecutor = ThreadPoolExecutor(max_workers=1)
    futuro = ejecutor.submit(funcion, *args)
    try:
        return futuro.result(timeout=segundos)
    finally:
        ejecutor.shutdown(wait=False, cancel_futures=True)


def describir_error(error):
    if isinstance(error, TimeoutError):
        return 'ha tardado demasiado'
    return str(error) or type(error).__name__


# ---------------------------------------------------------------------------
# Coste de vida (no depende del puesto: se lee del CSV y se cachea)
# ---------------------------------------------------------------------------
@st.cache_data(show_spinner='Cargando alquileres oficiales (SERPAVI)...')
def cargar_serpavi():
    muni = pd.read_csv(os.path.join(DATOS, 'serpavi_alquiler_municipios.csv'), sep=';',
                       encoding='utf-8-sig', dtype={'provincia_cod': str, 'CUMUN': str})
    prov = pd.read_csv(os.path.join(DATOS, 'serpavi_alquiler_provincias.csv'), sep=';',
                       encoding='utf-8-sig', dtype={'provincia_cod': str})
    muni = muni[muni['tipologia'] == 'colectiva (pisos)']
    prov = prov[prov['tipologia'] == 'colectiva (pisos)']
    # Nombre homogeneo para poder buscar lo que escribe el usuario
    nombres = {n: limpieza.normalizar_ciudad(n) for n in muni['NMUN'].unique()}
    muni['ciudad_norm'] = muni['NMUN'].map(nombres)
    provincias = {n: limpieza.normalizar_ciudad(n) for n in prov['provincia'].unique()}
    prov['provincia_norm'] = prov['provincia'].map(provincias)
    return muni, prov


@st.cache_data(show_spinner=False)
def cargar_numbeo():
    df = leer_csv('numbeo_ciudades.csv')
    aviso = None
    if df is None:
        try:
            numbeo_ciudades.guardar(con_limite(numbeo_ciudades.scrapear, TIEMPO_MAXIMO_COSTE_VIDA))
            df = leer_csv('numbeo_ciudades.csv')
        except Exception as e:
            aviso = f'Numbeo no está disponible ({describir_error(e)}) y no hay CSV guardado.'
            df = pd.DataFrame(columns=['ciudad'])
    df['ciudad_norm'] = df['ciudad'].map(limpieza.normalizar_ciudad)
    return df, aviso


@st.cache_data(show_spinner=False)
def cargar_ine():
    df = leer_csv('ine_salario_ccaa.csv')
    aviso = None
    if df is None:
        try:
            con_limite(ine_salarios.descargar, TIEMPO_MAXIMO_COSTE_VIDA)
            df = leer_csv('ine_salario_ccaa.csv')
        except Exception as e:
            aviso = f'El INE no está disponible ({describir_error(e)}) y no hay CSV guardado.'
            return pd.DataFrame(), aviso
    col_ccaa = 'Comunidades y Ciudades Autónomas'
    df = df[(df['Sexo'] == 'Ambos sexos') & (df['Medidas estadísticas'] == 'Media')
            & (df[col_ccaa] != '')]
    df = df[[col_ccaa, 'anio', 'valor']].rename(columns={col_ccaa: 'ccaa'})
    df['valor'] = df['valor'].astype(float)
    return df, aviso


def actualizar_coste_vida():
    # Vuelve a descargar Numbeo e INE; si fallan se quedan los CSV que habia
    avisos = []
    try:
        numbeo_ciudades.guardar(con_limite(numbeo_ciudades.scrapear, TIEMPO_MAXIMO_COSTE_VIDA))
    except Exception as e:
        avisos.append(f'Numbeo ha fallado ({describir_error(e)}): se mantiene el último CSV.')
    try:
        con_limite(ine_salarios.descargar, TIEMPO_MAXIMO_COSTE_VIDA)
    except Exception as e:
        avisos.append(f'El INE ha fallado ({describir_error(e)}): se mantiene el último CSV.')
    cargar_numbeo.clear()
    cargar_ine.clear()
    return avisos


def nombre_visible(nombre):
    # "Palmas de Gran Canaria, Las" -> "Las Palmas de Gran Canaria"; "Alicante/Alacant" -> "Alicante"
    nombre = str(nombre).split('/')[0].strip()
    m = re.match(r"^(.+),\s*(\S+)$", nombre)
    if m:
        articulo = m.group(2)
        nombre = articulo + m.group(1) if articulo.endswith("'") else f'{articulo} {m.group(1)}'
    return nombre[:1].upper() + nombre[1:]


def localizar(ciudad, muni, prov):
    """Ciudad normalizada -> municipio, provincia y comunidad (segun SERPAVI)."""
    filas = muni[muni['ciudad_norm'] == ciudad]
    if len(filas) > 0:
        # Si hay dos municipios con el mismo nombre, el que tiene mas alquileres
        cumun = filas.sort_values('n_alquileres', ascending=False).iloc[0]['CUMUN']
        filas = filas[filas['CUMUN'] == cumun]
        primera = filas.iloc[0]
        return {'ciudad': ciudad, 'nombre_oficial': nombre_visible(primera['NMUN']),
                'provincia': limpieza.normalizar_ciudad(primera['provincia']),
                'ccaa': primera['ccaa'], 'filas_alquiler': filas, 'nivel_alquiler': 'municipio'}
    filas = prov[prov['provincia_norm'] == ciudad]
    if len(filas) > 0:
        primera = filas.iloc[0]
        return {'ciudad': ciudad, 'nombre_oficial': nombre_visible(primera['provincia']),
                'provincia': ciudad, 'ccaa': primera['ccaa'],
                'filas_alquiler': filas, 'nivel_alquiler': 'provincia'}
    return None


def sugerir_ciudad(ciudad, muni):
    parecida = process.extractOne(ciudad, muni['ciudad_norm'].unique())
    return parecida[0] if parecida and parecida[1] >= 70 else None


def alquiler_serpavi(lugar, prov):
    # Ultimo año con dato; si el municipio no tiene, el de su provincia
    for filas, nivel in ((lugar['filas_alquiler'], lugar['nivel_alquiler']),
                         (prov[prov['provincia_norm'] == lugar['provincia']], 'provincia')):
        filas = filas.dropna(subset=['eur_mes_mediana'])
        if len(filas) > 0:
            ultima = filas.sort_values('anio').iloc[-1]
            return {'mediana': ultima['eur_mes_mediana'], 'p25': ultima['eur_mes_p25'],
                    'p75': ultima['eur_mes_p75'], 'anio': int(ultima['anio']), 'nivel': nivel}
    return None


# ---------------------------------------------------------------------------
# Ofertas (dependen del puesto: se scrapean en cada busqueda)
# ---------------------------------------------------------------------------
def guardar_ofertas(nombre_csv, df):
    # Añade las ofertas nuevas al CSV de la fuente (sirve de copia si la web falla)
    viejas = leer_csv(nombre_csv)
    if viejas is not None:
        df = pd.concat([df, viejas]).drop_duplicates('url', keep='first')
    df.to_csv(os.path.join(DATOS, nombre_csv), sep=';', index=False, encoding='utf-8-sig')


def buscar_tecnoempleo(puesto):
    # Primero con requests + BeautifulSoup (rapido); si la web lo bloquea, con Selenium
    try:
        return tecnoempleo.scrapear(puesto)
    except Exception as error_requests:
        print('Tecnoempleo con requests ha fallado:', error_requests, '-> pruebo con Selenium')
        try:
            import tecnoempleo_selenium
            return tecnoempleo_selenium.scrapear(puesto)
        except Exception as error_selenium:
            raise RuntimeError(f'requests: {error_requests}; Selenium: {error_selenium}')


def buscar_ofertas(puesto, ciudad):
    """Lanza Ticjob y Tecnoempleo a la vez. Devuelve (DataFrame, avisos)."""
    fuentes = {
        'Ticjob': (ticjob.buscarOfertas, (puesto, ciudad), 'ticjob.csv', ticjob.cabecera),
        'Tecnoempleo': (buscar_tecnoempleo, (puesto,), 'tecnoempleo.csv', tecnoempleo.cabecera),
    }
    ejecutor = ThreadPoolExecutor(max_workers=len(fuentes))
    futuros = {nombre: ejecutor.submit(f[0], *f[1]) for nombre, f in fuentes.items()}
    inicio = time.time()
    tablas = []
    avisos = []
    for nombre, futuro in futuros.items():
        nombre_csv, columnas = fuentes[nombre][2], fuentes[nombre][3]
        restante = max(1, TIEMPO_MAXIMO_OFERTAS - (time.time() - inicio))
        try:
            filas = futuro.result(timeout=restante)
            df = pd.DataFrame(filas, columns=columnas).astype(str).replace('nan', '')
            guardar_ofertas(nombre_csv, df)
        except Exception as e:
            df = leer_csv(nombre_csv)
            if df is None:
                avisos.append(f'**{nombre}** ha fallado ({describir_error(e)}) y no hay CSV guardado: '
                              'no se usan sus ofertas.')
                continue
            avisos.append(f'**{nombre}** ha fallado ({describir_error(e)}): se usa el último CSV '
                          f'guardado (`datos/{nombre_csv}`, {len(df)} ofertas).')
        df['fuente'] = nombre
        tablas.append(df)
    ejecutor.shutdown(wait=False, cancel_futures=True)
    if not tablas:
        return pd.DataFrame(columns=COLUMNAS_OFERTAS + ['fuente']), avisos
    juntas = pd.concat(tablas, ignore_index=True).drop_duplicates('url')
    return juntas.reindex(columns=COLUMNAS_OFERTAS + ['fuente']).fillna(''), avisos


def numero(texto):
    try:
        valor = float(texto)
        return valor if valor > 0 else None
    except (TypeError, ValueError):
        return None


def preparar_ofertas(df, puesto, lugar):
    """Calcula salario neto, parecido del puesto y coincidencia de ubicacion."""
    filas = []
    for _, o in df.iterrows():
        minimo, maximo = numero(o['salario_min']), numero(o['salario_max'])
        if minimo is None and maximo is None:
            minimo, maximo = limpieza.parsear_salario(o['salario_texto'])
        bruto = limpieza.salario_bruto_anual(minimo, maximo)
        filas.append({
            'fuente': o['fuente'],
            'puesto': o['puesto'],
            'empresa': o['empresa'],
            'ubicacion': o['ciudad'],
            'skills': o['skills'],
            'coincidencia': limpieza.coincidencia_ubicacion(
                o['ciudad'] + ' | ' + o['puesto'], lugar['ciudad'], lugar['provincia'], lugar['ccaa']),
            'parecido': limpieza.parecido_puesto(puesto, o['puesto']),
            'salario_texto': o['salario_texto'],
            'bruto_anual': bruto,
            'neto_mensual': limpieza.salario_neto_mensual(bruto) if bruto else None,
            'url': o['url'],
        })
    return pd.DataFrame(filas, columns=['fuente', 'puesto', 'empresa', 'ubicacion', 'skills',
                                        'coincidencia',
                                        'parecido', 'salario_texto', 'bruto_anual',
                                        'neto_mensual', 'url'])

# ---------------------------------------------------------------------------
# Datos para la comparativa entre ciudades
# ---------------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def resumen_ciudad(ciudad):
    """Alquiler SERPAVI, salario INE y Numbeo de una ciudad (para comparar)."""
    muni, prov = cargar_serpavi()
    lugar = localizar(ciudad, muni, prov)
    if lugar is None:
        return None
    alquiler = alquiler_serpavi(lugar, prov)
    ine, _ = cargar_ine()
    numbeo, _ = cargar_numbeo()
    fila_ine = ine[ine['ccaa'] == lugar['ccaa']] if len(ine) else pd.DataFrame()
    fila_numbeo = numbeo[numbeo['ciudad_norm'] == ciudad]
    return {
        'ciudad': ciudad,
        'Ciudad': lugar['nombre_oficial'],
        'Comunidad': lugar['ccaa'],
        'alquiler': alquiler['mediana'] if alquiler else None,
        'bruto_ine': fila_ine.iloc[0]['valor'] if len(fila_ine) else None,
        'numbeo_salario': numero(fila_numbeo.iloc[0]['salario_neto_mensual']) if len(fila_numbeo) else None,
        'numbeo_centro': numero(fila_numbeo.iloc[0]['alquiler_1hab_centro']) if len(fila_numbeo) else None,
    }


# ---------------------------------------------------------------------------
# Interfaz
# ---------------------------------------------------------------------------
NOMBRE_APP = 'mlpl scrapping'
COLOR = '#4F46E5'       # color principal (tambien en .streamlit/config.toml)
COLOR_ALQUILER = '#E11D48'
EJEMPLOS = ['Programador Python · Madrid', 'Data Scientist · Barcelona',
            'DevOps · Valencia', 'Consultor SAP · Sevilla', 'Desarrollador Java · Málaga']
REFERENCIAS = {
    'serpavi': 'SERPAVI · mediana oficial',
    'numbeo_centro': 'Numbeo · 1 hab. centro',
    'numbeo_afueras': 'Numbeo · 1 hab. afueras',
}

st.set_page_config(page_title=NOMBRE_APP, page_icon='💼', layout='wide')

st.markdown(f"""
<style>
  .block-container {{ padding-top: 2rem; max-width: 1200px; }}
  .hero {{
    background: linear-gradient(120deg, {COLOR} 0%, #7C3AED 55%, #DB2777 100%);
    color: white; border-radius: 18px; padding: 1.6rem 2rem; margin-bottom: 1.2rem;
  }}
  .hero h1 {{ color: white; font-size: 2.3rem; margin: 0; padding: 0; letter-spacing: -0.5px; }}
  .hero p {{ color: rgba(255,255,255,.88); margin: .35rem 0 0; font-size: 1.02rem; }}
  .hero .fuentes {{ margin-top: .8rem; display: flex; gap: .4rem; flex-wrap: wrap; }}
  .hero .fuentes span {{
    background: rgba(255,255,255,.18); border-radius: 999px; padding: .15rem .7rem; font-size: .8rem;
  }}
  div[data-testid="stMetric"] {{ background: white; }}
  div[data-testid="stMetricValue"] {{ font-weight: 700; }}
</style>
<div class="hero">
  <h1>💼 {NOMBRE_APP}</h1>
  <p>¿Compensa trabajar aquí? Busca ofertas reales y compara el sueldo neto con lo que cuesta
     el alquiler en esa ciudad.</p>
  <div class="fuentes"><span>Ticjob</span><span>Tecnoempleo</span><span>SERPAVI</span>
     <span>Numbeo</span><span>INE</span></div>
</div>
""", unsafe_allow_html=True)

# --- Barra lateral: ajustes que se aplican al momento, sin volver a buscar ---
with st.sidebar:
    st.header('⚙️ Ajustes')
    retencion = st.slider('Retención (IRPF + Seg. Social)', 5, 40, int(limpieza.RETENCION * 100),
                          format='%d %%', help='Parte del sueldo bruto que se va en impuestos. '
                          'Cambia el neto de todas las ofertas al momento.') / 100
    referencia = st.radio('Alquiler de referencia', list(REFERENCIAS),
                          format_func=REFERENCIAS.get,
                          help='Qué alquiler se resta al sueldo para calcular lo que te queda.')
    st.divider()
    st.subheader('🗂️ Coste de vida')
    st.caption('Numbeo e INE se leen de los CSV guardados en `datos/`.')
    if st.button('Volver a descargar Numbeo e INE', width='stretch'):
        with st.spinner('Descargando (puede tardar un par de minutos)...'):
            for aviso in actualizar_coste_vida():
                st.warning(aviso)
        st.success('Coste de vida actualizado.')
    st.divider()
    st.caption('Neto = bruto anual medio del rango × (1 − retención) / 12. '
               'Se descartan las ofertas que no publican salario.')


# --- Formulario ---
def usar_ejemplo():
    elegido = st.session_state.get('ejemplo')
    if elegido:
        st.session_state.puesto, st.session_state.ciudad = elegido.split(' · ')
        st.session_state.lanzar = True


with st.form('busqueda', border=True):
    col1, col2, col3 = st.columns([5, 5, 2], vertical_alignment='bottom')
    col1.text_input('Puesto de trabajo', key='puesto',
                    placeholder='Data Scientist, Programador Python...')
    col2.text_input('Ciudad española', key='ciudad', placeholder='Valencia, Sevilla...')
    buscar = col3.form_submit_button('🔎 Buscar', type='primary', width='stretch')
st.pills('O prueba con un ejemplo', EJEMPLOS, key='ejemplo', on_change=usar_ejemplo)

if buscar or st.session_state.pop('lanzar', False):
    puesto = st.session_state.puesto.strip()
    ciudad_escrita = st.session_state.ciudad.strip()
    if not puesto or not ciudad_escrita:
        st.error('Escribe un puesto y una ciudad.')
        st.stop()
    muni, prov = cargar_serpavi()
    ciudad = limpieza.normalizar_ciudad(ciudad_escrita)
    lugar = localizar(ciudad, muni, prov)
    if lugar is None:
        sugerencia = sugerir_ciudad(ciudad, muni)
        st.error(f'No encuentro «{ciudad_escrita}» entre los municipios españoles.'
                 + (f' ¿Quizá «{sugerencia}»?' if sugerencia else ''))
        st.stop()
    with st.status(f'Buscando «{puesto}» en Ticjob y Tecnoempleo...', expanded=False) as estado:
        st.write('Descargando ofertas de las dos webs a la vez (máximo '
                 f'{TIEMPO_MAXIMO_OFERTAS} s)...')
        crudas, avisos = buscar_ofertas(puesto, ciudad)
        st.write('Limpiando puestos, ciudades y salarios...')
        ofertas = preparar_ofertas(crudas, puesto, lugar)
        estado.update(label=f'{len(crudas)} ofertas descargadas y analizadas', state='complete')
    # Se guarda en la sesion: al mover filtros o ajustes no se vuelve a scrapear
    st.session_state.resultado = {'puesto': puesto, 'ciudad': ciudad, 'lugar': lugar,
                                  'ofertas': ofertas, 'avisos': avisos}

if 'resultado' not in st.session_state:
    st.info('👆 Escribe un puesto y una ciudad, o elige un ejemplo, para empezar.')
    st.stop()

# ---------------------------------------------------------------------------
# Resultados
# ---------------------------------------------------------------------------
res = st.session_state.resultado
puesto, ciudad, lugar = res['puesto'], res['ciudad'], res['lugar']
muni, prov = cargar_serpavi()
numbeo, aviso_numbeo = cargar_numbeo()
ine, aviso_ine = cargar_ine()

avisos = res['avisos'] + [a for a in (aviso_numbeo, aviso_ine) if a]
if avisos:
    with st.expander(f'⚠️ {len(avisos)} aviso(s) sobre las fuentes', expanded=True):
        for aviso in avisos:
            st.warning(aviso)

# Ofertas del puesto en la zona: primero las que tienen todas las palabras del puesto
ofertas = res['ofertas'].copy()
en_zona = ofertas[ofertas['coincidencia'] != '']
relevantes = en_zona[en_zona['parecido'] >= 1]
parcial = False
if relevantes['bruto_anual'].notna().sum() == 0:
    parciales = en_zona[en_zona['parecido'] >= 0.5]
    if parciales['bruto_anual'].notna().sum() > 0:
        relevantes, parcial = parciales, True
sin_salario = int(relevantes['bruto_anual'].isna().sum())
elegidas = relevantes.dropna(subset=['bruto_anual']).copy()
elegidas['neto_mensual'] = elegidas['bruto_anual'].map(
    lambda b: limpieza.salario_neto_mensual(b, retencion))
elegidas = elegidas.sort_values('neto_mensual', ascending=False)
elegidas['zona'] = elegidas['coincidencia'].map(
    {'ciudad': 'Ciudad', 'provincia': 'Provincia', 'comunidad': 'Comunidad'})

# Alquiler de referencia
alquiler = alquiler_serpavi(lugar, prov)
fila_numbeo = numbeo[numbeo['ciudad_norm'] == ciudad]
fila_ine = ine[ine['ccaa'] == lugar['ccaa']] if len(ine) else pd.DataFrame()
renta = alquiler['mediana'] if alquiler else None
etiqueta_renta = f'SERPAVI {alquiler["anio"]}' if alquiler else 'sin datos'
if referencia != 'serpavi':
    columna = 'alquiler_1hab_centro' if referencia == 'numbeo_centro' else 'alquiler_1hab_afueras'
    valor = numero(fila_numbeo.iloc[0][columna]) if len(fila_numbeo) else None
    if valor:
        renta = valor
        etiqueta_renta = 'Numbeo centro' if referencia == 'numbeo_centro' else 'Numbeo afueras'
    else:
        st.caption(f'ℹ️ Numbeo no tiene datos de {lugar["nombre_oficial"]}: se usa SERPAVI.')

# Sueldo de referencia: el de las ofertas o, si no hay, el del INE
bruto_ine = fila_ine.iloc[0]['valor'] if len(fila_ine) else None
if len(elegidas) > 0:
    neto, origen_neto = elegidas['neto_mensual'].mean(), 'media ofertas'
elif bruto_ine:
    neto = limpieza.salario_neto_mensual(bruto_ine, retencion)
    origen_neto = 'media INE'
else:
    neto, origen_neto = None, 'sin datos'

# --- Cabecera del resultado ---
st.markdown(f'## {puesto} en {lugar["nombre_oficial"]}')
st.markdown(f':violet-badge[📍 Provincia de {lugar["provincia"]}] '
            f':blue-badge[🗺️ {lugar["ccaa"]}] '
            f':gray-badge[💸 Retención {retencion:.0%}]')

c1, c2, c3, c4 = st.columns(4)
c1.metric('Ofertas', len(elegidas), 'con salario', delta_color='off', delta_arrow='off',
          border=True, help='Ofertas del puesto en la zona que publican salario')
c2.metric('Neto / mes', euros(neto), origen_neto, delta_color='off', delta_arrow='off',
          border=True, help=('Media del sueldo neto de las ofertas' if len(elegidas) else
                             f'No hay ofertas con salario: sueldo medio de {lugar["ccaa"]} (INE)'))
c3.metric('Alquiler / mes', euros(renta), etiqueta_renta, delta_color='off', delta_arrow='off',
          border=True, help='Alquiler de referencia (se cambia en la barra lateral)')
if neto and renta:
    pct = renta / neto
    c4.metric('Te queda / mes', euros(neto - renta), f'{pct:.0%} alquiler',
              delta_color='inverse' if pct > 0.3 else 'normal', delta_arrow='off', border=True)
    if pct <= 0.30:
        st.success(f'✅ **Compensa.** El alquiler se lleva el {pct:.0%} del sueldo, por debajo del '
                   '30 % que se suele recomendar.')
    elif pct <= 0.45:
        st.warning(f'⚖️ **Justo.** El alquiler se lleva el {pct:.0%} del sueldo: se puede vivir solo, '
                   'pero ahorrarás poco.')
    else:
        st.error(f'❌ **No compensa vivir solo.** El alquiler se lleva el {pct:.0%} del sueldo; '
                 'tocaría compartir piso.')
else:
    c4.metric('Te queda / mes', '—', border=True)

tab_ofertas, tab_coste, tab_evolucion, tab_comparar = st.tabs([
    f'💼 Ofertas ({len(elegidas)})', '🏠 Coste de vida', '📈 Evolución del alquiler',
    '🗺️ Comparar ciudades'])

# --- Pestaña: ofertas ---
with tab_ofertas:
    if parcial:
        st.info('Ninguna oferta coincide con todas las palabras del puesto; se muestran las que '
                'coinciden en parte.')
    if len(elegidas) == 0:
        descartadas = (f' Hay {sin_salario} que no publican salario y se han descartado.'
                       if sin_salario else '')
        st.info(f'No hay ofertas de «{puesto}» con salario publicado en {lugar["nombre_oficial"]} '
                f'ni en su comunidad.{descartadas} Arriba se usa el sueldo medio del INE como '
                'referencia.')
    else:
        f1, f2, f3 = st.columns([2, 2, 3])
        fuentes = f1.multiselect('Fuente', sorted(elegidas['fuente'].unique()),
                                 default=sorted(elegidas['fuente'].unique()))
        zonas = f2.multiselect('Coincide en', ['Ciudad', 'Provincia', 'Comunidad'],
                               default=sorted(elegidas['zona'].unique()))
        texto = f3.text_input('Filtrar por palabra o tecnología', placeholder='Python, remoto, AWS...')
        minimo = int(elegidas['neto_mensual'].min())
        maximo = int(elegidas['neto_mensual'].max())
        if maximo > minimo:
            neto_min = st.slider('Sueldo neto mínimo (€/mes)', minimo, maximo, minimo, step=50)
        else:
            neto_min = minimo
        vista = elegidas[elegidas['fuente'].isin(fuentes) & elegidas['zona'].isin(zonas)
                         & (elegidas['neto_mensual'] >= neto_min)]
        if texto:
            buscar_en = (vista['puesto'] + ' ' + vista['skills'] + ' ' + vista['empresa']
                         + ' ' + vista['ubicacion']).map(limpieza.limpiar)
            vista = vista[buscar_en.str.contains(limpieza.limpiar(texto), regex=False)]

        if len(vista) == 0:
            st.info('Ninguna oferta cumple los filtros.')
        else:
            graf = vista.reset_index(drop=True).copy()
            graf['oferta'] = [f'{i + 1}. {p[:55]}' for i, p in enumerate(graf['puesto'])]
            barras = alt.Chart(graf).mark_bar(cornerRadiusEnd=4).encode(
                x=alt.X('neto_mensual:Q', title='Sueldo neto mensual (€)'),
                y=alt.Y('oferta:N', sort=None, title=None, axis=alt.Axis(labelLimit=320)),
                color=alt.Color('fuente:N', title='Fuente',
                                scale=alt.Scale(range=[COLOR, '#0EA5E9'])),
                tooltip=[alt.Tooltip('puesto:N', title='Puesto'),
                         alt.Tooltip('empresa:N', title='Empresa'),
                         alt.Tooltip('ubicacion:N', title='Ubicación'),
                         alt.Tooltip('bruto_anual:Q', title='Bruto anual', format=',.0f'),
                         alt.Tooltip('neto_mensual:Q', title='Neto mensual', format=',.0f')])
            capas = barras
            if renta:
                capas = barras + alt.Chart(pd.DataFrame({'x': [renta]})).mark_rule(
                    color=COLOR_ALQUILER, strokeDash=[6, 4], size=2).encode(
                    x='x:Q', tooltip=[alt.Tooltip('x:Q', title='Alquiler', format=',.0f')])
            st.altair_chart(capas.properties(height=max(140, 34 * len(graf))), width='stretch')
            if renta:
                st.caption(f'La línea roja discontinua es el alquiler de referencia ({euros(renta)}).')

            tabla = vista.copy()
            tabla['ubicacion'] = tabla['ubicacion'].str.slice(0, 60)
            tabla['pct_alquiler'] = (renta / tabla['neto_mensual'] * 100) if renta else None
            st.dataframe(
                tabla[['fuente', 'puesto', 'empresa', 'zona', 'ubicacion', 'skills', 'bruto_anual',
                       'neto_mensual', 'pct_alquiler', 'url']],
                hide_index=True, width='stretch',
                column_config={
                    'fuente': 'Fuente', 'puesto': 'Puesto', 'empresa': 'Empresa',
                    'zona': st.column_config.TextColumn('Coincide en', help='Nivel al que la '
                                                        'ubicación coincide con tu ciudad'),
                    'ubicacion': 'Ubicación', 'skills': 'Tecnologías',
                    'bruto_anual': st.column_config.NumberColumn('Bruto anual', format='%.0f €'),
                    'neto_mensual': st.column_config.NumberColumn('Neto mensual', format='%.0f €'),
                    'pct_alquiler': st.column_config.ProgressColumn(
                        '% en alquiler', format='%.0f %%', min_value=0, max_value=100),
                    'url': st.column_config.LinkColumn('Oferta', display_text='Abrir ↗'),
                })
            st.download_button('⬇️ Descargar estas ofertas (CSV)',
                               tabla.drop(columns=['parecido']).to_csv(sep=';', index=False)
                               .encode('utf-8-sig'),
                               file_name=f'ofertas_{limpieza.limpiar(puesto).replace(" ", "_")}_'
                                         f'{ciudad.replace(" ", "_")}.csv',
                               mime='text/csv')
        if sin_salario:
            st.caption(f'{sin_salario} ofertas del puesto se han descartado por no publicar salario.')

# --- Pestaña: coste de vida ---
with tab_coste:
    a, b, c = st.columns(3)
    with a.container(border=True):
        st.markdown('**🏛️ Alquiler oficial (SERPAVI)**')
        if alquiler:
            st.metric('Mediana de un piso', euros(alquiler['mediana']))
            st.caption(f'Rango habitual {euros(alquiler["p25"])} – {euros(alquiler["p75"])} · '
                       f'{alquiler["nivel"]}, {alquiler["anio"]}')
        else:
            st.write('Sin datos.')
    with b.container(border=True):
        st.markdown('**🌍 Numbeo**')
        if len(fila_numbeo) > 0:
            n = fila_numbeo.iloc[0]
            st.metric('1 hab. en el centro', euros(numero(n['alquiler_1hab_centro'])))
            st.caption(f'Afueras {euros(numero(n["alquiler_1hab_afueras"]))} · salario neto medio '
                       f'{euros(numero(n["salario_neto_mensual"]))}')
        else:
            st.write(f'Numbeo no tiene datos de {lugar["nombre_oficial"]}.')
    with c.container(border=True):
        st.markdown('**📊 Salario oficial (INE)**')
        if bruto_ine:
            st.metric('Neto medio / mes', euros(limpieza.salario_neto_mensual(bruto_ine, retencion)))
            st.caption(f'Bruto anual {euros(bruto_ine)} · {lugar["ccaa"]}, '
                       f'{fila_ine.iloc[0]["anio"]}, todas las ocupaciones')
        else:
            st.write('Sin datos.')

    comparar = []
    if alquiler:
        comparar += [('SERPAVI · percentil 25', alquiler['p25']),
                     ('SERPAVI · mediana', alquiler['mediana']),
                     ('SERPAVI · percentil 75', alquiler['p75'])]
    if len(fila_numbeo) > 0:
        comparar += [('Numbeo · 1 hab. afueras', numero(fila_numbeo.iloc[0]['alquiler_1hab_afueras'])),
                     ('Numbeo · 1 hab. centro', numero(fila_numbeo.iloc[0]['alquiler_1hab_centro'])),
                     ('Numbeo · 3 hab. centro', numero(fila_numbeo.iloc[0]['alquiler_3hab_centro']))]
    comparar = pd.DataFrame([x for x in comparar if x[1]], columns=['Alquiler', 'euros'])
    if len(comparar) > 0:
        st.markdown('##### ¿Cuánto cuesta alquilar?')
        barras = alt.Chart(comparar).mark_bar(cornerRadiusEnd=4, color=COLOR).encode(
            x=alt.X('euros:Q', title='€ al mes'), y=alt.Y('Alquiler:N', sort=None, title=None),
            tooltip=['Alquiler', alt.Tooltip('euros:Q', format=',.0f', title='€/mes')])
        capas = barras
        if neto:
            capas = barras + alt.Chart(pd.DataFrame({'x': [neto]})).mark_rule(
                color='#16A34A', strokeDash=[6, 4], size=2).encode(x='x:Q')
        st.altair_chart(capas.properties(height=230), width='stretch')
        if neto:
            st.caption(f'La línea verde es tu sueldo neto de referencia ({euros(neto)}).')

# --- Pestaña: evolucion del alquiler ---
with tab_evolucion:
    series = []
    filas_muni = lugar['filas_alquiler'].dropna(subset=['eur_mes_mediana'])
    if len(filas_muni) and lugar['nivel_alquiler'] == 'municipio':
        series.append(filas_muni.assign(serie=lugar['nombre_oficial']))
    filas_prov = prov[prov['provincia_norm'] == lugar['provincia']].dropna(subset=['eur_mes_mediana'])
    if len(filas_prov):
        series.append(filas_prov.assign(serie=f'Provincia de {lugar["provincia"]}'))
    if not series:
        st.info('SERPAVI no tiene la evolución de esta zona.')
    else:
        evol = pd.concat(series)[['anio', 'serie', 'eur_mes_mediana', 'eur_mes_p25', 'eur_mes_p75']]
        principal = evol[evol['serie'] == evol['serie'].iloc[0]].sort_values('anio')
        primero, ultimo = principal.iloc[0], principal.iloc[-1]
        subida = ultimo['eur_mes_mediana'] / primero['eur_mes_mediana'] - 1
        e1, e2, e3 = st.columns(3)
        e1.metric(f'Alquiler en {int(primero["anio"])}', euros(primero['eur_mes_mediana']), border=True)
        e2.metric(f'Alquiler en {int(ultimo["anio"])}', euros(ultimo['eur_mes_mediana']),
                  f'{subida:+.0%} desde {int(primero["anio"])}', delta_color='inverse', border=True)
        e3.metric('Subida media al año',
                  f'{(1 + subida) ** (1 / max(1, ultimo["anio"] - primero["anio"])) - 1:+.1%}',
                  border=True)
        base = alt.Chart(evol).encode(x=alt.X('anio:O', title='Año'))
        banda = base.transform_filter(alt.datum.serie == principal['serie'].iloc[0]).mark_area(
            opacity=0.15, color=COLOR).encode(y='eur_mes_p25:Q', y2='eur_mes_p75:Q')
        lineas = base.mark_line(point=True, strokeWidth=3).encode(
            y=alt.Y('eur_mes_mediana:Q', title='Alquiler mediano (€/mes)'),
            color=alt.Color('serie:N', title=None, scale=alt.Scale(range=[COLOR, '#94A3B8']),
                            legend=alt.Legend(orient='top')),
            tooltip=[alt.Tooltip('serie:N', title='Zona'), alt.Tooltip('anio:O', title='Año'),
                     alt.Tooltip('eur_mes_mediana:Q', title='Mediana', format=',.0f'),
                     alt.Tooltip('eur_mes_p25:Q', title='Percentil 25', format=',.0f'),
                     alt.Tooltip('eur_mes_p75:Q', title='Percentil 75', format=',.0f')])
        st.altair_chart((banda + lineas).properties(height=360), width='stretch')
        st.caption('Pisos en alquiler, datos oficiales SERPAVI (Ministerio de Vivienda). '
                   'La banda sombreada va del percentil 25 al 75.')

# --- Pestaña: comparar ciudades ---
with tab_comparar:
    st.caption('Sueldo medio oficial (INE, por comunidad, con tu retención) menos el alquiler '
               'mediano (SERPAVI). Sirve para ver dónde compensa más trabajar.')
    todas = sorted(muni['ciudad_norm'].dropna().unique())
    por_defecto = sorted({c for c in numbeo['ciudad_norm'] if c in todas} | {ciudad})
    elegidas_c = st.multiselect('Ciudades a comparar', todas, default=por_defecto)
    filas = [resumen_ciudad(c) for c in elegidas_c]
    comp = pd.DataFrame([f for f in filas if f and f['alquiler'] and f['bruto_ine']])
    if len(comp) == 0:
        st.info('Elige alguna ciudad con datos.')
    else:
        comp['Neto INE'] = comp['bruto_ine'].map(lambda b: limpieza.salario_neto_mensual(b, retencion))
        comp['Te queda'] = comp['Neto INE'] - comp['alquiler']
        comp['% alquiler'] = comp['alquiler'] / comp['Neto INE'] * 100
        comp = comp.sort_values('Te queda', ascending=False)
        mejor = comp.iloc[0]
        st.markdown(f'🏆 Donde más te queda: **{mejor["Ciudad"]}** ({euros(mejor["Te queda"])} '
                    'al mes tras pagar el alquiler).')
        grafico = alt.Chart(comp).mark_bar(cornerRadiusEnd=4).encode(
            x=alt.X('Te queda:Q', title='Te queda al mes tras el alquiler (€)'),
            y=alt.Y('Ciudad:N', sort='-x', title=None),
            color=alt.condition(alt.datum.ciudad == ciudad, alt.value(COLOR), alt.value('#C7CBE8')),
            tooltip=['Ciudad', 'Comunidad',
                     alt.Tooltip('Neto INE:Q', format=',.0f', title='Neto INE'),
                     alt.Tooltip('alquiler:Q', format=',.0f', title='Alquiler'),
                     alt.Tooltip('Te queda:Q', format=',.0f'),
                     alt.Tooltip('% alquiler:Q', format='.0f', title='% en alquiler')])
        st.altair_chart(grafico.properties(height=max(160, 30 * len(comp))), width='stretch')
        st.caption(f'En color, {lugar["nombre_oficial"]}.')
        st.dataframe(
            comp[['Ciudad', 'Comunidad', 'Neto INE', 'alquiler', 'Te queda', '% alquiler',
                  'numbeo_salario', 'numbeo_centro']],
            hide_index=True, width='stretch',
            column_config={
                'Neto INE': st.column_config.NumberColumn('Neto INE / mes', format='%.0f €'),
                'alquiler': st.column_config.NumberColumn('Alquiler SERPAVI', format='%.0f €'),
                'Te queda': st.column_config.NumberColumn('Te queda', format='%.0f €'),
                '% alquiler': st.column_config.ProgressColumn(
                    '% en alquiler', format='%.0f %%', min_value=0, max_value=100),
                'numbeo_salario': st.column_config.NumberColumn('Neto Numbeo', format='%.0f €'),
                'numbeo_centro': st.column_config.NumberColumn('1 hab. centro (Numbeo)',
                                                               format='%.0f €'),
            })
