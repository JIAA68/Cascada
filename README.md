# Cascada

Riesgos potenciales sobre la población con menor capacidad de autoprotección en la Comunidad de Madrid.

Cascada cruza las capas de peligrosidad del **Catálogo de Riesgos Potenciales de la Comunidad de Madrid** con los **centros donde se concentra la población más vulnerable** (centros educativos, hospitales y centros de diálisis, centros de atención social); anticipa a siete días, con la previsión y los avisos de AEMET, dónde el tiempo activa esos riesgos; y, ante un incendio forestal, estima su evolución y el momento en que alcanza a cada centro. Está pensada para gestores institucionales de protección civil.

Es un demostrador: se ejecuta en local, sin usuarios ni credenciales, y todo lo que muestra se regenera desde las fuentes oficiales con un solo comando.

**Vídeo y presentación:**

- [Simulación de un incendio](https://youtu.be/hQ1-rvie1xQ) (vídeo en YouTube). Ignición junto a Torrejón de la Calzada un día de julio a las 15:00, con viento del oeste a 20 km/h, reproducida minuto a minuto durante 24 horas, con rótulos en los momentos clave.
- [Presentación ejecutiva](presentacion/cascada_presentacion.pdf) (PDF, 7 diapositivas).

## Qué hace

**Análisis basal.** Mapa de la Comunidad con las 13 capas de peligrosidad del catálogo (naturales y tecnológicas) y los centros, agrupados por familia y subtipo. Al marcar un grupo entero se muestra el nivel máximo del grupo en cada punto, no la superposición de sus capas. Al hacer clic en un punto se analiza la celda de 1 km de la rejilla europea que lo contiene: riesgos presentes con su nivel máximo y el porcentaje de celda que cubren, población del Censo 2021 (con menores de 16 y mayores de 64) y centros que contiene. Al hacer clic en un centro se muestran sus riesgos, calculados con la matriz peligrosidad × vulnerabilidad del propio catálogo.

**Prealerta a 7 días.** Para cada uno de los próximos siete días y cada uno de los 179 municipios, la previsión municipal de AEMET (diaria, y horaria a tres días cuando anuncia lluvia, tormenta o nieve) se traduce a los niveles del Plan Meteoalerta (verde, amarillo, naranja, rojo) con los umbrales oficiales de su zona de aviso; donde hay aviso oficial de AEMET, manda el aviso. El peligro meteorológico de incendio se calcula con el índice de Fosberg. El mapa colorea los municipios por nivel, dibuja las tres zonas de aviso y marca los centros con riesgo focal: los afectados directamente por el calor, el frío o la nieve, y aquellos en los que el fenómeno activa un peligro del catálogo (viento o sequedad sobre zonas de incendio forestal, lluvias sobre zonas inundables, nieve sobre carreteras…). Las 13 capas de peligrosidad meteorológica del catálogo se ofrecen como contexto.

**Gestión de crisis por incendio.** Una alerta en un punto (clic en el mapa o foco de calor detectado por satélite) arranca una simulación de 24 horas: velocidad de propagación de Rothermel con el mapa de modelos de combustibles de la Comunidad de Madrid (EFFIS fuera de ella), el relieve del IGN y el viento de AEMET o introducido a mano, y ruta del fuego por tiempo mínimo de recorrido en celdas de 50 m, en una zona de cálculo de 50 × 50 km. El resultado se reproduce en el mapa minuto a minuto: área quemada, frente activo, humo viento abajo, centros alcanzados, instalaciones Seveso y conducciones que despliegan su propia amenaza al ser alcanzadas, carreteras, trenes de Cercanías, poblaciones y municipios afectados, y los habitantes de las celdas de 1 km que toca el fuego. A partir del instante mostrado se generan dos comunicaciones ficticias: un mensaje para redes sociales y un aviso ES-Alert, tal como saldrían (no se publica ni se envía nada).

Los métodos, supuestos y limitaciones están en [docs/metodologia.md](docs/metodologia.md), y la descripción técnica completa del demostrador, en [docs/memoria_demostrador.md](docs/memoria_demostrador.md).

## Requisitos

- Python 3.12 o superior.
- Conexión a internet: para descargar las fuentes la primera vez, para el mapa base del IGN (sin red, una copia guardada de antemano; ver «Sin conexión»); en la prealerta, para la previsión y los avisos de AEMET; en la gestión de crisis, para el relieve (IGN), el viento (AEMET) y los focos de calor (NASA FIRMS); y, si se encienden, para los trenes (Renfe) y el tráfico (Ayuntamiento de Madrid y DGT) en tiempo real. El viento puede introducirse a mano si AEMET no responde; la prealerta guarda la última previsión recibida.
- Alrededor de 1 GB de disco para las descargas, los resultados y las teselas, y otros 2 GB si se prepara el modo sin conexión.

## Instalación

```bash
python -m venv .venv
```

```bash
.venv\Scripts\pip install -r requirements.txt
```

En Linux o macOS, `.venv/bin/pip` y `.venv/bin/python` en lugar de `.venv\Scripts\...`.

Para el viento y la previsión de AEMET, copia `.env.ejemplo` como `.env` y escribe en él tu clave de [AEMET OpenData](https://opendata.aemet.es) (gratuita). El fichero `.env` no se sube al repositorio. Sin clave, el visor ofrece el viento a mano, la prealerta solo puede mostrar los avisos oficiales (que van por el canal público, sin clave) y la cadena de datos omite la validación con el caso de Tres Cantos, que necesita la racha registrada por AEMET.

## Reproducir los datos

Un solo comando descarga las fuentes oficiales que falten, registra cada descarga (URL, fecha, huella SHA-256) y construye los activos, el análisis basal, las teselas de las 13 capas y la base de la prealerta (municipios, zonas de aviso de AEMET, capas meteorológicas del catálogo en cada activo y sus teselas hasta el zoom 11):

```bash
.venv\Scripts\python -m procesamiento.cadena
```

Las descargas que ya están en disco se reutilizan; el análisis basal y las teselas se vuelven a calcular. `--sin-teselas` omite las teselas y `--zoom-max N` limita su nivel de detalle (15 por defecto, la resolución del catálogo; las capas meteorológicas de la prealerta llegan al 11). Las teselas de las 13 capas de peligrosidad son la parte lenta de la cadena, alrededor de una hora.

Las descargas quedan anotadas en [datos/registro.csv](datos/registro.csv) (fuentes de la cadena, se publica) y en `datos/cache/registro.csv` (descargas de uso: AEMET, FIRMS, relieve de cada simulación, trenes y tráfico; no se publica).

## Ejecutar el visor

```bash
.venv\Scripts\python -m procesamiento.servidor
```

y abrir <http://localhost:8765>. Es un único servidor en Python que sirve el visor, los ficheros de datos con peticiones por rangos (lo que necesita PMTiles) y la API local:

| Método y ruta | Qué devuelve |
|---|---|
| `GET /api/municipios` | Municipios para el buscador: nombre, recuadro y punto de su capital |
| `GET /api/resumen` | Población de las celdas de 1 km que cubren la Comunidad, para la ventana de datos del arranque |
| `GET /api/celda?lon=&lat=` | Análisis basal de la celda de 1 km que contiene el punto |
| `GET /api/activo?id=` | Ficha común y riesgos de un centro |
| `GET /api/focos` | Focos de calor de NASA FIRMS en la Comunidad (últimas 24 h) |
| `POST /api/incendio` | Simula un incendio. Cuerpo JSON: `lon`, `lat`, `hora` (opcional, ISO local), `viento` (opcional: `velocidad_kmh`, `desde`) o `vientos` (opcional: lista hora a hora, hasta 25); sin viento se usa AEMET |
| `GET /api/incendio/llegada?id=` | Mapa de tiempos de llegada de una simulación (enteros de 16 bits, minutos) |
| `GET /api/validacion` | Caso de validación del modelo de incendio (Tres Cantos, 2025): simulación guardada, perímetro de EFFIS, focos de satélite y métricas |
| `GET /api/incendio/movilidad?id=` | Trenes, incidencias de la DGT y tráfico de la ciudad actuales que el fuego o el humo de una simulación alcanzarían |
| `GET /api/trenes` | Trenes de viajeros de Renfe en la Comunidad (tiempo real) |
| `GET /api/trafico` | Tráfico de la ciudad de Madrid e incidencias de la DGT (tiempo real) |
| `GET /api/prealerta` | Prealerta a 7 días: nivel de cada municipio y día, resumen diario de la Comunidad y avisos oficiales |
| `GET /api/prealerta/municipio?codigo=&dia=` | Detalle de un municipio (sus siete días) y sus centros con riesgo focal el día pedido (índice 0 a 6 o fecha) |
| `GET /api/prealerta/activos?dia=` | Centros de toda la Comunidad con riesgo focal un día |
| `POST /api/prealerta/actualizar` | Vuelve a pedir la previsión a AEMET, en segundo plano |

Solo escucha en la propia máquina. El puerto se cambia con `--puerto`.

## Sin conexión

Las librerías del visor (MapLibre GL JS y PMTiles) van en `visor/vendor/`. Con red, el visor pide el mapa base, el relieve y la ortofoto directamente al IGN. Para una demostración sin red, se descargan de antemano en `datos/cache/externo/` las teselas de toda la Comunidad hasta el zoom 13 (y, si se quiere, una zona con más zoom), las tipografías del mapa y el MDT de 25 m de toda la Comunidad, con el que se puede simular en cualquier punto; opcionalmente se deja calculada una simulación con viento a mano:

```bash
.venv\Scripts\python -m procesamiento.sin_conexion --lon -3.80629 --lat 40.21090 --radio-km 25 --zoom-max 14 --simular --hora 2026-07-15T15:00 --viento 20,270
```

Ocupa alrededor de 2 GB. Después se arranca el servidor sin conexión: el visor pide entonces el mapa a la copia guardada (y amplía las teselas del zoom 13 al acercarse), y cualquier petición a internet falla en el acto, para que nada se quede esperando a una red que no hay:

```bash
.venv\Scripts\python -m procesamiento.servidor --sin-conexion
```

Sin red funcionan el análisis basal, la gestión de crisis con viento a mano en cualquier punto de la Comunidad, el caso de validación y la prealerta con la última previsión guardada. No funcionan el viento de AEMET, los focos de FIRMS, los trenes y el tráfico en tiempo real.

Una simulación también puede lanzarse desde la línea de comandos (el punto debe tener combustible forestal):

```bash
.venv\Scripts\python -m procesamiento.incendio.simulacion --lon -3.80629 --lat 40.21090 --hora 2026-07-15T15:00 --viento 20,270
```

## Pruebas

```bash
.venv\Scripts\python -m pytest
```

Incluyen la validación de la implementación de Rothermel frente a las tablas de Anderson (1982) y la relación largo/ancho de Anderson (1983), la propagación (cambio de viento sin efecto hacia atrás, independencia del rumbo respecto de la rejilla, barreras sin combustible, salto de franjas), el humo, la cadena de datos, la prealerta (umbrales, índice de Fosberg, lectura de la previsión y de los avisos CAP de AEMET con muestras locales, cálculo por municipio), la validación con casos reales (lectura del viento de la Red de Calidad del Aire y métricas a hora fija frente a un modelo nulo), el modo sin conexión y la API. No necesitan conexión.

## Estructura del repositorio

```
cascada/
├── README.md
├── LICENSE                EUPL 1.2
├── requirements.txt
├── .env.ejemplo           plantilla de claves (el .env real no se publica)
├── docs/                  memoria del demostrador y metodología
├── presentacion/          vídeo de una simulación y presentación ejecutiva en PDF
├── datos/
│   ├── registro.csv       URL, fecha y huella de cada descarga de la cadena
│   ├── brutos/            descargas (no se suben al repositorio)
│   ├── cache/             descargas de uso y extracciones (no se suben)
│   ├── procesados/        resultados intermedios y simulaciones (no se suben)
│   └── visor/             ficheros que sirve el servidor: PMTiles, GeoJSON (no se suben)
├── procesamiento/         cadena de datos, análisis basal, servidor y API
│   ├── incendio/          modelo de incendio: combustibles, Rothermel, propagación,
│   │                      entradas, consecuencias, humo, focos, simulación y validación
│   ├── prealerta/         prealerta: territorio y zonas de aviso, previsión y avisos de
│   │                      AEMET, umbrales de Meteoalerta y Fosberg, cálculo y servicio
│   └── pruebas/           pruebas con pytest (con muestras de AEMET en pruebas/datos/)
└── visor/                 web con MapLibre GL JS (análisis basal, prealerta y gestión de crisis)
```

## Datos personales y centros sensibles

Los ficheros publicados no contienen NIF, teléfonos, correos ni webs de los centros. Los 177 centros sociales en los que la propia Comunidad de Madrid reserva algún dato (la dirección o el teléfono; sobre todo de menores y de mujeres) no se ubican por ningún medio. En los centros de colectivos protegidos, el rótulo del mapa se queda en el tipo de centro, sin el colectivo. `datos/procesados/activos.csv` y `activos_basal.csv` se regeneran en local y no se suben al repositorio. Tampoco se sube `instalaciones_seveso.csv`, la posición de las instalaciones Seveso deducida de las zonas del catálogo.

## Fuentes, licencias y atribuciones

| Fuente | Organismo | Licencia | Uso |
|---|---|---|---|
| Catálogo de Riesgos Potenciales: capas de peligrosidad (5 m) | Comunidad de Madrid (geoportal IDEM) | CC BY 4.0 | Amenazas |
| Centros educativos | Comunidad de Madrid (datos.comunidad.madrid) | CC BY | Activos |
| Centros, servicios y establecimientos sanitarios | Comunidad de Madrid (datos.comunidad.madrid) | CC BY | Activos |
| Registro de centros de atención social | Comunidad de Madrid (datos.comunidad.madrid) | CC BY | Activos y plazas |
| Municipios y distritos de Madrid (2020) | Comunidad de Madrid (datos.comunidad.madrid) | CC BY | Límites y municipios alcanzados |
| Censo 2021 en rejilla europea de 1 km | INE | Condiciones de reutilización del INE | Población por celda |
| Mapa base vectorial, ortofoto PNOA y MDT (25 m y teselas de relieve) | IGN (CNIG) | CC BY 4.0 | Mapa base operativo, ortofoto, relieve y pendiente del modelo de incendio |
| Nomenclátor Geográfico Básico de España (servicio WFS INSPIRE de nombres geográficos): capitales de municipio, núcleos de población y entidades menores | IGN (CNIG) | CC BY 4.0 | Núcleos de población a los que llega el incendio |
| Mapa de modelos de combustibles (LiDAR, 433.681 polígonos, modelos NFFL) | Comunidad de Madrid (IDEM, servicio WFS) | CC BY 4.0 | Modelo de incendio dentro de la Comunidad |
| Mapa europeo de combustibles (NFFL) | Copernicus EFFIS (JRC) | CC BY 4.0 | Modelo de incendio fuera de la Comunidad |
| Observación convencional, predicción horaria y predicción diaria por municipio | AEMET OpenData | Condiciones de reutilización de AEMET | Viento del modelo de incendio; previsión de la prealerta |
| Avisos del Plan Meteoalerta (ficheros CAP del canal público) y delimitación de las zonas de aviso | AEMET | Condiciones de reutilización de AEMET | Prealerta: avisos oficiales y zonas |
| Avisos meteorológicos de España (respaldo si AEMET no responde) | Meteoalarm (EUMETNET) | Licencia equivalente a CC BY 4.0 | Prealerta |
| Focos de calor VIIRS (Suomi NPP, NOAA-20, NOAA-21) | NASA FIRMS | Datos abiertos de la NASA | Alertas automáticas; focos de 2025 para validar el modelo |
| Áreas quemadas (perímetros) | Copernicus EFFIS (JRC) | CC BY 4.0 | Validación del modelo de incendio (Tres Cantos, 2025) |
| Red de Calidad del Aire: datos meteorológicos horarios | Comunidad de Madrid (datos.comunidad.madrid) | CC BY | Viento medido para validar el modelo |
| Base Topográfica Armonizada 2017 (1:10.000): red viaria y ferroviaria | Comunidad de Madrid (geoportal IDEM, servicio WFS) | CC BY 4.0 | Carreteras y vías de tren afectadas por el incendio |
| Posiciones de los trenes de viajeros (GTFS-Realtime) | Renfe (data.renfe.com) | CC BY 4.0 | Trenes en tiempo real |
| Horario de Cercanías (GTFS estático, 30 días) | Renfe (data.renfe.com) | CC BY 4.0 | Trenes programados que pasan por estaciones afectadas |
| Tráfico en tiempo real (puntos de medida) | Ayuntamiento de Madrid, portal de datos abiertos | CC BY 4.0 | Tráfico de la ciudad |
| Incidencias en carretera (DATEX II v3.7) | DGT, punto de acceso nacional | Creative Commons Reconocimiento (la ficha del conjunto no indica la versión) | Incidencias en toda la Comunidad |

Atribuciones: datos de la Comunidad de Madrid (Catálogo de Riesgos Potenciales y portal de datos abiertos); © Instituto Geográfico Nacional (mapa base, ortofoto PNOA y modelo digital del terreno); Fuente: INE, Censo de Población 2021; © AEMET, información elaborada a partir de datos de la Agencia Estatal de Meteorología; Copernicus Emergency Management Service, European Forest Fire Information System (EFFIS); NASA FIRMS, Fire Information for Resource Management System; Renfe (CC BY 4.0); Ayuntamiento de Madrid, portal de datos abiertos; Dirección General de Tráfico, punto de acceso nacional de información de tráfico.

Modelos: Rothermel, R. C. (1972), *A mathematical model for predicting fire spread in wildland fuels*; Albini, F. A. (1976), *Estimating wildfire behavior and effects*; Anderson, H. E. (1982), *Aids to determining fuel models for estimating fire behavior*; Finney, M. A. (2002), *Fire growth using minimum travel time methods*; Fosberg, M. A. (1978), *Weather in wildland fire management: the fire weather index*; umbrales del Plan Meteoalerta de AEMET (anexo 1, 2022). Implementación propia, sin dependencias de modelos de terceros.

Software: Python con NumPy, pandas, SciPy, rasterio, pyproj, Shapely y pyogrio (licencias BSD y MIT); PMTiles (BSD); MapLibre GL JS (BSD). Mapa base y ortofoto por WMTS del IGN.

## Licencia

© 2026 José Ignacio Atance. Código bajo la [Licencia Pública de la Unión Europea 1.2](LICENSE) (EUPL 1.2). Los datos conservan la licencia de su fuente.
