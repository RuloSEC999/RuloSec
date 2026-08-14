#!/usr/bin/env bash
#
# lab-cia-sim.sh — Réplica del segmento LAB-CIA con network namespaces
#
# Reproduce el laboratorio de la Práctica 01 SIN necesidad de VirtualBox ni
# virtualización por hardware: dos namespaces de red unidos por un veth hacen
# de "Kali" y "Debian". Sirve para validar las reglas del IDS antes de
# desplegarlas en las VMs de verdad.
#
# Con este script se validaron las reglas de lab/reglas/lab-cia.rules:
# tráfico real de Nmap, capturado con tcpdump y procesado por Snort y Suricata.
#
#   sudo ./lab-cia-sim.sh up        # levantar el laboratorio
#   sudo ./lab-cia-sim.sh scan      # lanzar el reconocimiento y capturar
#   sudo ./lab-cia-sim.sh ids       # pasar la captura por Suricata y Snort
#   sudo ./lab-cia-sim.sh down      # desmontar
#
# Requiere root (CAP_NET_ADMIN) y: iproute2 nmap tcpdump suricata snort python3
#
set -Eeuo pipefail

IP_KALI="192.168.100.20"
IP_DEBIAN="192.168.100.10"
RED="192.168.100.0/24"
OUT="${OUT:-/tmp/lab-cia}"
REGLAS="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/reglas/lab-cia.rules"

c_reset=$'\033[0m'; c_ok=$'\033[32m'; c_hi=$'\033[36m'; c_err=$'\033[31m'
log() { printf '%s==>%s %s\n' "$c_hi" "$c_reset" "$*"; }
ok()  { printf '%s  ok%s %s\n' "$c_ok" "$c_reset" "$*"; }
die() { printf '%s ERR%s %s\n' "$c_err" "$c_reset" "$*" >&2; exit 1; }

(( EUID == 0 )) || die "hace falta root para crear namespaces de red"

up() {
  down 2>/dev/null || true
  log "Creando el segmento LAB-CIA"
  ip netns add kali; ip netns add debian
  ip link add veth-k type veth peer name veth-d
  ip link set veth-k netns kali; ip link set veth-d netns debian
  ip netns exec kali   ip addr add "$IP_KALI/24"   dev veth-k
  ip netns exec debian ip addr add "$IP_DEBIAN/24" dev veth-d
  for ns in kali debian; do ip netns exec "$ns" ip link set lo up; done
  ip netns exec kali   ip link set veth-k up
  ip netns exec debian ip link set veth-d up

  mkdir -p "$OUT"
  # Servicios expuestos: los banners son la fuga de confidencialidad a detectar.
  cat > "$OUT/servicios.py" <<'PY'
import socket, threading
BANNERS = {
    21:   b"220 ProFTPD Server (Debian)\r\n",
    22:   b"SSH-2.0-OpenSSH_9.2p1 Debian-2\r\n",
    80:   b"HTTP/1.1 200 OK\r\nServer: Apache/2.4.57 (Debian)\r\n\r\n",
    3306: b"\x4a\x00\x00\x00\x0a8.0.34-Debian\x00",
}
def serve(port):
    s = socket.socket(); s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("0.0.0.0", port)); s.listen(16)
    while True:
        try:
            c, _ = s.accept()
            try: c.sendall(BANNERS[port])
            except Exception: pass
            c.close()
        except Exception: break
for p in BANNERS: threading.Thread(target=serve, args=(p,), daemon=True).start()
threading.Event().wait()
PY
  ip netns exec debian python3 "$OUT/servicios.py" & echo $! > "$OUT/servicios.pid"
  sleep 2
  ok "kali=$IP_KALI  debian=$IP_DEBIAN  (servicios 21/22/80/3306 arriba)"
}

scan() {
  ip netns list | grep -q '^kali' || die "el laboratorio no está levantado (usa 'up')"
  mkdir -p "$OUT"
  log "Capturando en el Debian y lanzando reconocimiento desde Kali"
  ip netns exec debian tcpdump -i veth-d -w "$OUT/recon.pcap" -q 2>/dev/null & local t=$!
  sleep 2
  ip netns exec kali nmap -sn "$RED"                              >"$OUT/nmap-sn.txt"  2>&1 || true
  ip netns exec kali nmap -sS -p 1-1000 "$IP_DEBIAN"              >"$OUT/nmap-sS.txt"   2>&1 || true
  ip netns exec kali nmap -sV -p 21,22,80,3306 "$IP_DEBIAN"       >"$OUT/nmap-sV.txt"  2>&1 || true
  for s in sN sF sX; do
    ip netns exec kali nmap "-$s" -p 21,22,80,3306 "$IP_DEBIAN"   >"$OUT/nmap-$s.txt"  2>&1 || true
  done
  sleep 2; kill "$t" 2>/dev/null || true; wait "$t" 2>/dev/null || true
  ok "captura en $OUT/recon.pcap ($(tcpdump -r "$OUT/recon.pcap" -qn 2>/dev/null | wc -l) paquetes)"
}

ids() {
  [[ -f "$OUT/recon.pcap" ]] || die "no hay captura; ejecuta 'scan' primero"
  [[ -f "$REGLAS" ]] || die "no encuentro las reglas: $REGLAS"

  # -k none: en veth el checksum offload invalida los checksums y ambos IDS
  # descartarían los paquetes en silencio. Es EL error clásico al probar con
  # capturas: cero alertas y ninguna pista del porqué.
  log "Suricata"
  rm -rf "$OUT/suricata"; mkdir -p "$OUT/suricata"
  suricata -r "$OUT/recon.pcap" -S "$REGLAS" -l "$OUT/suricata" -k none \
    --set vars.address-groups.HOME_NET="[$IP_DEBIAN/32]" \
    --set vars.address-groups.EXTERNAL_NET="[$IP_KALI/32]" >/dev/null 2>&1 || true
  resumen "$OUT/suricata/fast.log"

  log "Snort"
  cat > "$OUT/snort-lab.conf" <<EOF
var HOME_NET $IP_DEBIAN/32
var EXTERNAL_NET $IP_KALI/32
include /etc/snort/classification.config
include /etc/snort/reference.config
include $REGLAS
EOF
  snort -q -r "$OUT/recon.pcap" -c "$OUT/snort-lab.conf" -A console -k none \
    >"$OUT/snort.log" 2>/dev/null || true
  resumen "$OUT/snort.log"
}

resumen() {
  local f="$1"
  [[ -f "$f" ]] || { echo "   (sin salida)"; return; }
  grep -oP '\[\*\*\] \[\d+:\d+:\d+\] \K[^\[]+' "$f" 2>/dev/null \
    | sed 's/ *$//' | sort | uniq -c | sort -rn | sed 's/^/   /'
  echo "   ---- total: $(grep -c '\[\*\*\]' "$f" 2>/dev/null || echo 0) alertas"
}

down() {
  [[ -f "$OUT/servicios.pid" ]] && { kill "$(cat "$OUT/servicios.pid")" 2>/dev/null || true; rm -f "$OUT/servicios.pid"; }
  ip netns del kali   2>/dev/null || true
  ip netns del debian 2>/dev/null || true
  ok "laboratorio desmontado"
}

case "${1:-}" in
  up) up ;; scan) scan ;; ids) ids ;; down) down ;;
  all) up; scan; ids ;;
  *) awk 'NR>1 && /^#/ { sub(/^# ?/, ""); print; next } NR>1 { exit }' "$0"; exit 1 ;;
esac
