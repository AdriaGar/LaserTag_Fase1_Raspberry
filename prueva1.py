#!/usr/bin/env python3
import pigpio
import time

# Pines
GPIO_TX = 18  # Emisor KY-005
GPIO_RX = 17  # Receptor KY-022

# Parámetros PWM (38 kHz, 50 % duty)
FREQ = 38000
DUTY = 0.5

# Código NEC que se enviará
CODE_TO_SEND = 0xC0FFD02F

# Timings NEC (en segundos)
MARK = 560e-6
ONE_SPACE = 1690e-6
ZERO_SPACE = 560e-6
HEADER_MARK = 9000e-6
HEADER_SPACE = 4500e-6
TRAILER_MARK = 560e-6

# Inicializar pigpio
pi = pigpio.pi()
if not pi.connected:
    print("❌ No se pudo conectar con pigpiod (ejecuta 'sudo pigpiod')")
    exit()

pi.set_mode(GPIO_TX, pigpio.OUTPUT)
pi.set_mode(GPIO_RX, pigpio.INPUT)
pi.set_pull_up_down(GPIO_RX, pigpio.PUD_UP)

# --- Emisión NEC ---
def send_mark(duration):
    pi.hardware_PWM(GPIO_TX, FREQ, int(DUTY * 1e6))
    time.sleep(duration)
    pi.hardware_PWM(GPIO_TX, 0, 0)

def send_space(duration):
    pi.hardware_PWM(GPIO_TX, 0, 0)
    time.sleep(duration)

def send_nec(code):
    send_mark(HEADER_MARK)
    send_space(HEADER_SPACE)
    for i in range(32):
        send_mark(MARK)
        if code & (1 << (31 - i)):
            send_space(ONE_SPACE)
        else:
            send_space(ZERO_SPACE)
    send_mark(TRAILER_MARK)
    send_space(0.05)  # pequeña pausa

# --- Captura cruda ---
def capture_raw(duration=0.3):
    """Captura los pulsos crudos del receptor durante 'duration' segundos"""
    start = time.time()
    last_state = pi.read(GPIO_RX)
    last_time = time.time()
    pulses = []

    while time.time() - start < duration:
        curr = pi.read(GPIO_RX)
        if curr != last_state:
            pulse_len = (time.time() - last_time) * 1_000_000  # μs
            pulses.append(int(pulse_len))
            last_state = curr
            last_time = time.time()

    return pulses

# --- Decodificación básica NEC ---
def try_decode_nec(pulses):
    bits = []
    for p in pulses:
        if 400 < p < 800:
            bits.append('0')
        elif 1200 < p < 2000:
            bits.append('1')
    if len(bits) >= 32:
        value = int(''.join(bits[:32]), 2)
        return f"0x{value:08X}"
    return None

# --- Bucle principal ---
try:
    print(f"🔹 Enviando código 0x{CODE_TO_SEND:08X} y mostrando recepción en tiempo real.\nCtrl+C para detener.\n")
    while True:
        send_nec(CODE_TO_SEND)
        pulses = capture_raw(0.2)
        if len(pulses) > 0:
            hex_code = try_decode_nec(pulses)
            if hex_code:
                print(f"📡 Posible NEC recibido: {hex_code}")
                if hex_code == f"0x{CODE_TO_SEND:08X}":
                    print("✅ Coincidencia detectada, deteniendo emisión.")
                    break
            else:
                # Muestra los primeros pulsos en hexadecimal (duraciones)
                sample = " ".join([hex(p) for p in pulses[:10]])
                print(f"📶 Señal cruda ({len(pulses)} pulsos): {sample}")
        time.sleep(0.1)

except KeyboardInterrupt:
    print("\n🛑 Interrumpido por el usuario.")

finally:
    pi.hardware_PWM(GPIO_TX, 0, 0)
    pi.stop()