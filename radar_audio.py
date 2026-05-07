#Radar Audio

import sounddevice as sd
import numpy as np
import time

# Configuración del escáner acústico
FRECUENCIA_MUESTREO = 44100
FRECUENCIA_OBJETIVO = 19500
TAMANO_BUFFER = 4096

# NUEVA LÓGICA DE FILTRADO (Stealth & Anti-Ruido)
UMBRAL_ABSOLUTO = 15.0  # El piso mínimo (evita que el polvo o estática disparen la alerta)
RATIO_RUIDO = 3.5       # La baliza debe ser 3.5 veces más ruidosa que el ambiente exacto de ese segundo
ultimo_aviso = 0
COOLDOWN_SEGUNDOS = 2.0

print("\n\033[95m[RULO SEC - SIGINT ACÚSTICO AVANZADO]\033[0m")
print("\033[90mInicializando análisis FFT con filtro de Relación Señal/Ruido (SNR)...\033[0m")
print(f"\033[96m[*] Escuchando espectro inaudible en: {FRECUENCIA_OBJETIVO} Hz\033[0m\n")

def procesar_audio(indata, frames, time_info, status):
    global ultimo_aviso
    if status:
        pass
    
    # Extraer audio y aplicar matemáticas
    audio_data = indata[:, 0]
    fft_data = np.abs(np.fft.rfft(audio_data))
    fft_freqs = np.fft.rfftfreq(TAMANO_BUFFER, 1 / FRECUENCIA_MUESTREO)
    
    # Encontrar nuestro objetivo (19.5 kHz)
    indice_objetivo = (np.abs(fft_freqs - FRECUENCIA_OBJETIVO)).argmin()
    magnitud_objetivo = fft_data[indice_objetivo]
    
    # ========================================================
    # EL FILTRO ANTI-FALSOS POSITIVOS (Análisis de Vecindario)
    # ========================================================
    # Tomamos muestras de las frecuencias justo antes y después de 19.5kHz
    # para saber qué tan ruidosa está la habitación en ese instante exacto.
    vecindario_izq = fft_data[indice_objetivo-6 : indice_objetivo-2]
    vecindario_der = fft_data[indice_objetivo+2 : indice_objetivo+6]
    ruido_ambiente = np.mean(np.concatenate((vecindario_izq, vecindario_der)))
    
    # Evitar divisiones por cero en el silencio absoluto
    if ruido_ambiente < 1.0:
        ruido_ambiente = 1.0

    tiempo_actual = time.time()
    
    # LA REGLA DE ORO:
    # 1. ¿Supera el piso de energía mínimo? Y
    # 2. ¿Es un pico anormal que destaca 3.5 veces sobre el ruido de fondo?
    if magnitud_objetivo > UMBRAL_ABSOLUTO and magnitud_objetivo > (ruido_ambiente * RATIO_RUIDO):
        if (tiempo_actual - ultimo_aviso) > COOLDOWN_SEGUNDOS:
            timestamp = time.strftime("%H:%M:%S")
            print(f"\033[91m[{timestamp}] ⚠ ¡ALERTA CRÍTICA! Baliza Ultrasónica Detectada.\033[0m")
            print(f"\033[93m[!] Proximidad confirmada (Air-Gap roto).\033[0m")
            print(f"\033[90m    -> Señal: {magnitud_objetivo:.1f} | Ruido Ambiente: {ruido_ambiente:.1f} | Multiplicador: {magnitud_objetivo/ruido_ambiente:.1f}x\033[0m\n")
            ultimo_aviso = tiempo_actual

try:
    with sd.InputStream(samplerate=FRECUENCIA_MUESTREO, channels=1, blocksize=TAMANO_BUFFER, callback=procesar_audio):
        while True:
            time.sleep(0.1)
except KeyboardInterrupt:
    print("\n\033[90m[*] Radar acústico apagado.\033[0m")
except Exception as e:
    print(f"\033[91m[ERROR] No se pudo acceder al micrófono: {e}\033[0m")