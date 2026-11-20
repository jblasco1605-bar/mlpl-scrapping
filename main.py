"""tecnojob: ¿compensa trabajar de X en la ciudad Y? (pagina web)

Es la misma consulta que consola.py, pero en una pagina web hecha con Streamlit.
La logica (scraping, limpieza y cruce de datos) esta en consulta.py.

Se puede arrancar de dos formas:
    - python3 main.py (o el boton Play): el propio fichero lanza Streamlit.
    - streamlit run main.py
Para usar el proyecto solo en la terminal, sin pagina web: python3 consola.py
"""
import json
import os
import sys

import pandas as pd
import streamlit as st

import consulta
import limpieza
from consulta import euros

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
# Pagina web
# ---------------------------------------------------------------------------
LOGO = os.path.join(consulta.CARPETA, 'logo', 'logo_tecnojob.png')
ICONO = os.path.join(consulta.CARPETA, 'logo', 'icono_tecnojob.png')

st.set_page_config(page_title='tecnojob', page_icon=ICONO, layout='wide')
st.image(LOGO, width=340)
st.write('¿Compensa trabajar aquí? Busca ofertas en **Ticjob** y **Tecnoempleo** y compara el '
         'sueldo neto con el alquiler de la ciudad (**SERPAVI**, **Numbeo** e **INE**).')

col1, col2 = st.columns(2)
puesto = col1.text_input('Puesto de trabajo', placeholder='Programador Python, Data Scientist...')
ciudad_escrita = col2.text_input('Ciudad española', placeholder='Madrid, Valencia, Sevilla...')
buscar = st.button('🔎 Buscar', type='primary')

with st.expander('Actualizar los datos de coste de vida (SERPAVI, INE y Numbeo)'):
    st.caption('Vuelve a ejecutar sus scrapers. Numbeo tarda alrededor de un minuto.')
    if st.button('Actualizar ahora'):
        with st.spinner('Actualizando...'):
            for mensaje in consulta.actualizarCosteVida(avisar=lambda texto: None):
                st.write(mensaje)

if buscar and (puesto.strip() == '' or ciudad_escrita.strip() == ''):
    st.error('Escribe un puesto y una ciudad.')

elif buscar:
    with st.spinner('Descargando ofertas de Ticjob y Tecnoempleo...'):
        r = consulta.hacerConsulta(puesto, ciudad_escrita, avisar=lambda texto: None)

    if r['error']:
        st.error(r['error'])
    else:
        lugar = r['lugar']
        for aviso in r['avisos']:
            st.warning(aviso)

        # --- Resumen ---
        st.header(f'{puesto} en {lugar["nombre"]}')
        st.caption(f'Provincia de {lugar["provincia"]} · {lugar["ccaa"]} · '
                   f'retención aplicada: {limpieza.RETENCION:.0%}')
        m1, m2, m3, m4 = st.columns(4)
        m1.metric('Ofertas con salario', len(r['ofertas']))
        m2.metric('Neto / mes', euros(r['neto']))
        m3.metric('Alquiler / mes', euros(r['alquiler']))
        m4.metric('Te queda / mes', euros(r['te_queda']))
        st.caption(f'Neto: {r["origen"]} · Alquiler: mediana SERPAVI {r["anio"]}')
        if r['veredicto']:
            tipo, texto = r['veredicto']
            if tipo == 'compensa':
                st.success('✅ ' + texto)
            elif tipo == 'justo':
                st.warning('⚖️ ' + texto)
            else:
                st.error('❌ ' + texto)

        # --- Ofertas ---
        st.subheader('Ofertas')
        ofertas = r['ofertas']
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
        st.caption(f'{r["sin_salario"]} ofertas del puesto descartadas por no publicar salario.')

        # --- Coste de vida ---
        st.subheader('Coste de vida')
        c1, c2, c3 = st.columns(3)
        c1.markdown(f'**SERPAVI (oficial)**  \nAlquiler mediano de un piso: '
                    f'{euros(r["alquiler"])}/mes ({r["anio"]})')
        if r['numbeo']:
            c2.markdown(f'**Numbeo**  \n1 hab. centro: {euros(r["numbeo"]["centro"])}/mes  \n'
                        f'1 hab. afueras: {euros(r["numbeo"]["afueras"])}/mes')
        else:
            c2.markdown('**Numbeo**  \nSin datos de esta ciudad.')
        if r['bruto_ine']:
            c3.markdown(f'**INE (oficial)**  \nSalario medio en {lugar["ccaa"]}: '
                        f'{euros(r["bruto_ine"])} brutos/año')

        st.subheader('Evolución del alquiler (SERPAVI)')
        st.line_chart(r['evolucion'], x='Año', y='Alquiler (€/mes)')

        st.subheader('¿En qué ciudad compensa más?')
        st.caption('Salario medio del INE de cada comunidad (neto) menos el alquiler de SERPAVI.')
        st.bar_chart(r['ranking'], x='Ciudad', y='Te queda', horizontal=True)
        st.dataframe(r['ranking'], hide_index=True)

        # --- Resultado completo en JSON (como en la practica de APIs REST) ---
        st.download_button('⬇️ Descargar el resultado en JSON',
                           json.dumps(consulta.resultadoJson(r), indent=4, ensure_ascii=False,
                                      default=float),
                           file_name='resultado.json', mime='application/json')
