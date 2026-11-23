"""Servidor local de Cascada: visor, ficheros de datos con rangos y API.

Uso:
    python -m procesamiento.servidor [--puerto 8765] [--sin-conexion]

y abrir http://localhost:8765. Solo escucha en la propia máquina. Si el puerto ya está ocupado (otro
servidor de Cascada abierto), no arranca. Un error inesperado se responde con un 500 en JSON y su traza
sale por la consola.

- /                      visor (carpeta visor/)
- /datos/...             ficheros para el visor (datos/visor/), con peticiones por rangos
                         (HTTP 206), que PMTiles necesita
- /externo/<servicio>/z/x/y.ext, /externo/glifos/<tipografía>/<rango>.pbf
                         con --sin-conexion, mapa base vectorial, relieve y ortofoto del IGN y tipografías del mapa
                         desde la copia guardada (procesamiento/sin_conexion.py); con red, el visor los pide al IGN
- GET /api/celda?lon=&lat=   análisis basal de la celda de 1 km que contiene el punto
- GET /api/activo?id=        ficha común y riesgos de un activo
- GET /api/focos             focos de calor de NASA FIRMS en la Comunidad (últimas 24 h)
- POST /api/incendio         simula un incendio. Cuerpo JSON: {"lon", "lat", "hora"?: ISO local,
                             "viento"?: {"velocidad_kmh", "desde"}, o "vientos"?: [{...}, ...] hora a hora}
                             (sin viento, se usa AEMET)
- GET /api/incendio/llegada?id=  mapa de llegada de una simulación (uint16 por filas, minutos)
- GET /api/incendio/movilidad?id=  trenes, incidencias de la DGT y tráfico de la ciudad actuales
- GET /api/validacion        caso de validación del modelo de incendio (Tres Cantos, 2025): simulación guardada,
                             perímetro de EFFIS, focos de satélite y métricas
                             dentro de la zona afectada por una simulación (llamas o humo)
- GET /api/trenes            trenes de viajeros de Renfe en la Comunidad (tiempo real, 30 s)
- GET /api/trafico           tráfico de la ciudad de Madrid e incidencias de la DGT (5 min)
- GET /api/prealerta         prealerta a 7 días: niveles por municipio y día, avisos oficiales y resumen
- GET /api/prealerta/municipio?codigo=&dia=  detalle de un municipio (7 días) y sus activos con riesgo focal
- GET /api/prealerta/activos?dia=            activos de la Comunidad con riesgo focal un día (índice 0 a 6 o fecha)
- POST /api/prealerta/actualizar             vuelve a pedir la previsión a AEMET (en segundo plano)
"""
import argparse
import json
import math
import mimetypes
import os
import re
import traceback
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs

from .fuentes import RAIZ, VISOR

CARPETA_VISOR = RAIZ / "visor"
mimetypes.add_type("application/vnd.pmtiles", ".pmtiles")
mimetypes.add_type("application/geo+json", ".geojson")
mimetypes.add_type("text/javascript", ".js")
RANGO = re.compile(r"bytes=(\d*)-(\d*)$")
CUERPO_MAX = 64 * 1024     # bytes de una alerta


def ruta_segura(base: Path, relativa: str) -> Path | None:
    """Ruta dentro de base, o None si intenta salir de ella."""
    destino = (base / relativa.lstrip("/")).resolve()
    return destino if destino.is_relative_to(base.resolve()) else None


def _serializable(o):
    if hasattr(o, "item"):
        return o.item()
    return str(o)


