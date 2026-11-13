import csv
import os

# Carpeta datos/ (funciona tanto si se ejecuta desde scrapers/ como desde main.py)
DATOS = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'datos')

# Los CSV de partida (serpavi_municipios.csv y serpavi_provincias.csv) salen de guardar
# como CSV las hojas "Municipios" y "Provincias" del Excel que publica el Ministerio.
# En el Excel cada año es un grupo de columnas (..._11, ..._12, ... _24), asi que
# aqui lo pasamos a formato "una fila por territorio, año y tipo de vivienda".

# Codigo de provincia -> comunidad autonoma (nombres como en el INE)
comunidades = {
    'Andalucía': ['04', '11', '14', '18', '21', '23', '29', '41'],
    'Aragón': ['22', '44', '50'],
    'Asturias, Principado de': ['33'],
    'Balears, Illes': ['07'],
    'Canarias': ['35', '38'],
    'Cantabria': ['39'],
    'Castilla - La Mancha': ['02', '13', '16', '19', '45'],
    'Castilla y León': ['05', '09', '24', '34', '37', '40', '42', '47', '49'],
    'Cataluña': ['08', '17', '25', '43'],
    
    'Comunitat Valenciana': ['03', '12', '46'],
    'Extremadura': ['06', '10'],
    'Galicia': ['15', '27', '32', '36'],
    'Madrid, Comunidad de': ['28'],
    'Murcia, Región de': ['30'],
    'Navarra, Comunidad Foral de': ['31'],
    'País Vasco': ['01', '20', '48'],
    'Rioja, La': ['26'],
    'Ceuta': ['51'],
    'Melilla': ['52'],
}

# Nombre de la medida en el Excel -> nombre de la columna que queremos
medidas = {
    'BI_ALVHEPCO_TV': 'n_alquileres',
    'ALQM2_LV_M_V': 'eur_m2_mediana',
    'ALQM2_LV_25_V': 'eur_m2_p25',
    'ALQM2_LV_75_V': 'eur_m2_p75',
    'ALQTBID12_M_V': 'eur_mes_mediana',
    'ALQTBID12_25_V': 'eur_mes_p25',
    'ALQTBID12_75_V': 'eur_mes_p75',
    'SLVM2_M_V': 'm2_mediana',
}
tipos = {'C': 'colectiva (pisos)', 'U': 'unifamiliar/rural'}


def getComunidad(provincia):
    for comunidad in comunidades:
        if provincia in comunidades[comunidad]:
            return comunidad
    return ''


def convertir(entrada, salida, columnas_id, nombre_provincia):
    with open(entrada, encoding='utf-8') as f:
        lector = csv.DictReader(f, delimiter=';')
        filas = list(lector)

    print('leidas', len(filas), 'filas de', entrada)
    guardadas = 0
    with open(salida, 'w', newline='', encoding='utf-8-sig') as f:
        escritor = csv.writer(f, delimiter=';')
        escritor.writerow(['provincia_cod', 'provincia', 'ccaa'] + columnas_id[2:]
                          + ['anio', 'tipologia'] + list(medidas.values()))
        for fila in filas:
            provincia = fila['CPRO']
            for anio in range(11, 25):
                for tipo in tipos:
                    valores = []
                    for medida in medidas:
                        valor = fila.get(medida + tipo + '_' + str(anio), '')
                        if valor != '':
                            valor = round(float(valor), 2)
                        valores.append(valor)
                    # si no hay ningun dato de alquiler no guardamos la fila
                    if valores[1:] == [''] * 7:
                        continue
                    escritor.writerow([provincia, fila[nombre_provincia], getComunidad(provincia)]
                                      + [fila[c] for c in columnas_id[2:]]
                                      + [2000 + anio, tipos[tipo]] + valores)
                    guardadas = guardadas + 1
    print(guardadas, 'filas guardadas en', salida)


def convertirTodo():
    convertir(os.path.join(DATOS, 'serpavi_municipios.csv'),
              os.path.join(DATOS, 'serpavi_alquiler_municipios.csv'),
              ['CPRO', 'NPRO', 'CUMUN', 'NMUN'], 'NPRO')
    convertir(os.path.join(DATOS, 'serpavi_provincias.csv'),
              os.path.join(DATOS, 'serpavi_alquiler_provincias.csv'),
              ['CPRO', 'LITPRO'], 'LITPRO')


if __name__ == '__main__':
    convertirTodo()
    print('alquileres SERPAVI guardados')
