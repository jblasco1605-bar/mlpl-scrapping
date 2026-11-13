"""Homogeneizar ciudades, puestos y salarios de todas las fuentes."""
import re
import unicodedata

from rapidfuzz import fuzz

# Porcentaje del bruto que se va en IRPF + Seguridad Social (aproximado)
RETENCION = 0.20

# Parecido minimo (0-100) para dar por buena una palabra con faltas de ortografia
UMBRAL_PARECIDO = 80


# ---------------------------------------------------------------------------
# Texto basico
# ---------------------------------------------------------------------------
def quitar_tildes(texto):
    texto = unicodedata.normalize('NFKD', str(texto))
    return texto.encode('ascii', 'ignore').decode()


def limpiar(texto):
    # minusculas, sin tildes y sin espacios sobrantes
    return re.sub(r'\s+', ' ', quitar_tildes(texto).lower()).strip()


# ---------------------------------------------------------------------------
# Ciudades
# ---------------------------------------------------------------------------
# Variante (minusculas, sin tildes) -> nombre unificado. Ampliable.
EQUIVALENCIAS_CIUDAD = {
    # ingles -> espanol
    'seville': 'sevilla', 'saragossa': 'zaragoza', 'corunna': 'a coruna',
    'cordova': 'cordoba', 'majorca': 'palma', 'navarre': 'pamplona',
    # valenciano / catalan -> castellano
    'valencia': 'valencia', 'alacant': 'alicante', 'elx': 'elche',
    'castello': 'castellon', 'castello de la plana': 'castellon',
    'castellon de la plana': 'castellon',
    'lerida': 'lleida', 'gerona': 'girona',
    # gallego
    'la coruna': 'a coruna', 'coruna': 'a coruna', 'orense': 'ourense',
    'sanxenxo': 'sanxenxo',
    # euskera
    'donostia': 'san sebastian', 'donostia-san sebastian': 'san sebastian',
    'bilbo': 'bilbao', 'gasteiz': 'vitoria', 'vitoria-gasteiz': 'vitoria',
    'iruna': 'pamplona',
    # nombres largos o con isla
    'palma de mallorca': 'palma',
    'las palmas': 'las palmas de gran canaria',
    'gran canaria': 'las palmas de gran canaria',
    'tenerife': 'santa cruz de tenerife',
}

# Palabras que no van con mayuscula en mitad de un nombre
MINUSCULAS = {'de', 'del', 'la', 'las', 'el', 'los', 'y', 'i', 'en'}

# "Coruna, A" o "Palmas de Gran Canaria, Las" -> articulo delante
ARTICULO_FINAL = re.compile(r"^(.+),\s*(a|o|as|os|la|las|el|los|l'|els|les|es|sa)$")


def formato_titulo(texto):
    palabras = texto.split(' ')
    resultado = []
    for i, palabra in enumerate(palabras):
        if i > 0 and palabra in MINUSCULAS:
            resultado.append(palabra)
        else:
            resultado.append(palabra[:1].upper() + palabra[1:])
    return ' '.join(resultado)


def normalizar_ciudad(texto):
    """'Seville (Sevilla)' -> 'Sevilla', 'València' -> 'Valencia', 'La Coruña' -> 'A Coruna'."""
    if texto is None:
        return ''
    t = limpiar(texto)
    if t in ('', 'nan'):
        return ''
    t = re.sub(r'\(.*?\)', '', t).strip()   # "seville (sevilla)" -> "seville"
    if '/' in t:                              # "alicante/alacant" -> "alicante"
        t = t.split('/')[0].strip()
    m = ARTICULO_FINAL.match(t)
    if m:                                     # "coruna, a" -> "a coruna"
        articulo = m.group(2)
        t = articulo + m.group(1) if articulo.endswith("'") else articulo + ' ' + m.group(1)
    t = EQUIVALENCIAS_CIUDAD.get(t, t)
    return formato_titulo(t)


# Comunidad autonoma con el nombre del INE -> variantes que usan las webs
VARIANTES_CCAA = {
    'Andalucía': ['andalucia', 'andalusia'],
    'Aragón': ['aragon'],
    'Asturias, Principado de': ['asturias', 'principado de asturias'],
    'Balears, Illes': ['baleares', 'illes balears', 'islas baleares', 'balearic islands'],
    'Canarias': ['canarias', 'islas canarias', 'canary islands', 'no peninsular'],
    'Cantabria': ['cantabria'],
    'Castilla - La Mancha': ['castilla-la mancha', 'castilla la mancha'],
    'Castilla y León': ['castilla y leon', 'castilla-leon'],
    'Cataluña': ['cataluna', 'catalunya', 'catalonia'],
    'Comunitat Valenciana': ['comunidad valenciana', 'comunitat valenciana', 'valencian community'],
    'Extremadura': ['extremadura'],
    'Galicia': ['galicia'],
    'Madrid, Comunidad de': ['madrid', 'comunidad de madrid'],
    'Murcia, Región de': ['murcia', 'region de murcia'],
    'Navarra, Comunidad Foral de': ['navarra', 'comunidad foral de navarra'],
    'País Vasco': ['pais vasco', 'euskadi', 'basque country'],
    'Rioja, La': ['la rioja', 'rioja'],
    'Ceuta': ['ceuta'],
    'Melilla': ['melilla'],
}


