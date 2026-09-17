#!/bin/bash
# Levanta las 5 terminales del entorno RuloSec en una sesión tmux
# Uso: ./iniciar_rulosec.sh
# Para volver a entrar después: tmux attach -t rulosec

SESION="rulosec"
DIR="/Users/victorsedano/mi_servidor_web"

# Si ya existe la sesión, solo reconectar
tmux has-session -t $SESION 2>/dev/null
if [ $? -eq 0 ]; then
    echo "La sesión '$SESION' ya existe. Reconectando..."
    tmux attach -t $SESION
    exit 0
fi

# Liberar el puerto 5001 antes de arrancar
kill -9 $(lsof -ti :5001) 2>/dev/null

# Ventana 1: Servidor Flask en puerto 5001
tmux new-session -d -s $SESION -n servidor -c "$DIR" \
    "python3.13 servidor.py"

# Ventana 2: Keylogger (tail al archivo de evidencia, filtrado)
tmux new-window -t $SESION -n keylogger -c "$DIR" \
    "sleep 1; tail -f evidencia_quetzalcoatl.txt | grep --line-buffered -i 'campo\|autofill'"

# Ventana 3: Biometría conductual (mouse) — directo del log del servidor via docker, o stdout local
tmux new-window -t $SESION -n biometria -c "$DIR" \
    "echo 'Biometría sale por stdout del servidor (ventana 1) o de docker compose logs.'; echo 'Si usas Docker: docker compose logs -f app_python | grep --line-buffered BIOMETRÍA'; bash"

# Ventana 4: Docker Compose (Tor + Flask)
tmux new-window -t $SESION -n docker -c "$DIR" \
    "echo 'Listo para levantar Docker. Ejecuta: docker compose up'; bash"

# Ventana 5: Air-gap / Radar acústico
tmux new-window -t $SESION -n airgap -c "$DIR" \
    "python3 radar_audio.py"

tmux select-window -t $SESION:servidor
tmux attach -t $SESION
