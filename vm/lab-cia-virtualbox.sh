#!/usr/bin/env bash
#
# lab-cia-virtualbox.sh — Laboratorio LAB-CIA en VirtualBox
#
# Práctica 01 "Identificación de Riesgos de Confidencialidad"
# ICSA-014 Manejo de Datos para la Ciberseguridad — FCC/BUAP, Otoño 2026
#
# Crea las dos VMs de la práctica con la configuración de red exacta:
#
#     Debian 12  (defensa)  ── Adaptador 1: NAT
#     Kali Linux (ataque)   ── Adaptador 2: Red interna "LAB-CIA", promiscuo
#
# NO instala el sistema por ti: la práctica pide capturas de pantalla de cada
# paso del instalador, así que ese recorrido lo haces tú. Lo que automatiza es
# la parte tediosa y donde todo el mundo se equivoca — el modo promiscuo del
# adaptador 2, sin el cual Snort y Suricata no ven ni un paquete.
#
#     ./lab-cia-virtualbox.sh --iso-debian ~/Descargas/debian-12.iso \
#                             --iso-kali   ~/Descargas/kali.iso
#
set -Eeuo pipefail

#--- Parámetros de la práctica ------------------------------------------------
INTNET="LAB-CIA"          # nombre de la red interna (imagen 4 del enunciado)
VM_DEBIAN="LAB-CIA-Debian"
VM_KALI="LAB-CIA-Kali"
RAM_DEBIAN="2048"
RAM_KALI="4096"
CPUS="2"
DISK_DEBIAN_GB="25"
DISK_KALI_GB="60"
ISO_DEBIAN=""
ISO_KALI=""
ONLY=""
DRY_RUN="0"

c_reset=$'\033[0m'; c_ok=$'\033[32m'; c_warn=$'\033[33m'; c_err=$'\033[31m'; c_hi=$'\033[36m'
log()  { printf '%s==>%s %s\n' "$c_hi"  "$c_reset" "$*"; }
ok()   { printf '%s  ok%s %s\n' "$c_ok"  "$c_reset" "$*"; }
warn() { printf '%s  !!%s %s\n' "$c_warn" "$c_reset" "$*" >&2; }
die()  { printf '%s ERR%s %s\n' "$c_err" "$c_reset" "$*" >&2; exit 1; }

usage() {
  awk 'NR>1 && /^#/ { sub(/^# ?/, ""); print; next } NR>1 { exit }' "$0"
  cat <<EOF

Opciones:
  --iso-debian RUTA    ISO de Debian 12 (netinst o DVD)
  --iso-kali RUTA      ISO de Kali (Installer AMD64)
  --only {debian|kali} Crear sólo una de las dos VMs
  --intnet NOMBRE      Nombre de la red interna      (def: $INTNET)
  --cpus N             vCPUs por VM                  (def: $CPUS)
  --dry-run            Enseñar los comandos sin ejecutarlos
  -h, --help           Esta ayuda
EOF
}

while (($#)); do
  case "$1" in
    --iso-debian) ISO_DEBIAN="${2:?}"; shift 2 ;;
    --iso-kali)   ISO_KALI="${2:?}";   shift 2 ;;
    --only)       ONLY="${2:?}";       shift 2 ;;
    --intnet)     INTNET="${2:?}";     shift 2 ;;
    --cpus)       CPUS="${2:?}";       shift 2 ;;
    --dry-run)    DRY_RUN="1";         shift ;;
    -h|--help)    usage; exit 0 ;;
    *) die "opción desconocida: $1  (usa --help)" ;;
  esac
done

case "$ONLY" in ""|debian|kali) ;; *) die "--only debe ser 'debian' o 'kali'" ;; esac

command -v VBoxManage >/dev/null 2>&1 \
  || die "no encuentro VBoxManage. Instala VirtualBox y asegúrate de que esté en el PATH.
    macOS: suele estar en /usr/local/bin o /Applications/VirtualBox.app/Contents/MacOS
    Windows: usa Git Bash y añade 'C:\\Program Files\\Oracle\\VirtualBox' al PATH"

vbox() {
  if [[ "$DRY_RUN" == "1" ]]; then printf '    VBoxManage %s\n' "$*"; else VBoxManage "$@"; fi
}