class Manejador(BaseHTTPRequestHandler):
    server_version = "Cascada/1.0"

    def log_message(self, formato, *args):
        print(f"[{self.log_date_time_string()}] {formato % args}", flush=True)

    # ------------------------------------------------------------------ respuestas
    def json(self, datos, estado=HTTPStatus.OK):
        cuerpo = json.dumps(datos, ensure_ascii=False, default=_serializable).encode("utf-8")
        self.send_response(estado)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(cuerpo)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(cuerpo)

    def error(self, estado, mensaje):
        self.json({"error": mensaje}, estado)

    def fichero(self, ruta: Path | None):
        if ruta is None or not ruta.is_file():
            return self.error(HTTPStatus.NOT_FOUND, "No encontrado")
        tam = ruta.stat().st_size
        inicio, fin, estado = 0, tam - 1, HTTPStatus.OK
        rango = self.headers.get("Range")
        if rango:
            m = RANGO.match(rango.strip())
            if not m or (m.group(1) == "" and m.group(2) == ""):
                return self.rango_invalido(tam)
            if m.group(1) == "":                       # bytes=-N: los últimos N
                inicio = max(tam - int(m.group(2)), 0)
            else:
                inicio = int(m.group(1))
                if m.group(2):
                    fin = min(int(m.group(2)), tam - 1)
            if inicio > fin or inicio >= tam:
                return self.rango_invalido(tam)
            estado = HTTPStatus.PARTIAL_CONTENT
        longitud = fin - inicio + 1
        self.send_response(estado)
        self.send_header("Content-Type", mimetypes.guess_type(ruta.name)[0] or "application/octet-stream")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(longitud))
        if estado == HTTPStatus.PARTIAL_CONTENT:
            self.send_header("Content-Range", f"bytes {inicio}-{fin}/{tam}")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        if self.command == "HEAD":
            return
        with open(ruta, "rb") as f:
            f.seek(inicio)
            restante = longitud
            while restante > 0:
                bloque = f.read(min(1 << 16, restante))
                if not bloque:
                    break
                self.wfile.write(bloque)
                restante -= len(bloque)

    def texto(self, contenido: str, mime: str):
        datos = contenido.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", f"{mime}; charset=utf-8")
        self.send_header("Content-Length", str(len(datos)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(datos)

    def externo(self, resto: str):
        """Teselas del IGN y tipografías del mapa desde la caché del modo sin conexión."""
        from urllib.parse import unquote
        from . import sin_conexion
        partes = unquote(resto).split("/")
        encontrado = None
        if len(partes) == 3 and partes[0] == "glifos" and partes[2].endswith(".pbf"):
            ruta = sin_conexion.glifo(partes[1], partes[2].removesuffix(".pbf"))
            encontrado = (ruta, "application/x-protobuf") if ruta else None
        elif len(partes) == 4 and partes[0] in sin_conexion.SERVICIOS:
            y = partes[3].split(".")[0]
            if partes[1].isdigit() and partes[2].isdigit() and y.isdigit():
                encontrado = sin_conexion.tesela(partes[0], int(partes[1]), int(partes[2]), int(y))
        if not encontrado:
            return self.error(HTTPStatus.NOT_FOUND, "No disponible sin conexión")
        ruta, mime = encontrado
        datos = ruta.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", mime)
        if datos[:2] == b"\x1f\x8b":   # teselas vectoriales guardadas comprimidas
            self.send_header("Content-Encoding", "gzip")
        self.send_header("Content-Length", str(len(datos)))
        self.send_header("Cache-Control", "max-age=86400")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(datos)

    def rango_invalido(self, tam):
        self.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
        self.send_header("Content-Range", f"bytes */{tam}")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def fallo_interno(self):
        """Error inesperado: traza a la consola y un 500 en JSON (si aún se puede responder)."""
        traceback.print_exc()
        try:
            self.error(HTTPStatus.INTERNAL_SERVER_ERROR, "Error interno del servidor; el detalle está en la consola")
        except OSError:
            pass

    # ------------------------------------------------------------------ rutas
    def do_GET(self):
        try:
            self._get()
        except ConnectionError:
            pass
        except Exception:
            self.fallo_interno()

    def _get(self):
        ruta, _, consulta = self.path.partition("?")
        if ruta.startswith("/api/"):
            return self.api(ruta, parse_qs(consulta))
        if ruta.startswith("/datos/"):
            return self.fichero(ruta_segura(VISOR, ruta.removeprefix("/datos/")))
        if ruta == "/externo/configuracion.js":
            from .sin_conexion import configuracion_visor
            return self.texto(configuracion_visor(), "text/javascript")
        if ruta.startswith("/externo/"):
            return self.externo(ruta.removeprefix("/externo/"))
        return self.fichero(ruta_segura(CARPETA_VISOR, "index.html" if ruta in ("", "/") else ruta))

    do_HEAD = do_GET

    def do_POST(self):
        try:
            self._post()
        except ConnectionError:
            pass
        except Exception:
            self.fallo_interno()

    def _post(self):
        ruta = self.path.partition("?")[0]
        if ruta == "/api/prealerta/actualizar":
            from .prealerta import servicio
            return self.json(servicio.actualizar())
        if ruta not in ("/api/incendio", "/api/presa"):
            return self.error(HTTPStatus.NOT_FOUND, "No encontrado")
        try:
            longitud = int(self.headers.get("Content-Length", 0))
        except ValueError:
            longitud = -1
        if not 0 <= longitud <= CUERPO_MAX:
            return self.error(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "Alerta incorrecta: cuerpo ausente o demasiado grande")
        try:
            cuerpo = json.loads(self.rfile.read(longitud) or b"{}")
            self.json(simular_incendio(cuerpo) if ruta == "/api/incendio" else simular_presa(cuerpo))
        except (KeyError, ValueError, TypeError, AttributeError) as e:
            self.error(HTTPStatus.BAD_REQUEST, f"Alerta incorrecta: {e}")
        except OSError as e:   # AEMET, IGN o FIRMS no responden
            self.error(HTTPStatus.SERVICE_UNAVAILABLE, f"No se ha podido obtener un dato externo: {e}")
        except RuntimeError as e:
            self.error(HTTPStatus.SERVICE_UNAVAILABLE, str(e))

    def api(self, ruta, parametros):
        from .consultas import NoEncontrado, activo, celda, municipios, resumen
        try:
            if ruta == "/api/resumen":
                datos = resumen()
            elif ruta == "/api/municipios":
                datos = municipios()
            elif ruta == "/api/celda":
                datos = celda(*coordenadas(parametros["lon"][0], parametros["lat"][0]))
            elif ruta == "/api/activo":
                datos = activo(parametros["id"][0])
            elif ruta == "/api/focos":
                from .incendio.focos import focos_actuales
                datos = focos_actuales()
            elif ruta == "/api/trenes":
                from .tiempo_real import trenes
                datos = trenes()
            elif ruta == "/api/trafico":
                from .tiempo_real import trafico
                datos = trafico()
            elif ruta == "/api/incendio/movilidad":
                from .incendio.movilidad import cruce
                datos = cruce(parametros["id"][0])
            elif ruta == "/api/presas":
                from .presa.simulacion import presas
                datos = presas()
            elif ruta == "/api/incendio/llegada":
                from .incendio.simulacion import llegada_u16
                return self.binario(llegada_u16(parametros["id"][0]))
            elif ruta == "/api/validacion":
                from .incendio.validacion import cargar
                try:
                    datos = cargar()
                except FileNotFoundError:
                    return self.error(HTTPStatus.NOT_FOUND, "La validación no está calculada: python -m procesamiento.incendio.validacion")
            elif ruta == "/api/prealerta":
                from .prealerta import servicio
                datos = servicio.resumen()
            elif ruta == "/api/prealerta/municipio":
                from .prealerta import servicio
                datos = servicio.municipio(parametros["codigo"][0], parametros.get("dia", ["0"])[0])
            elif ruta == "/api/prealerta/activos":
                from .prealerta import servicio
                datos = servicio.activos(parametros.get("dia", ["0"])[0])
            else:
                return self.error(HTTPStatus.NOT_FOUND, "No encontrado")
        except (KeyError, ValueError, IndexError):
            return self.error(HTTPStatus.BAD_REQUEST, "Parámetros incorrectos")
        except NoEncontrado as e:
            return self.error(HTTPStatus.NOT_FOUND, str(e))
        except FileNotFoundError:
            return self.error(HTTPStatus.NOT_FOUND, "No hay datos: ejecuta python -m procesamiento.cadena o repite la simulación")
        except OSError as e:
            return self.error(HTTPStatus.SERVICE_UNAVAILABLE, f"No se ha podido obtener un dato externo: {e}")
        except RuntimeError as e:
            return self.error(HTTPStatus.SERVICE_UNAVAILABLE, str(e))
        self.json(datos)

    def binario(self, datos: bytes):
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(len(datos)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(datos)


def _finito(valor, nombre: str) -> float:
    numero = float(valor)
    if not math.isfinite(numero):
        raise ValueError(f"{nombre} no es un número válido")
    return numero


def coordenadas(lon, lat) -> tuple[float, float]:
    """Longitud y latitud numéricas y dentro de su rango; ValueError si no."""
    lon, lat = _finito(lon, "la longitud"), _finito(lat, "la latitud")
    if not (-180 <= lon <= 180 and -90 <= lat <= 90):
        raise ValueError("coordenadas fuera de rango")
    return lon, lat


def simular_incendio(peticion: dict) -> dict:
    """Valida la alerta recibida y lanza la simulación."""
    from datetime import datetime
    from .incendio.entradas import MADRID
    from .incendio.propagacion import Viento
    from .incendio.simulacion import simular
    if not isinstance(peticion, dict):
        raise ValueError("se esperaba un objeto JSON")
    lon, lat = coordenadas(peticion["lon"], peticion["lat"])
    hora = datetime.fromisoformat(peticion["hora"]) if peticion.get("hora") else datetime.now(MADRID)
    hora = hora.replace(tzinfo=MADRID) if hora.tzinfo is None else hora
    if not 2000 <= hora.year <= 2100:
        raise ValueError("fecha fuera de rango")
    lista = peticion.get("vientos") or ([peticion["viento"]] if peticion.get("viento") else [])
    if not isinstance(lista, list) or len(lista) > 25:
        raise ValueError("la serie de viento admite como mucho 25 horas")
    manual = [Viento(_finito(w["velocidad_kmh"], "la velocidad del viento"), _finito(w["desde"], "la dirección del viento") % 360)
              for w in lista]
    if any(not 0 <= w.velocidad_kmh <= 150 for w in manual):
        raise ValueError("velocidad de viento fuera de rango")
    return simular(lon, lat, hora, (manual[0] if len(manual) == 1 else manual) or None)


def simular_presa(peticion: dict) -> dict:
    """Valida la alerta de rotura de presa recibida y lanza la simulación."""
    from datetime import datetime
    from .incendio.entradas import MADRID
    from .presa.simulacion import simular
    if not isinstance(peticion, dict):
        raise ValueError("se esperaba un objeto JSON")
    presa = str(peticion["presa"])
    hora = datetime.fromisoformat(peticion["hora"]) if peticion.get("hora") else datetime.now(MADRID)
    hora = hora.replace(tzinfo=MADRID) if hora.tzinfo is None else hora
    if not 2000 <= hora.year <= 2100:
        raise ValueError("fecha fuera de rango")
    return simular(presa, hora)


class Servidor(ThreadingHTTPServer):
    """En Windows, SO_REUSEADDR deja abrir un puerto ya ocupado y seguiría respondiendo el servidor anterior:
    se desactiva para que un segundo servidor en el mismo puerto falle al arrancar."""
    allow_reuse_address = os.name != "nt"
    daemon_threads = True


def crear_servidor(puerto: int = 8765) -> ThreadingHTTPServer:
    return Servidor(("127.0.0.1", puerto), Manejador)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--puerto", type=int, default=8765)
    p.add_argument("--sin-conexion", action="store_true",
                   help="mapa base, relieve, ortofoto y tipografías solo desde la copia local (defensa sin red)")
    a = p.parse_args(argv)
    if a.sin_conexion:
        from . import sin_conexion
        sin_conexion.activar()
    try:
        servidor = crear_servidor(a.puerto)
    except OSError as e:
        raise SystemExit(f"No se puede abrir el puerto {a.puerto}: ¿hay otro servidor de Cascada abierto? ({e})")
    print(f"Cascada en http://localhost:{a.puerto}  (Ctrl+C para parar)"
          + ("  [sin conexión: solo la copia local]" if a.sin_conexion else ""), flush=True)
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print("\nServidor parado")


if __name__ == "__main__":
    main()
