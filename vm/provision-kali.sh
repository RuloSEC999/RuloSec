#!/usr/bin/env bash
#
# provision-kali.sh — Instala una VM de Kali Linux desde cero, desatendida.
#
# Descarga el instalador netinst oficial, verifica la firma GPG de Kali y el
# SHA256 de la imagen, y lanza una instalación sin interacción usando preseed.
# No hay ni un solo clic en un instalador gráfico.
#
#   ./provision-kali.sh --backend qemu     # portable, sólo necesita QEMU
#   ./provision-kali.sh --backend libvirt  # Linux con KVM/libvirt
#
# La contraseña NUNCA se escribe en el repo ni en la línea de comandos:
# se pide por stdin o se toma de la variable de entorno KALI_PASSWORD.
#
set -Eeuo pipefail

#--- Valores por defecto ------------------------------------------------------
BACKEND="qemu"
VM_NAME="kali"
DISK_GB="60"
RAM_MB="4096"
CPUS="2"
USERNAME="kali"
HOSTNAME_="kali"
TIMEZONE="America/Mexico_City"
LOCALE="es_MX.UTF-8"
KEYMAP="es"
# kali-linux-default = el set de herramientas "clásico" (~2.5 GB).
# Alternativas: kali-linux-headless (sin escritorio),
#               kali-linux-everything (todo, ~15 GB y horas de descarga).
PACKAGES="kali-linux-default kali-desktop-xfce openssh-server"
APT_PROXY=""
ISO_PATH=""
WORKDIR="${PWD}/.kali-build"
ASSUME_YES="0"

# Clave de firma del archivo de Kali Linux.
# Huella publicada por Offensive Security en docs.kali.org.
KALI_KEY_FPR="44C6513A8E4FB3D30875F758ED444FF07D8D0BF6"
KALI_KEY_URL="https://archive.kali.org/archive-key.asc"
KALI_CDIMAGE="https://cdimage.kali.org/current"

#--- Utilidades ---------------------------------------------------------------
c_reset=$'\033[0m'; c_ok=$'\033[32m'; c_warn=$'\033[33m'; c_err=$'\033[31m'; c_hi=$'\033[36m'
log()  { printf '%s==>%s %s\n' "$c_hi"  "$c_reset" "$*"; }
ok()   { printf '%s  ok%s %s\n' "$c_ok"  "$c_reset" "$*"; }
warn() { printf '%s  !!%s %s\n' "$c_warn" "$c_reset" "$*" >&2; }
die()  { printf '%s ERR%s %s\n' "$c_err" "$c_reset" "$*" >&2; exit 1; }

need() {
  local missing=()
  for c in "$@"; do command -v "$c" >/dev/null 2>&1 || missing+=("$c"); done
  if ((${#missing[@]})); then
    die "faltan comandos: ${missing[*]}
    Debian/Ubuntu: sudo apt install ${missing[*]}
    Fedora:        sudo dnf install ${missing[*]}"
  fi
}

usage() {
  # Imprime el bloque de comentarios de cabecera, sin el shebang.
  awk 'NR>1 && /^#/ { sub(/^# ?/, ""); print; next } NR>1 { exit }' "$0"
  cat <<EOF

Opciones:
  --backend {qemu|libvirt}   Hipervisor a usar           (def: $BACKEND)
  --name NOMBRE              Nombre de la VM             (def: $VM_NAME)
  --disk GB                  Tamaño del disco en GB      (def: $DISK_GB)
  --ram MB                   RAM en MB                   (def: $RAM_MB)
  --cpus N                   vCPUs                       (def: $CPUS)
  --user USUARIO             Usuario a crear             (def: $USERNAME)
  --hostname NOMBRE          Hostname del sistema        (def: $HOSTNAME_)
  --timezone TZ              Zona horaria                (def: $TIMEZONE)
  --locale LOCALE            Locale                      (def: $LOCALE)
  --keymap MAPA              Distribución de teclado     (def: $KEYMAP)
  --packages "P1 P2"         Metapaquetes a instalar     (def: $PACKAGES)
  --apt-proxy URL            Proxy apt durante el install
  --iso RUTA                 Usar una ISO local ya descargada
  --workdir RUTA             Directorio de trabajo       (def: $WORKDIR)
  -y, --yes                  No pedir confirmación
  -h, --help                 Esta ayuda

Contraseña: se toma de \$KALI_PASSWORD, o se pide por stdin.
EOF
}

#--- Argumentos ---------------------------------------------------------------
while (($#)); do
  case "$1" in
    --backend)  BACKEND="${2:?}"; shift 2 ;;
    --name)     VM_NAME="${2:?}"; shift 2 ;;
    --disk)     DISK_GB="${2:?}"; shift 2 ;;
    --ram)      RAM_MB="${2:?}"; shift 2 ;;
    --cpus)     CPUS="${2:?}"; shift 2 ;;
    --user)     USERNAME="${2:?}"; shift 2 ;;
    --hostname) HOSTNAME_="${2:?}"; shift 2 ;;
    --timezone) TIMEZONE="${2:?}"; shift 2 ;;
    --locale)   LOCALE="${2:?}"; shift 2 ;;
    --keymap)   KEYMAP="${2:?}"; shift 2 ;;
    --packages) PACKAGES="${2:?}"; shift 2 ;;
    --apt-proxy) APT_PROXY="${2:?}"; shift 2 ;;
    --iso)      ISO_PATH="${2:?}"; shift 2 ;;
    --workdir)  WORKDIR="${2:?}"; shift 2 ;;
    -y|--yes)   ASSUME_YES="1"; shift ;;
    -h|--help)  usage; exit 0 ;;
    *) die "opción desconocida: $1  (usa --help)" ;;
  esac
