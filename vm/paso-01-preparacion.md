# Paso 1 — Preparar VirtualBox y las ISOs

Práctica 01 "Identificación de Riesgos de Confidencialidad"
ICSA-014 Manejo de Datos para la Ciberseguridad — FCC/BUAP

Antes de crear ninguna VM hacen falta tres cosas: VirtualBox instalado, las dos
ISOs descargadas y **verificadas**, y espacio en disco. Este paso no produce
todavía ninguna máquina; produce los insumos para `lab-cia-virtualbox.sh`.

---

## 1. Requisitos previos

| Requisito | Valor | Cómo comprobarlo |
|---|---|---|
| Espacio libre | **~90 GB** (Kali 60 + Debian 25 + ISOs) | `df -h ~` · Windows: propiedades del disco |
| Virtualización HW | VT-x / AMD-V **activada en la BIOS** | Linux: `grep -Eoc '(vmx\|svm)' /proc/cpuinfo` (>0) · Windows: Administrador de tareas → Rendimiento → CPU → "Virtualización: Habilitada" |
| RAM | 8 GB recomendable (las VMs piden 2 GB + 4 GB) | — |

> **Extension Pack: no hace falta.** La red interna y el modo promiscuo son
> funciones de la base de VirtualBox. El Extension Pack tiene licencia PUEL
> (no libre) y no aporta nada a esta práctica. No lo instales.

Si VT-x/AMD-V está desactivado, VirtualBox arranca las VMs en emulación pura o
directamente se niega. En portátiles suele venir desactivado de fábrica y la
opción está en la BIOS/UEFI como *Intel Virtualization Technology*, *SVM Mode*
o *AMD-V*.

---

## 2. Instalar VirtualBox

Descarga desde la fuente oficial — **`https://www.virtualbox.org/wiki/Downloads`** —
y no desde repositorios de terceros.

| Sistema | Paquete |
|---|---|
| Windows | *Windows hosts* (`.exe`) |
| macOS | *macOS / Intel hosts* o *Developer preview for macOS / Apple Silicon* según tu Mac |
| Debian/Ubuntu | *Linux distributions* → el `.deb` de tu versión, o el repo oficial de Oracle |

Comprueba que quedó en el `PATH`:

```bash
VBoxManage --version
```

Si el comando no aparece:

- **Windows** (Git Bash): añade `C:\Program Files\Oracle\VirtualBox` al `PATH`.
- **macOS**: suele estar en `/usr/local/bin` o
  `/Applications/VirtualBox.app/Contents/MacOS`.

`lab-cia-virtualbox.sh` aborta si no encuentra `VBoxManage`, incluso con
`--dry-run`, así que este comando tiene que funcionar antes de seguir.

---

## 3. Descargar las ISOs

### Debian 12 — cuidado con `current/`

La práctica pide **Debian 12 (bookworm)**. Desde agosto de 2025 la estable de
Debian es la **13 (trixie)**, así que la ruta `debian-cd/current/` ya **no**
apunta a Debian 12: te bajarías la versión equivocada.

- Ruta correcta (archivo de versiones): `https://cdimage.debian.org/cdimage/archive/`
  → entra en la carpeta `12.x.0` más alta que veas → `amd64/iso-cd/`
- Archivo: `debian-12.x.0-amd64-netinst.iso` (~630 MB)

Confirma en la propia página qué `12.x.0` es la última antes de descargar. La
imagen **netinst** basta: el resto de paquetes los baja durante la instalación
por el adaptador NAT.

### Kali — tiene que ser la imagen *Installer*

`https://www.kali.org/get-kali/#kali-installer-images`

Kali publica varias imágenes y **solo una sirve para esta práctica**:

| Imagen | ¿Sirve? | Por qué |
|---|---|---|
| **Installer** (`kali-linux-AAAA.N-installer-amd64.iso`, ~4 GB) | **Sí** | Es la que pregunta nombre de máquina, dominio, nombre completo, usuario y contraseña, y luego muestra la pantalla de selección de software con Xfce y `default -- recommended tools`. |
| NetInstaller (`...-installer-netinst-amd64.iso`, ~500 MB) | Aceptable | Mismas pantallas, pero descarga todo por red: mucho más lento. |
| **Live** (`...-live-amd64.iso`) | **No** | Arranca a un escritorio en vivo y su instalador (Calamares) tiene otro flujo: **no** pide dominio ni muestra `default -- recommended tools`. No podrías capturar las pantallas que pide el enunciado. |

Los datos del enunciado (`LAB-CIA`, `datoskali.org`, `Atacante Kali`,
`atacante`, `12345`, Xfce + `default -- recommended tools`) se introducen en
esas pantallas del instalador, de ahí que la imagen *Installer* sea obligatoria.