# Crea y configura una VM. $1=nombre $2=ram $3=discoGB $4=iso $5=ostype
crear_vm() {
  local name="$1" ram="$2" disk_gb="$3" iso="$4" ostype="$5"

  [[ -n "$iso" ]] || die "falta la ISO para $name (usa --iso-debian / --iso-kali)"
  [[ -f "$iso" ]] || die "no existe la ISO: $iso"

  if VBoxManage showvminfo "$name" >/dev/null 2>&1; then
    warn "la VM '$name' ya existe; la salto."
    warn "Para rehacerla: VBoxManage unregistervm '$name' --delete"
    return 0
  fi

  log "Creando $name"
  vbox createvm --name "$name" --ostype "$ostype" --register

  # Red: adaptador 1 NAT (internet), adaptador 2 red interna aislada.
  # nicpromisc2=allow-all es lo que permite al IDS ver tráfico ajeno.
  vbox modifyvm "$name" \
    --memory "$ram" --cpus "$CPUS" \
    --vram 128 --graphicscontroller vmsvga \
    --nic1 nat \
    --nic2 intnet --intnet2 "$INTNET" --nicpromisc2 allow-all \
    --nictype1 82540EM --nictype2 82540EM \
    --audio-driver none \
    --boot1 dvd --boot2 disk --boot3 none --boot4 none \
    --rtcuseutc on --ioapic on

  local folder disk
  if [[ "$DRY_RUN" == "1" ]]; then
    disk="<carpeta-de-la-vm>/$name.vdi"
  else
    folder="$(VBoxManage showvminfo "$name" --machinereadable \
              | sed -n 's/^CfgFile="\(.*\)"$/\1/p')"
    folder="$(dirname "$folder")"
    disk="$folder/$name.vdi"
  fi

  log "Disco de ${disk_gb} GB"
  vbox createmedium disk --filename "$disk" --size $((disk_gb * 1024)) --format VDI

  vbox storagectl "$name" --name "SATA" --add sata --controller IntelAhci --portcount 2
  vbox storageattach "$name" --storagectl "SATA" --port 0 --device 0 \
    --type hdd --medium "$disk"

  vbox storagectl "$name" --name "IDE" --add ide
  vbox storageattach "$name" --storagectl "IDE" --port 0 --device 0 \
    --type dvddrive --medium "$iso"

  ok "$name lista — NAT + red interna '$INTNET' (promiscuo: permitir todo)"
}

#--- Ejecución ----------------------------------------------------------------
cat <<EOF
  LAB-CIA — Práctica 01, FCC/BUAP
  --------------------------------
  red interna   $INTNET   (adaptador 2, modo promiscuo: permitir todo)
  Debian 12     $VM_DEBIAN   ${RAM_DEBIAN} MB / ${DISK_DEBIAN_GB} GB
  Kali          $VM_KALI     ${RAM_KALI} MB / ${DISK_KALI_GB} GB
EOF
[[ "$DRY_RUN" == "1" ]] && echo "  (dry-run: no se ejecuta nada)"
echo

# El enunciado dice "Primero instala Debian", así que ese es el orden.
if [[ "$ONLY" != "kali" ]]; then
  crear_vm "$VM_DEBIAN" "$RAM_DEBIAN" "$DISK_DEBIAN_GB" "$ISO_DEBIAN" "Debian_64"
fi
if [[ "$ONLY" != "debian" ]]; then
  crear_vm "$VM_KALI" "$RAM_KALI" "$DISK_KALI_GB" "$ISO_KALI" "Debian_64"
fi

cat <<EOF

  Siguiente paso — arranca y recorre el instalador capturando cada pantalla:

    VBoxManage startvm "$VM_DEBIAN"     # primero Debian
    VBoxManage startvm "$VM_KALI"       # después Kali

  Datos que pide el enunciado para la VM de Kali (Paso 3):
    Nombre de la máquina  LAB-CIA
    Dominio               datoskali.org
    Nombre completo       Atacante Kali
    Usuario               atacante
    Contraseña            12345
    Software              Xfce + "default -- recommended tools"

  Recuerda: cada captura debe llevar de fondo tu escritorio con fecha y hora.

  Comprobaciones de los Pasos 5 y 7, ya dentro de las VMs:
    Debian:  ip link show
             ip addr show enp0s8
             ping -c 4 google.com
    Kali:    nmcli device status
             ip a
EOF
