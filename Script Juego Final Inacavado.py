#!/usr/bin/env python3
import pigpio
import time
import threading
import requests

# --- CONFIGURACIÓN DE PINES ---
GPIO_RX = 17
GPIO_TX = 18
GPIO_BOTON = 2

# --- AJUSTES DE EMISIÓN ---
MODO_AUTOMATICO = True
FRECUENCIA = 38000
DUTY_CYCLE = 0.33

# --- Backend Configuracion ---
ID_JUGADOR = "6004"
CODIGO_A_ENVIAR = int(ID_JUGADOR)
URL_BASE = "http://192.168.0.100:3000"
URL_BACKEND = f"{URL_BASE}/game/hit"
ULTIM_IMPACTE = 0
ANTI_SPAM = 2
PARTIDA_ID = None

# --- AJUSTES DE RECEPCIÓN (MÁS FLEXIBLES) ---
HEADER_MARK = 9000
TOLERANCE = 0.4        # Margen de error del 40%
MIN_PULSE_WIDTH = 100  # Ignorar ruidos muy cortos

pi = pigpio.pi()
if not pi.connected:
    print("Error: pigpiod no está corriendo. Ejecuta 'sudo pigpiod'")
    exit()

pi.set_mode(GPIO_RX, pigpio.INPUT)
pi.set_pull_up_down(GPIO_RX, pigpio.PUD_UP)
pi.set_mode(GPIO_TX, pigpio.OUTPUT)
pi.set_mode(GPIO_BOTON, pigpio.INPUT)
pi.set_pull_up_down(GPIO_BOTON, pigpio.PUD_UP)

# Variables globales para RX
durations = []
recording = False
last_tick = None
start_time_rx = None

# --- OBTENIR PARTIDA ACTIVA AL INICI ---
def obtenir_partida_activa():
    global PARTIDA_ID
    try:
        # Busca la partida activa d'aquest jugador concret
        res = requests.get(f"{URL_BASE}/jugador/{ID_JUGADOR}/partida-activa",timeout=2)
        if res.status_code != 200:
            print("[BACKEND] No hi ha partida activa")
            PARTIDA_ID = None
            return
        data = res.json()

        partida = data.get("partida")
        if not partida:
            print("[BACKEND] No hi ha partida activa")
            PARTIDA_ID = None
            return

        if partida.get("estat") in ("pendent", "jugant"):
            PARTIDA_ID = partida.get("id_partida")
            print(f"[BACKEND] Partida trobada: {PARTIDA_ID}")
        else:
            PARTIDA_ID = None
    except requests.exceptions.RequestException as e:
        print(f"[BACKEND] Error connexió: {e}")
        PARTIDA_ID = None

# --- MOTOR DE EMISIÓN (WAVES) ---

def generar_onda_ir(frecuencia, duty, duracion_us):
    if duracion_us <= 0: return None
    periodo_us = 1000000.0 / frecuencia
    on_us = int(periodo_us * duty)
    off_us = int(periodo_us - on_us)
    ciclos = int(duracion_us / periodo_us)
    wf = []
    for _ in range(ciclos):
        wf.append(pigpio.pulse(1 << GPIO_TX, 0, on_us))
        wf.append(pigpio.pulse(0, 1 << GPIO_TX, off_us))
    pi.wave_add_generic(wf)
    return pi.wave_create()

def generar_onda_silencio(duracion_us):
    if duracion_us <= 0: return None
    wf = [pigpio.pulse(0, 0, int(duracion_us))]
    pi.wave_add_generic(wf)
    return pi.wave_create()

print("Inicializando hardware IR...")
pi.wave_clear()

# Pre-generación de formas de onda NEC
W_HEADER_MARK  = generar_onda_ir(FRECUENCIA, DUTY_CYCLE, 9000)
W_HEADER_SPACE = generar_onda_silencio(4500)
W_BIT_MARK     = generar_onda_ir(FRECUENCIA, DUTY_CYCLE, 560)
W_ZERO_SPACE   = generar_onda_silencio(560)
W_ONE_SPACE    = generar_onda_silencio(1690)

