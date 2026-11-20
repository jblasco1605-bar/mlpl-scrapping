"""tecnojob en la terminal (sin pagina web).

Ejecutar desde la carpeta del proyecto (o con el boton Play de VS Code / Spyder):
    python3 consola.py

Pide un puesto y una ciudad, muestra todo el resultado en la terminal y lo
guarda en resultado.json.
"""
import json
import os

import pandas as pd

import consulta
import limpieza
from consulta import euros

# Para que las tablas de pandas se vean enteras en la terminal
pd.set_option('display.width', 200)
pd.set_option('display.max_columns', 20)
pd.set_option('display.max_colwidth', 45)


def titulo(texto):
    print()
    print(texto.upper())
    print('-' * len(texto))


def mostrarResultado(r):
    lugar = r['lugar']
    titulo(f'{r["puesto"]} en {lugar["nombre"]}')
    print(f'Provincia de {lugar["provincia"]} · {lugar["ccaa"]} · '
          f'retención aplicada: {limpieza.RETENCION:.0%}')
    for aviso in r['avisos']:
        print('AVISO:', aviso)

    titulo('Resumen')
    print('Ofertas con salario:', len(r['ofertas']))
    print('Neto / mes:         ', euros(r['neto']), f'({r["origen"]})')
    print('Alquiler / mes:     ', euros(r['alquiler']), f'(mediana SERPAVI {r["anio"]})')
    print('Te queda / mes:     ', euros(r['te_queda']))
    if r['veredicto']:
        print('>>>', r['veredicto'][1])

    titulo('Ofertas')
    if len(r['ofertas']) == 0:
        print('No hay ofertas de este puesto con salario publicado en la zona.')
        print('Se usa el salario medio del INE como referencia.')
    else:
        print(r['ofertas'][['Fuente', 'Puesto', 'Empresa', 'Coincide en', 'Bruto anual',
                            'Neto mensual']].to_string(index=False))
        print('\nEnlaces:')
        for i, enlace in enumerate(r['ofertas']['Enlace']):
            print(f'  {i + 1}. {enlace}')
    print(f'\n{r["sin_salario"]} ofertas del puesto descartadas por no publicar salario.')

    titulo('Coste de vida')
    print('SERPAVI (oficial): alquiler mediano de un piso', euros(r['alquiler']), f'({r["anio"]})')
    if r['numbeo']:
        print('Numbeo: 1 hab. centro', euros(r['numbeo']['centro']),
              '· 1 hab. afueras', euros(r['numbeo']['afueras']))
    else:
        print('Numbeo: sin datos de esta ciudad.')
    if r['bruto_ine']:
        print(f'INE (oficial): salario medio en {lugar["ccaa"]}', euros(r['bruto_ine']), 'brutos/año')

    titulo('Evolución del alquiler (SERPAVI)')
    print(r['evolucion'].to_string(index=False))

    titulo('¿En qué ciudad compensa más? (neto INE - alquiler SERPAVI)')
    print(r['ranking'].to_string(index=False))


# ---------------------------------------------------------------------------
# Programa principal
# ---------------------------------------------------------------------------
if __name__ == '__main__':
    print('=' * 46)
    print('  tecnojob · ofertas IT y coste de vida')
    print('  ¿Compensa trabajar aquí?')
    print('=' * 46)
    seguir = 's'
    while seguir == 's':
        puesto = input('\nPuesto de trabajo (ej. Programador Python): ').strip()
        ciudad = input('Ciudad española (ej. Valencia): ').strip()
        if puesto == '' or ciudad == '':
            print('Escribe un puesto y una ciudad.')
            continue

        resultado = consulta.hacerConsulta(puesto, ciudad)
        if resultado['error']:
            print(resultado['error'])
        else:
            mostrarResultado(resultado)
            # Guardamos el resultado en JSON (como en la practica de APIs REST)
            ruta = os.path.join(consulta.CARPETA, 'resultado.json')
            with open(ruta, 'w', encoding='utf-8') as f:
                f.write(json.dumps(consulta.resultadoJson(resultado), indent=4,
                                   ensure_ascii=False, default=float))
            print('\nResultado guardado en', ruta)

        seguir = input('\n¿Otra consulta? (s/n): ').strip().lower()
    print('¡Hasta luego!')
