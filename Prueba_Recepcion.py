#!/usr/bin/env python3
import pigpio
import time

GPIO_RX = 17
THRESHOLD = 800  # umbral entre '0' y '1' en microsegundos (entre 560 y 1690 típicamente)
HEADER_MARK = 9000
HEADER_SPACE = 4500
TOLERANCE = 0.3

pi = pigpio.pi()
if not pi.connected:
    print("No se pudo conectar con pigpio.")
    exit()

pi.set_mode(GPIO_RX, pigpio.INPUT)
pi.set_pull_up_down(GPIO_RX, pigpio.PUD_UP)

durations = []
recording = False
last_tick = None
start_time = None

def cb(gpio, level, tick):
    global last_tick, durations, recording, start_time
    if last_tick is None:
        last_tick = tick
        return
    delta = (tick - last_tick) & 0xFFFFFFFF
    last_tick = tick

    if not recording and delta > 8000:  # detecta encabezado
        durations = [delta]
        recording = True
        start_time = time.time()
    elif recording:
        durations.append(delta)
        if (time.time() - start_time) > 0.12:  # silencio 120 ms
            recording = False

cb_handle = pi.callback(GPIO_RX, pigpio.EITHER_EDGE, cb)

try:
    print("Apunta el mando hacia el receptor y pulsa un botón (Ctrl+C para salir):")
    while True:
        if not recording and durations:
            # analizar
            code = durations.copy()
            durations.clear()
            print(f"\nCapturados {len(code)} pulsos.")
            # buscar encabezado típico NEC
            if abs(code[0] - HEADER_MARK) < HEADER_MARK*TOLERANCE and abs(code[1] - HEADER_SPACE) < HEADER_SPACE*TOLERANCE:
                bits = ""
                for i in range(2, len(code)-1, 2):
                    mark, space = code[i], code[i+1]
                    if abs(space - 560) < 300:
                        bits += "0"
                    elif abs(space - 1690) < 600:
                        bits += "1"
                # agrupar en bytes
                if len(bits) % 8 == 0 and len(bits) >= 32:
                    val = int(bits, 2)
                    hex_str = hex(val)
                    print(f"Bits: {bits}")
                    print(f"Hex : {hex_str}")
                else:
                    print("No coincide con NEC estándar (longitud irregular).")
            else:
                print("Encabezado no coincide con NEC.")
            print("\nListo para otra captura...\n")
        time.sleep(0.05)

except KeyboardInterrupt:
    print("\nDetenido por el usuario.")

finally:
    cb_handle.cancel()
    pi.stop()