def normalizar_ccaa(texto):
    """'Comunidad Valenciana' -> 'Comunitat Valenciana' (nombre del INE). '' si no es una comunidad."""
    t = limpiar(texto)
    for nombre_ine, variantes in VARIANTES_CCAA.items():
        if t == limpiar(nombre_ine) or t in variantes:
            return nombre_ine
    return ''


def partes_ubicacion(texto):
    # "Cataluña, Madrid" / "Madrid (Híbrido) | 30.000 €" -> trozos sueltos
    texto = re.sub(r'\(.*?\)', ' ', str(texto))
    return [p.strip() for p in re.split(r',|\||;|/| o | y ', texto) if p.strip()]


def coincidencia_ubicacion(texto_oferta, ciudad, provincia='', ccaa=''):
    """Compara la ubicacion de una oferta con la ciudad buscada.

    Devuelve 'ciudad', 'provincia', 'comunidad' o '' (no coincide). Ticjob casi
    siempre da la comunidad ("Cataluña"), por eso se mira tambien ese nivel.
    """
    texto = str(texto_oferta)
    texto_limpio = ' ' + re.sub(r'[^a-z0-9]+', ' ', limpiar(texto)) + ' '
    ciudad_limpia = ' ' + limpiar(ciudad) + ' '
    if ciudad_limpia in texto_limpio:
        return 'ciudad'
    partes = partes_ubicacion(texto)
    if any(normalizar_ciudad(p) == ciudad for p in partes):
        return 'ciudad'
    if provincia and provincia != ciudad and any(normalizar_ciudad(p) == provincia for p in partes):
        return 'provincia'
    if ccaa and any(normalizar_ccaa(p) == ccaa for p in partes):
        return 'comunidad'
    return ''


# ---------------------------------------------------------------------------
# Puestos
# ---------------------------------------------------------------------------
# Nombre unificado -> sinonimos (minusculas, sin tildes). Ampliable.
SINONIMOS_PUESTO = {
    'desarrollador': ['desarrollador', 'desarrolladora', 'programador', 'programadora',
                      'developer', 'programmer', 'software engineer',
                      'ingeniero de software', 'ingeniera de software',
                      'analista programador', 'analista organico', 'dev'],
    'cientifico_de_datos': ['cientifico de datos', 'cientifica de datos', 'data scientist',
                            'data science'],
    'analista_de_datos': ['analista de datos', 'data analyst', 'analista bi',
                          'business intelligence', 'bi analyst'],
    'ingeniero_de_datos': ['ingeniero de datos', 'ingeniera de datos', 'data engineer'],
    'machine_learning': ['machine learning', 'ml engineer', 'ingeniero ia', 'ai engineer',
                         'inteligencia artificial'],
    'devops': ['devops', 'sre', 'site reliability', 'platform engineer'],
    'sistemas': ['administrador de sistemas', 'tecnico de sistemas', 'ingeniero de sistemas',
                 'sysadmin', 'system administrator'],
    'qa': ['qa', 'tester', 'testing', 'quality assurance'],
    'frontend': ['frontend', 'front-end', 'front end'],
    'backend': ['backend', 'back-end', 'back end'],
    'fullstack': ['fullstack', 'full-stack', 'full stack'],
    'jefe_de_proyecto': ['jefe de proyecto', 'jefa de proyecto', 'project manager',
                         'scrum master', 'product owner'],
    'ciberseguridad': ['ciberseguridad', 'cybersecurity', 'seguridad informatica',
                       'pentester', 'analista soc'],
    'soporte': ['soporte', 'helpdesk', 'help desk', 'service desk', 'tecnico de soporte'],
    'consultor': ['consultor', 'consultora', 'consultant'],
}

# Palabras que no aportan a la busqueda
PALABRAS_VACIAS = {'de', 'del', 'la', 'el', 'los', 'las', 'en', 'y', 'a', 'para', 'con',
                   'h', 'm', 'hm', 'mf'}

# Sinonimos ordenados de mas largo a mas corto ("analista de datos" antes que "analista")
_SINONIMOS = sorted(((s, nombre) for nombre, lista in SINONIMOS_PUESTO.items() for s in lista),
                    key=lambda par: -len(par[0]))


