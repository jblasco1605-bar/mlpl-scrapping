# Respaldo de tecnoempleo.py: si la web bloquea a requests (control anti-bots),
# abrimos un Chrome de verdad con Selenium, esperamos a que cargue y le pasamos
# el HTML al mismo codigo de BeautifulSoup de tecnoempleo.py.
import time
from urllib.parse import quote_plus

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException, WebDriverException
from selenium.webdriver.common.by import By

import tecnoempleo


def abrirNavegador(visible=False):
    # Sin ventana (headless) para que la app no abra Chrome en cada busqueda
    opciones = webdriver.ChromeOptions()
    if not visible:
        opciones.add_argument('--headless=new')
    opciones.add_argument('--window-size=1280,2000')
    driver = webdriver.Chrome(options=opciones)
    driver.set_page_load_timeout(30)
    return driver


def cerrarCookies(driver):
    # Usamos try-except por si algun dia no sale el aviso de cookies
    try:
        boton = driver.find_element(
            By.XPATH, "//button[contains(text(), 'Aceptar')] | //a[contains(text(), 'Aceptar')]")
        boton.click()
        time.sleep(1)
    except (NoSuchElementException, WebDriverException):
        pass


def scrapear(puesto, max_paginas=3, visible=False):
    driver = abrirNavegador(visible)
    filas = []
    urls_vistas = []
    try:
        driver.get(tecnoempleo.url + '?te=' + quote_plus(puesto))
        time.sleep(3)   # que cargue la pagina y pase el control de seguridad
        cerrarCookies(driver)
        for pagina in range(1, max_paginas + 1):
            print('Tecnoempleo (Selenium), pagina', pagina)
            soup = BeautifulSoup(driver.page_source, 'html.parser')
            filas = filas + tecnoempleo.leerOfertas(soup, puesto, urls_vistas)
            # Pasar a la siguiente pagina; si no hay boton, hemos terminado
            try:
                driver.find_element(By.PARTIAL_LINK_TEXT, 'Siguiente').click()
                time.sleep(3)
            except (NoSuchElementException, WebDriverException):
                break
    finally:
        driver.quit()   # cerramos el navegador aunque haya habido un error
    if len(filas) == 0:
        raise RuntimeError('Tecnoempleo (Selenium) no ha devuelto ofertas')
    return filas


if __name__ == '__main__':
    filas = scrapear('analista de datos', visible=True)
    tecnoempleo.guardar(filas)
    print(len(filas), 'ofertas guardadas en datos/tecnoempleo.csv')