> `vm/provision-kali.sh` usa la netinst a propósito: ese script es la vía
> desatendida por preseed, un camino distinto al de la práctica.

---

## 4. Verificar las ISOs

Descargar sin verificar es exactamente el riesgo de integridad del que trata la
materia. Junto a cada ISO hay un `SHA256SUMS` y su firma.

### 4a. Comprobar el hash

Descarga `SHA256SUMS` en la misma carpeta que la ISO y:

```bash
# Linux
sha256sum -c SHA256SUMS --ignore-missing

# macOS
shasum -a 256 -c SHA256SUMS --ignore-missing
```

```powershell
# Windows PowerShell — compara la salida con la línea de tu ISO en SHA256SUMS
Get-FileHash -Algorithm SHA256 .\kali-linux-2026.1-installer-amd64.iso
```

Debe decir `OK` / coincidir. Si no coincide, la descarga se corrompió o no es
legítima: bórrala y vuelve a bajarla.

### 4b. Comprobar la firma GPG (lo que de verdad autentica)

El hash solo prueba que el archivo llegó entero. La firma prueba **quién** lo
publicó.

**Kali** — la huella de la clave del archivo de Kali, la misma que
`vm/provision-kali.sh` tiene fijada:

```bash
KALI_FPR=44C6513A8E4FB3D30875F758ED444FF07D8D0BF6

curl -fsSL https://archive.kali.org/archive-key.asc | gpg --import
gpg --list-keys "$KALI_FPR"          # si no la lista, ALTO: clave incorrecta

curl -fsSLO https://cdimage.kali.org/current/SHA256SUMS
curl -fsSLO https://cdimage.kali.org/current/SHA256SUMS.gpg
gpg --verify SHA256SUMS.gpg SHA256SUMS
```

Busca `Good signature`. Un aviso de *"This key is not certified with a trusted
signature"* es normal (no has firmado la clave); lo que **no** puede aparecer es
`BAD signature`.

**Debian** — el fichero de firma es `SHA256SUMS.sign`:

```bash
curl -fsSLO <ruta-de-tu-12.x.0>/SHA256SUMS
curl -fsSLO <ruta-de-tu-12.x.0>/SHA256SUMS.sign
gpg --verify SHA256SUMS.sign SHA256SUMS
```

Si GPG dice que no tiene la clave, impórtala y **contrasta la huella con la
lista oficial de `https://www.debian.org/CD/verify`** antes de fiarte de ella.
No des por buena una huella copiada de un foro — ni de este documento.

---

## 5. Comprobación final del paso

Con VirtualBox instalado y las dos ISOs verificadas, previsualiza la creación
de las VMs sin ejecutar nada:

```bash
cd vm
./lab-cia-virtualbox.sh \
  --iso-debian ~/Descargas/debian-12.x.0-amd64-netinst.iso \
  --iso-kali   ~/Descargas/kali-linux-2026.N-installer-amd64.iso \
  --dry-run
```

`--dry-run` imprime los `VBoxManage` que se ejecutarían y no toca nada. Requiere
que `VBoxManage` exista y que **las rutas de las ISOs sean correctas**: el
script comprueba ambas cosas antes de simular. Si el dry-run sale limpio, el
Paso 1 está terminado y la creación real es el mismo comando sin `--dry-run`.

En la salida debes ver, para cada VM, la línea con:

```
--nic1 nat --nic2 intnet --intnet2 LAB-CIA --nicpromisc2 allow-all
```

Eso es la topología que pide el enunciado: NAT en el adaptador 1, red interna
`LAB-CIA` en el 2, modo promiscuo *permitir todo*.

---

## 6. Evidencia del Paso 1

Las capturas las haces tú, con tu escritorio y la fecha y hora visibles. Para
este paso lo razonable es capturar:

1. VirtualBox abierto, con la versión a la vista (*Ayuda → Acerca de*).
2. La carpeta de descargas con las dos ISOs.
3. La terminal con el resultado de la verificación: `OK` del `sha256sum -c` y
   el `Good signature` del `gpg --verify`.
4. La salida del `--dry-run`, donde se lee `--intnet2 LAB-CIA --nicpromisc2
   allow-all`.

La 3 es la que más vale: documenta que verificaste procedencia e integridad
antes de ejecutar nada, que es el fondo del asunto en una práctica sobre
riesgos de confidencialidad.

---

## Siguiente

Con las ISOs verificadas, el Paso 2 es crear las VMs de verdad (mismo comando
sin `--dry-run`) y arrancar el instalador de Debian. Ojo ahí: el instalador
detectará **dos** interfaces de red y preguntará cuál es la principal — hay que
elegir la primera (`enp0s3`, el NAT), que es la que tiene salida a Internet para
bajar los paquetes. La segunda es el segmento aislado y no tiene DHCP.