def normalizar_puesto(texto):
    """'Programador/a Python (H/M)' -> 'desarrollador python'."""
    t = limpiar(texto)
    t = re.sub(r'\b(\w+)/as?\b', r'\1', t)        # "programador/a" -> "programador"
    t = re.sub(r'\(.*?\)', ' ', t)               # "(h/m)", "(remoto)"
    t = re.sub(r'[^a-z0-9+#.\- ]', ' ', t)
    t = ' ' + re.sub(r'\s+', ' ', t).strip() + ' '
    for sinonimo, nombre in _SINONIMOS:
        t = t.replace(' ' + sinonimo + ' ', ' ' + nombre + ' ')
    return t.replace('_', ' ').strip()


def _palabras(texto_normalizado):
    # Los sinonimos de varias palabras cuentan como una sola ("cientifico de datos")
    t = ' ' + texto_normalizado + ' '
    for nombre in SINONIMOS_PUESTO:
        frase = nombre.replace('_', ' ')
        t = t.replace(' ' + frase + ' ', ' ' + nombre + ' ')
    return [p for p in t.split() if p not in PALABRAS_VACIAS]


def parecido_puesto(busqueda, titulo):
    """Fraccion (0-1) de palabras de la busqueda que aparecen en el titulo.

    Usa sinonimos, coincidencia parcial ('python' en 'python3') y rapidfuzz
    para faltas de ortografia ('pyhton').
    """
    q = _palabras(normalizar_puesto(busqueda))
    t = _palabras(normalizar_puesto(titulo))
    if not q or not t:
        return 0.0
    encontradas = 0
    for palabra in q:
        for otra in t:
            if palabras_coinciden(palabra, otra):
                encontradas += 1
                break
    return encontradas / len(q)


def palabras_coinciden(palabra, otra):
    if palabra == otra:
        return True
    # coincidencia parcial: "python" en "python3", "c" en "c++" (pero "java" no en "javascript")
    if re.fullmatch(re.escape(palabra) + r'[\d.+#\-]*', otra):
        return True
    # faltas de ortografia ("pyhton"), solo en palabras largas para no mezclar "java"/"jira"
    return len(palabra) >= 5 and fuzz.ratio(palabra, otra) >= UMBRAL_PARECIDO


# ---------------------------------------------------------------------------
# Salarios
# ---------------------------------------------------------------------------
_NUM = r'(\d{1,3}(?:[.,]\d{3})+|\d+(?:[.,]\d+)?)'
_RANGO = re.compile(_NUM + r'\s*(k|mil)?\s*(?:€|eur|euros)?\s*(?:-|–|a|y|hasta)\s*'
                    + _NUM + r'\s*(k|mil)?')
_SUELTO = re.compile(_NUM + r'\s*(k|mil)?\s*(?:€|eur)')


def _a_numero(texto):
    if re.fullmatch(r'\d{1,3}(?:[.,]\d{3})+', texto):     # "34.000" -> 34000
        return float(re.sub(r'[.,]', '', texto))
    return float(texto.replace(',', '.'))                  # "34,5" -> 34.5


def _a_anual(valor, es_miles, texto):
    if es_miles:
        valor = valor * 1000
    if 700 <= valor < 8000 and 'mes' in texto:              # "2.000 €/mes"
        valor = valor * 12
    return valor


def parsear_salario(texto):
    """'34.000 - 40.000 EUR B/A' -> (34000.0, 40000.0). (None, None) si no hay cifra."""
    if texto is None:
        return None, None
    t = limpiar(str(texto).replace('€', ' eur '))           # el € se perderia al quitar tildes
    t = re.sub(r'\d{1,2}/\d{1,2}/\d{2,4}', ' ', t)          # quitar fechas
    for m in _RANGO.finditer(t):
        a = _a_numero(m.group(1))
        b = _a_numero(m.group(3))
        miles = bool(m.group(2) or m.group(4))
        if a < 1000 and b >= 1000:                         # "36 - 42.000"
            a = a * 1000
        a = _a_anual(a, miles and a < 1000, t)
        b = _a_anual(b, miles and b < 1000, t)
        if 8000 <= a <= b <= 300000:
            return a, b
    for m in _SUELTO.finditer(t):
        v = _a_anual(_a_numero(m.group(1)), bool(m.group(2)), t)
        if 8000 <= v <= 300000:
            return v, v
    return None, None


def salario_bruto_anual(minimo, maximo):
    # Media del rango; si solo hay uno, ese
    valores = [v for v in (minimo, maximo) if v is not None and v == v]
    if not valores:
        return None
    return sum(valores) / len(valores)


def salario_neto_mensual(bruto_anual, retencion=RETENCION):
    return bruto_anual * (1 - retencion) / 12