done

case "$BACKEND" in
  qemu|libvirt) ;;
  *) die "backend inválido: $BACKEND (usa qemu o libvirt)" ;;
esac

[[ "$DISK_GB" =~ ^[0-9]+$ ]] || die "--disk debe ser un entero"
[[ "$RAM_MB"  =~ ^[0-9]+$ ]] || die "--ram debe ser un entero"
[[ "$CPUS"    =~ ^[0-9]+$ ]] || die "--cpus debe ser un entero"
((RAM_MB >= 2048)) || die "Kali con escritorio necesita al menos 2048 MB de RAM"
((DISK_GB >= 20)) || die "el disco debe ser de al menos 20 GB"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEMPLATE="$SCRIPT_DIR/kali.preseed.tmpl"
[[ -f "$TEMPLATE" ]] || die "no encuentro la plantilla: $TEMPLATE"

#--- Dependencias -------------------------------------------------------------
need curl gpg openssl awk
if [[ "$BACKEND" == "qemu" ]]; then
  need qemu-system-x86_64 qemu-img xorriso cpio gzip
else
  need virt-install virsh
fi

#--- Contraseña ---------------------------------------------------------------
# Se hashea localmente (SHA-512 crypt). El texto plano no toca el disco.
get_password() {
  local p1 p2
  if [[ -n "${KALI_PASSWORD:-}" ]]; then
    p1="$KALI_PASSWORD"
  else
    read -rsp "Contraseña para el usuario '$USERNAME': " p1; echo >&2
    read -rsp "Confírmala: " p2; echo >&2
    [[ "$p1" == "$p2" ]] || die "las contraseñas no coinciden"
  fi
  ((${#p1} >= 8)) || die "la contraseña debe tener al menos 8 caracteres"
  PWHASH="$(openssl passwd -6 "$p1")"
  unset p1 p2
}

#--- Descarga y verificación de la ISO ----------------------------------------
verify_and_fetch_iso() {
  mkdir -p "$WORKDIR"

  log "Importando la clave de firma de Kali"
  export GNUPGHOME="$WORKDIR/gnupg"
  mkdir -p "$GNUPGHOME"; chmod 700 "$GNUPGHOME"
  curl -fsSL --retry 3 "$KALI_KEY_URL" | gpg --quiet --import 2>/dev/null \
    || die "no pude descargar la clave desde $KALI_KEY_URL"
  gpg --quiet --list-keys "$KALI_KEY_FPR" >/dev/null 2>&1 \
    || die "la clave descargada NO coincide con la huella esperada ($KALI_KEY_FPR).
    Aborto: no voy a confiar en una imagen firmada por una clave desconocida."
  ok "clave verificada: $KALI_KEY_FPR"

  log "Descargando checksums firmados"
  curl -fsSL --retry 3 -o "$WORKDIR/SHA256SUMS"     "$KALI_CDIMAGE/SHA256SUMS"
  curl -fsSL --retry 3 -o "$WORKDIR/SHA256SUMS.gpg" "$KALI_CDIMAGE/SHA256SUMS.gpg"

  gpg --quiet --verify "$WORKDIR/SHA256SUMS.gpg" "$WORKDIR/SHA256SUMS" 2>/dev/null \
    || die "la firma GPG de SHA256SUMS no es válida. Aborto."
  ok "firma GPG de SHA256SUMS válida"

  local iso_name
  iso_name="$(awk '/installer-netinst-amd64\.iso$/ {print $2; exit}' "$WORKDIR/SHA256SUMS")"
  [[ -n "$iso_name" ]] || die "no encontré una ISO netinst en SHA256SUMS"

  if [[ -z "$ISO_PATH" ]]; then
    ISO_PATH="$WORKDIR/$iso_name"
    log "Descargando $iso_name (se reanuda si ya existe)"
    curl -fL --retry 3 -C - -o "$ISO_PATH" "$KALI_CDIMAGE/$iso_name"
  else
    log "Usando ISO local: $ISO_PATH"
    [[ -f "$ISO_PATH" ]] || die "no existe: $ISO_PATH"
  fi

  log "Verificando SHA256 de la imagen"
  local want have
  want="$(awk -v n="$(basename "$ISO_PATH")" '$2==n {print $1; exit}' "$WORKDIR/SHA256SUMS")"
  if [[ -z "$want" ]]; then
    warn "esa ISO no aparece en SHA256SUMS; no puedo verificarla"
  else
    have="$(openssl dgst -sha256 -r "$ISO_PATH" | awk '{print $1}')"
    [[ "$want" == "$have" ]] || die "SHA256 NO coincide.
      esperado: $want
      obtenido: $have
    La imagen está corrupta o alterada. Aborto."
    ok "SHA256 correcto"
  fi
}

#--- Preseed ------------------------------------------------------------------
build_preseed() {
  PRESEED="$WORKDIR/preseed.cfg"
  # El hash contiene $ y /: se pasa por variable de awk, nunca por sed.
  awk -v user="$USERNAME" -v pwhash="$PWHASH" -v host="$HOSTNAME_" \
      -v tz="$TIMEZONE" -v loc="$LOCALE" -v km="$KEYMAP" \
      -v pkgs="$PACKAGES" -v aptproxy="$APT_PROXY" '
    { gsub(/@@USER@@/, user); gsub(/@@PWHASH@@/, pwhash)
      gsub(/@@HOSTNAME@@/, host); gsub(/@@TIMEZONE@@/, tz)
      gsub(/@@LOCALE@@/, loc); gsub(/@@KEYMAP@@/, km)
      gsub(/@@PACKAGES@@/, pkgs); gsub(/@@APT_PROXY@@/, aptproxy)
      print }
  ' "$TEMPLATE" > "$PRESEED"
  chmod 600 "$PRESEED"
  # Sólo marcadores reales: la plantilla lleva texto con arrobas en comentarios.
  if grep -qE '@@[A-Z_]+@@' "$PRESEED"; then
    die "quedaron marcadores sin sustituir: $(grep -oE '@@[A-Z_]+@@' "$PRESEED" | sort -u | tr '\n' ' ')"
  fi
  ok "preseed generado ($PRESEED)"
}

#--- Backend: QEMU ------------------------------------------------------------
run_qemu() {
  local disk="$WORKDIR/$VM_NAME.qcow2"
  local kvm_args=()

  if [[ -e /dev/kvm && -r /dev/kvm && -w /dev/kvm ]]; then
    kvm_args=(-enable-kvm -cpu host)
    ok "KVM disponible: la instalación irá a velocidad nativa"
  else
    warn "sin acceso a /dev/kvm — se usará emulación TCG (10-20x más lento)."
    warn "Habilita VT-x/AMD-V en la BIOS y añade tu usuario al grupo 'kvm'."
  fi

  log "Extrayendo kernel e initrd del instalador"
  rm -f "$WORKDIR/vmlinuz" "$WORKDIR/initrd.gz"
  xorriso -osirrox on -indev "$ISO_PATH" \
    -extract /install.amd/vmlinuz   "$WORKDIR/vmlinuz" \
    -extract /install.amd/initrd.gz "$WORKDIR/initrd.gz" >/dev/null 2>&1 \
    || die "no pude extraer /install.amd/{vmlinuz,initrd.gz} de la ISO"

  # Inyectar el preseed dentro del initrd. Se descomprime, se añade el fichero
  # al archivo cpio con -A (que reescribe el trailer) y se vuelve a comprimir.
  # Así no hace falta servidor HTTP ni remasterizar la ISO, y el resultado es
  # un initrd normal y corriente que se puede inspeccionar con `cpio -t`.
  log "Inyectando el preseed en el initrd"
  local inj="$WORKDIR/inj" cpio_img="$WORKDIR/initrd.cpio"
  rm -rf "$inj" "$cpio_img"; mkdir -p "$inj"
  cp "$PRESEED" "$inj/preseed.cfg"

  # El initrd de d-i es gzip, pero no damos por hecho el formato.
  case "$(od -An -tx1 -N6 "$WORKDIR/initrd.gz" | tr -d ' \n')" in
    1f8b*)    gzip -dc  "$WORKDIR/initrd.gz" > "$cpio_img" ;;
    fd377a*)  need xz;  xz   -dc "$WORKDIR/initrd.gz" > "$cpio_img" ;;
    425a68*)  need bzip2; bzip2 -dc "$WORKDIR/initrd.gz" > "$cpio_img" ;;
    *) die "no reconozco la compresión del initrd de la ISO" ;;
  esac

  ( cd "$inj" && printf 'preseed.cfg\n' \
      | cpio -H newc -o -A -F "$cpio_img" --quiet ) \
    || die "no pude añadir el preseed al initrd"

  gzip -9 -c "$cpio_img" > "$WORKDIR/initrd.inj.gz"
  rm -f "$cpio_img"

  # Comprobación: el preseed tiene que estar realmente dentro.
  gzip -dc "$WORKDIR/initrd.inj.gz" | cpio -t --quiet 2>/dev/null \
    | grep -qx 'preseed.cfg' \
    || die "el preseed no quedó dentro del initrd; abortando antes de arrancar"
  ok "preseed inyectado y verificado dentro del initrd"

  log "Creando disco de ${DISK_GB}G"
  qemu-img create -f qcow2 "$disk" "${DISK_GB}G" >/dev/null

  log "Arrancando la instalación desatendida (esto tarda; sin KVM, mucho)"
  qemu-system-x86_64 \
    "${kvm_args[@]}" \
    -m "$RAM_MB" -smp "$CPUS" \
    -drive file="$disk",if=virtio,format=qcow2 \
    -cdrom "$ISO_PATH" \
    -kernel "$WORKDIR/vmlinuz" -initrd "$WORKDIR/initrd.inj.gz" \
    -append "auto=true priority=critical preseed/file=/preseed.cfg console=ttyS0,115200n8 --- console=ttyS0,115200n8" \
    -netdev user,id=n0 -device virtio-net-pci,netdev=n0 \
    -nographic -no-reboot

  # El preseed apaga la VM al terminar, así que llegar aquí = install hecho.
  local runner="$WORKDIR/run-$VM_NAME.sh"
  cat > "$runner" <<EOF