def send_nec(code):
    cadena = [W_HEADER_MARK, W_HEADER_SPACE]
    for i in range(32):
        cadena.append(W_BIT_MARK)
        if code & (1 << (31 - i)):
            cadena.append(W_ONE_SPACE)
        else:
            cadena.append(W_ZERO_SPACE)
    cadena.append(W_BIT_MARK)

    print(f"\n[TX] >> Enviando: 0x{code:08X}")
    pi.wave_chain(cadena)
    while pi.wave_tx_busy():
        time.sleep(0.01)

# --- MOTOR DE RECEPCIÓN (OPTIMIZADO) ---

def cb_receptor(gpio, level, tick):
    global last_tick, durations, recording, start_time_rx
    if last_tick is None:
        last_tick = tick
        return

    delta = pigpio.tickDiff(last_tick, tick)
    last_tick = tick

    # Iniciar grabación si detectamos un pulso largo (Header)
    if not recording and delta > 8000:
        durations = [delta]
        recording = True
        start_time_rx = time.time()
    elif recording:
        durations.append(delta)
        if (time.time() - start_time_rx) > 0.15: # Fin de trama tras 150ms
            recording = False

cb_handle = pi.callback(GPIO_RX, pigpio.EITHER_EDGE, cb_receptor)

def enviar_impacte(atacant_id):
    global ULTIM_IMPACTE

    if PARTIDA_ID is None:
        return

    if time.time() - ULTIM_IMPACTE < ANTI_SPAM:
        return

    ULTIM_IMPACTE = time.time()

    try:
        requests.post(
            URL_BACKEND,
            json={
                "attacker_id": atacant_id,
                "victim_id": ID_JUGADOR,
                "partida": PARTIDA_ID
            },
            timeout=0.5
        )
        print("[BACKEND] Impacte enviat")
    except Exception as e:
        print("[BACKEND] Error:", e)

def hilo_procesador_ir():
    global durations, recording
    while True:
        if not recording and durations:
            # Limpieza rápida: filtrar ruidos y copiar
            raw_data = [d for d in durations if d > MIN_PULSE_WIDTH]
            durations.clear()

            # Buscamos el inicio de la trama NEC (Header Mark)
            if len(raw_data) >= 64:
                start_idx = -1
                for i in range(len(raw_data)):
                    if abs(raw_data[i] - HEADER_MARK) < HEADER_MARK * TOLERANCE:
                        start_idx = i
                        break

                if start_idx != -1:
                    bits = ""
                    # Analizamos los espacios (índices impares tras el mark de cada bit)
                    # La estructura es: [HeaderMark, HeaderSpace, Bit1Mark, Bit1Space...]
                    for j in range(start_idx + 2, len(raw_data) - 1, 2):
                        space = raw_data[j+1]
                        if 300 < space < 1000:   # Es un 0
                            bits += "0"
                        elif 1100 < space < 2500: # Es un 1
                            bits += "1"

                    if len(bits) >= 32:
                        try:
                            val = int(bits[:32], 2)
                            atacant_id = str(val)
                            print(f"\n[RX] << Capturado de jugador: {atacant_id}")
                            threading.Thread(
                                target=enviar_impacte,
                                args=(atacant_id,),
                                daemon=True
                            ).start()
                        except:
                            pass
        time.sleep(0.05)

# --- BUCLE PRINCIPAL ---
try:

    obtenir_partida_activa()

    t_procesador = threading.Thread(target=hilo_procesador_ir, daemon=True)
    t_procesador.start()

    print("--- SISTEMA IR COMPLETO ---")
    print("Lectura activa. Emisión automática: " + ("SÍ" if MODO_AUTOMATICO else "NO"))

    ultimo_envio_auto = time.time()

    while True:
        if PARTIDA_ID is None:
            obtenir_partida_activa()
            time.sleep(1)
            continue

        # Enviar automáticamente cada segundo
        if MODO_AUTOMATICO and (time.time() - ultimo_envio_auto >= 5.0):
            send_nec(CODIGO_A_ENVIAR)
            ultimo_envio_auto = time.time()

        # Enviar al pulsar botón
        if pi.read(GPIO_BOTON) == 0:
            send_nec(CODIGO_A_ENVIAR)
            while pi.read(GPIO_BOTON) == 0:
                time.sleep(0.1)

        time.sleep(0.05)

except KeyboardInterrupt:
    print("\nDeteniendo...")
finally:
    pi.wave_clear()
    pi.stop()