#!/usr/bin/env bash
# Arranca la VM ya instalada. SSH: ssh -p 2222 $USERNAME@localhost
exec qemu-system-x86_64 ${kvm_args[*]} \\
  -m $RAM_MB -smp $CPUS \\
  -drive file="$disk",if=virtio,format=qcow2 \\
  -netdev user,id=n0,hostfwd=tcp::2222-:22 -device virtio-net-pci,netdev=n0 \\
  -vga virtio -display gtk "\$@"
EOF
  chmod +x "$runner"

  ok "Instalación terminada."
  echo
  echo "  Disco:    $disk"
  echo "  Arrancar: $runner"
  echo "  SSH:      ssh -p 2222 $USERNAME@localhost"
}

#--- Backend: libvirt ---------------------------------------------------------
run_libvirt() {
  if virsh dominfo "$VM_NAME" >/dev/null 2>&1; then
    die "ya existe una VM llamada '$VM_NAME'.
    Bórrala con: virsh destroy $VM_NAME; virsh undefine $VM_NAME --remove-all-storage"
  fi

  [[ -r /dev/kvm && -w /dev/kvm ]] \
    || warn "sin acceso a /dev/kvm: será lento. Añádete al grupo 'kvm' y reinicia sesión."

  log "Lanzando virt-install (instalación desatendida, consola serie)"
  virt-install \
    --name "$VM_NAME" \
    --memory "$RAM_MB" \
    --vcpus "$CPUS" \
    --disk size="$DISK_GB",format=qcow2,bus=virtio \
    --location "$ISO_PATH,kernel=install.amd/vmlinuz,initrd=install.amd/initrd.gz" \
    --initrd-inject "$PRESEED" \
    --extra-args "auto=true priority=critical preseed/file=/preseed.cfg console=ttyS0,115200n8" \
    --network network=default,model=virtio \
    --os-variant debian12 \
    --graphics none \
    --noreboot \
    --wait -1

  ok "Instalación terminada."
  echo
  echo "  Arrancar: virsh start $VM_NAME"
  echo "  Consola:  virsh console $VM_NAME"
  echo "  Gráfico:  virt-viewer $VM_NAME"
}

#--- Main ---------------------------------------------------------------------
cat <<EOF
  Kali Linux — aprovisionamiento desatendido
  ------------------------------------------
  backend    $BACKEND
  VM         $VM_NAME   ${CPUS} vCPU / ${RAM_MB} MB RAM / ${DISK_GB} GB disco
  usuario    $USERNAME @ $HOSTNAME_
  locale     $LOCALE   teclado: $KEYMAP   tz: $TIMEZONE
  paquetes   $PACKAGES
  trabajo    $WORKDIR
EOF

if [[ "$ASSUME_YES" != "1" ]]; then
  read -rp "¿Seguimos? [s/N] " a
  [[ "$a" =~ ^[sSyY]$ ]] || { echo "Cancelado."; exit 0; }
fi

get_password
verify_and_fetch_iso
build_preseed

case "$BACKEND" in
  qemu)    run_qemu ;;
  libvirt) run_libvirt ;;
esac
