# Cascada: memoria del demostrador

Describe lo que está implantado y funcionando en el demostrador. Lo que el diseño prevé y no está construido se indica como tal en el apartado 15. Las cifras proceden de los datos oficiales descargados por la cadena de datos y de las ejecuciones del propio demostrador.

## 1. Objeto

Cascada es una herramienta para gestores institucionales de protección civil. Cruza las capas de peligrosidad del Catálogo de Riesgos Potenciales de la Comunidad de Madrid con los centros donde se concentra la población con menor capacidad de autoprotección, que el proyecto denomina *activos*: centros educativos, hospitales y centros de diálisis, y centros de atención social. Sobre ese cruce ofrece tres capacidades:

- **Análisis basal:** qué riesgos estáticos hay en una zona y qué riesgos tiene cada activo.
- **Prealerta a 7 días:** dónde está el riesgo focal en los próximos siete días según la previsión y los avisos de AEMET: qué fenómenos afectan directamente a los activos y qué peligros del catálogo activan en cada municipio.
- **Gestión de crisis por incendio forestal:** a partir de una alerta en un punto, evolución estimada del incendio durante 24 horas, momento en que alcanza a cada activo, efecto cascada sobre instalaciones industriales y conducciones, humo, municipios afectados y comunicaciones ficticias.

El demostrador se ejecuta en local, sin usuarios ni credenciales, con un único servidor en Python y un visor web. Todo lo que muestra se regenera desde las fuentes oficiales con un comando.

## 2. Alcance

| Capacidad del diseño funcional | Estado en el demostrador |
|---|---|
| Riesgo basal (celda de 1 km y activo) | Implantado |
| Gestión de crisis: incendio forestal | Implantado |
| Gestión de crisis: efecto cascada Seveso y conducciones | Implantado como amenaza derivada del incendio |
| Comunicaciones ficticias (redes sociales y ES-Alert) | Implantado |
| Alertas automáticas por focos de satélite | Implantado |
| Prealerta a 7 días | Implantado; pendientes la primera previsión real y las teselas de las capas meteorológicas (apartado 8.6) |
| Gestión de crisis: nube tóxica o rotura de presa como crisis propia | No implantado |
| Simulacro | No implantado (el motor es el mismo; falta el marcado) |
| Ficha restringida | No implantado (solo ficha común) |
| Activos cercanos con deslizadores | No implantado |
| Activos dinámicos: trenes de viajeros en tiempo real | Implantado, con cruce en la gestión de crisis |
| Activos dinámicos: estaciones de tren | No implantado |
| Tráfico en tiempo real (ciudad de Madrid e incidencias de la DGT) | Implantado, con cruce en la gestión de crisis |
| Informes | No implantado |
| Validación del modelo de incendio con un caso real (Tres Cantos, 2025) | Implantado y calculado |
| Validación del modelo de incendio con siete incendios, a hora fija y frente a un modelo nulo | Calculado |

## 3. Fuentes de datos

### 3.1 Relación

| Fuente | Organismo | Licencia | Uso en el demostrador |
|---|---|---|---|
| Catálogo de Riesgos Potenciales, capas de peligrosidad (GeoTIFF de 5 m) | Comunidad de Madrid, geoportal IDEM | CC BY 4.0 | 13 capas del análisis basal (y dos combinadas por grupo derivadas de ellas), la de radiación térmica para el efecto cascada y las 14 meteorológicas de la prealerta |
| Centros educativos (CSV) | Comunidad de Madrid, portal de datos abiertos | CC BY | Activos educativos |
| Centros, servicios y establecimientos sanitarios (CSV) | Comunidad de Madrid, portal de datos abiertos | CC BY | Hospitales y centros de diálisis |
| Registro de centros de atención social (CSV) | Comunidad de Madrid, portal de datos abiertos | CC BY | Centros sociales y sus plazas |
| Municipios y distritos de Madrid, 2020 (shapefile) | Comunidad de Madrid, portal de datos abiertos | CC BY | Municipio de la ignición, municipios alcanzados, límite de la Comunidad para los focos |
| Censo 2021 en rejilla europea de 1 km (CSV) | INE | Condiciones de reutilización del INE | Población total, menores de 16 y mayores de 64 por celda |
| Mapa base y ortofoto PNOA (WMTS) | IGN | CC BY 4.0 | Fondo del mapa |
| Mapa base vectorial (teselas vectoriales) | IGN | CC BY 4.0 | Mapa base operativo: bosque, agua, núcleos urbanos, carreteras, ferrocarril y nombres |
| Modelo digital del terreno en teselas (raster-dem) | IGN | CC BY 4.0 | Relieve sombreado del mapa base |
| Modelo digital del terreno de 25 m (WCS INSPIRE, cobertura `Elevacion25830_25`) | IGN | CC BY 4.0 | Pendiente y orientación para el modelo de incendio |
| Mapa de modelos de combustibles (LiDAR, 433.681 polígonos, modelos NFFL) | Comunidad de Madrid (IDEM, servicio WFS) | CC BY 4.0 | Combustible por celda dentro de la Comunidad |
| Mapa europeo de combustibles, modelos NFFL (GeoTIFF de 250 m) | Copernicus EFFIS (JRC) | CC BY 4.0 | Combustible por celda fuera de la Comunidad |
| Observación convencional, predicción horaria y predicción diaria por municipio | AEMET OpenData | Condiciones de reutilización de AEMET | Viento de la primera hora y de las siguientes; previsión de la prealerta (diaria a 7 días y horaria a 3) |
| Avisos del Plan Meteoalerta (RSS público y ficheros CAP) y delimitación de las zonas de aviso (shapefile v6) | AEMET | Condiciones de reutilización de AEMET | Prealerta: avisos oficiales por zona y las tres zonas de Madrid |
| Avisos meteorológicos de España (JSON) | Meteoalarm (EUMETNET) | Licencia equivalente a CC BY 4.0 | Prealerta: respaldo de los avisos si AEMET no responde |
| Focos de calor VIIRS de Suomi NPP, NOAA-20 y NOAA-21 (CSV casi en tiempo real, Europa) | NASA FIRMS | Datos abiertos de la NASA | Alertas automáticas |
| Posiciones de los trenes de viajeros (GTFS-Realtime, JSON) | Renfe (data.renfe.com) | CC BY 4.0 | Trenes en tiempo real |
| Tráfico en tiempo real: puntos de medida (XML) | Ayuntamiento de Madrid | CC BY 4.0 (ficha del conjunto en datos.madrid.es y en datos.gob.es) | Tráfico de la ciudad |
| Incidencias en carretera (DATEX II v3.7, XML) | DGT, punto de acceso nacional | Creative Commons Reconocimiento, sin versión indicada (ficha «Incidencias DGT DATEX2 v3.7» del punto de acceso nacional) | Incidencias en toda la Comunidad |

Las librerías del visor (MapLibre GL JS 4.7.1 y PMTiles 3.2.1) van en `visor/vendor/`, con sus licencias (BSD de 3 cláusulas). El mapa base, el relieve y la ortofoto del IGN y las tipografías del mapa pasan por el servidor local, que guarda una copia (modo sin conexión, apartado 4.1). Lo demás se sirve desde el propio equipo.

Tres de las fuentes estatales pertenecen a categorías de **conjuntos de datos de alto valor** del Reglamento de Ejecución (UE) 2023/138, que garantiza su licencia abierta, su gratuidad y su acceso por API: geoespacial (IGN), meteorología (AEMET) y estadística (INE).

### 3.2 Trazabilidad

Cada fichero descargado se anota con su URL, la fecha de descarga en UTC, su huella SHA-256 y su tamaño. Hay dos registros:

- `datos/registro.csv`: fuentes de la cadena de datos (catálogo, centros, población, combustibles, municipios, zonas de aviso de AEMET). Se publica con el código.
- `datos/cache/registro.csv`: descargas de uso (AEMET, FIRMS, relieve de cada simulación, trenes y tráfico, previsión y avisos de la prealerta; de trenes y tráfico se guarda solo la última copia, en `datos/cache/tiempo_real/`; la previsión, en `datos/cache/prealerta/`). No se publica porque crece con cada uso.

Un fichero que ya está en disco no se vuelve a descargar. Un fichero en descarga se escribe con un nombre parcial y se renombra al terminar, de modo que una descarga interrumpida no deja un fichero a medias que se tome por bueno.

### 3.3 Sistema de referencia

Las capas del catálogo y las coordenadas de los centros están en ETRS89 UTM 30N (EPSG:25830). Esto se verificó con 34 direcciones de centros geocodificadas por CartoCiudad: la mediana de la desviación es de 0,4 a 1,5 m, frente a unos 235 m si se interpretaran en ED50. Las 47 capas del catálogo comparten exactamente la misma rejilla de 5 m, lo que permite leerlas por bloques alineados sin remuestrear.

El visor trabaja en longitud y latitud (EPSG:4326) y en Web Mercator (EPSG:3857) para las teselas; la rejilla de población es la europea en EPSG:3035; el modelo de incendio trabaja en EPSG:25830. Las conversiones se hacen con pyproj.

## 4. Arquitectura

### 4.1 Componentes

```
Fuentes oficiales ──► Cadena de datos (Python) ──► datos/procesados, datos/visor
                                                          │
                                        Servidor local (Python, puerto 8765)
                                          ├── visor/ (HTML, CSS, JS)
                                          ├── datos/visor/ con peticiones por rangos
                                          ├── /externo/: copia del mapa del IGN y tipografías (solo sin conexión)
                                          └── API: celda, activo, focos, incendio, llegada,
                                              movilidad, trenes, tráfico, prealerta
                                                          │
                                             Navegador: MapLibre GL JS + PMTiles
```

- **Cadena de datos** (`procesamiento/`): descarga, activos, análisis basal, teselas, capas combinadas por grupo, núcleos urbanos y base de la prealerta (municipios, zonas de aviso, capas meteorológicas de cada activo). Se ejecuta una vez y cuando cambian las fuentes.
- **Servidor** (`procesamiento/servidor.py`): un único proceso basado en `http.server` de la biblioteca estándar, con hilos, que escucha solo en 127.0.0.1. Sirve el visor, los ficheros de datos con soporte de rangos HTTP (respuestas 206, cabeceras `Accept-Ranges`, `Content-Range`, y 416 para rangos inválidos) y la API en JSON. Comprueba que ninguna ruta salga de las carpetas servidas.
- **Motor de incendio** (`procesamiento/incendio/`): se ejecuta bajo demanda desde la API o desde la línea de comandos.
- **Prealerta** (`procesamiento/prealerta/`): previsión y avisos de AEMET en caché, umbrales, cálculo por municipio y día, y un servicio que el servidor consulta y que actualiza la previsión en segundo plano (apartado 8).
- **Visor** (`visor/`): una página con tres modos, análisis basal, prealerta y gestión de crisis, sin framework ni compilación.

### 4.2 Tecnologías

Python 3.12 o superior con NumPy, pandas, SciPy, rasterio (GDAL), pyproj, Shapely, pyogrio, pmtiles y pytest. En el navegador, MapLibre GL JS 4.7 y el protocolo PMTiles 3.2. No se usa ningún servicio propietario: el fondo es el WMTS del IGN y las teselas de riesgo se sirven desde el propio equipo.

### 4.3 Tamaño del código

Unas 10.700 líneas en total: 8.280 de Python (de ellas 1.750 de pruebas) y 2.450 de HTML, CSS y JavaScript, sin contar las librerías de `visor/vendor/`.

## 5. Cadena de datos

Un comando ejecuta toda la cadena:

```
python -m procesamiento.cadena [--sin-teselas] [--zoom-max 13]
```

Pasos:

1. **Fuentes oficiales.** Descarga, si faltan, los tres CSV de centros, la población del INE, los municipios y los zips de las 13 capas basales, de las 13 meteorológicas (1_1 a 1_13) y de torrencialidad en cauces (2_2); extrae cada GeoTIFF de su zip a la caché, porque leer por ventanas dentro del zip es muy lento.
2. **Activos y análisis basal.** Construye los activos y, en una sola pasada por bloques de 512 filas sobre las 13 capas, la rejilla de 1 km y los riesgos de cada activo (apartado 6).
3. **Teselas.** Genera un fichero PMTiles por capa (apartado 5.3).
4. **Capas combinadas por grupo.** Nivel máximo de las cinco capas naturales, y de las ocho tecnológicas, en cada píxel de 5 m, sin el fondo de incendios y avión (`procesamiento/combinadas.py`; GeoTIFF teselado y comprimido en la caché), y sus teselas (apartado 5.3).
5. **Núcleos urbanos.** Extrae de las teselas de zoom 12 del mapa base vectorial del IGN los núcleos urbanos y las manzanas de CartoCiudad y los funde en manchas para las escalas pequeñas (apartado 6.4).
6. **Prealerta.** Municipios con los distritos de la capital unidos, zonas de aviso de AEMET y municipio de cada activo; nivel de las 14 capas meteorológicas y de torrencialidad en el punto de cada activo (apartado 8.1).
7. **Teselas meteorológicas.** Las 13 capas meteorológicas hasta el zoom 11, con el nivel más frecuente.

Lo que ya existe en disco se reutiliza, de modo que repetir el comando es rápido.

### 5.1 Activos

Se leen los tres conjuntos del portal de datos (separador `;`, UTF-8 con BOM, coordenadas UTM con coma decimal) y se aplica este filtrado:

| Familia | Filtro | Subtipos | Resultado |
|---|---|---|---|
| Educativos | Solo centros en situación de alta. Entran por código de tipo: infantil (escuelas infantiles y casas de niños), primaria y secundaria (incluidos los colegios extranjeros en España), educación especial (incluidas aulas hospitalarias y centros educativo-terapéuticos). Salen adultos, enseñanzas artísticas e idiomas, FP específica, deportivas, universidades, equipos de orientación y administrativos | infantil, primaria_secundaria, educacion_especial | 3.163 |
| Sanitarios | Un registro por número de registro del centro. Entran hospitales generales, especializados, de media y larga estancia, de salud mental y otros centros con internamiento, y centros de diálisis. El conjunto no publica el nombre del centro, así que se muestra su tipo | hospital, dialisis | 105 (93 y 12) |
| Atención social | Entran todos. Residenciales son los tipos "centros residenciales" y "centros de acogida"; el resto, de día | residencial, de_dia | 2.643 |

De los 5.911 activos, **5.630 tienen ubicación**. 177 centros sociales tienen algún dato marcado como reservado por la propia Comunidad (175, la dirección, el municipio, las coordenadas y el teléfono; 2, solo el teléfono) y no se ubican por ningún medio; 104 tienen las coordenadas vacías. Ninguno de los tres conjuntos contiene NIF de personas físicas.

A cada activo se le asigna una **vulnerabilidad** según la capacidad de autoprotección de sus ocupantes y si hay gente durmiendo en el centro:

| Vulnerabilidad | Nivel | Activos | Ubicados |
|---|---|---|---|
| Muy alta | 5 | Hospitales; centros sociales residenciales; educación especial, aulas hospitalarias y centros educativo-terapéuticos | 1.061 |
| Alta | 4 | Escuelas infantiles; centros de diálisis; residencias de personas mayores autónomas, pisos tutelados y viviendas comunitarias de adultos autónomos | 1.798 |
| Moderada | 3 | Primaria y secundaria; centros sociales de día | 2.562 |
| Baja | 2 | Hogares y clubes de mayores | 211 |

**Centros sensibles:** son los 177 en los que la propia Comunidad reserva algún dato, que suman 3.071 plazas autorizadas. Cascada sigue el criterio de la Comunidad: lo que ella publica se muestra, y lo que reserva no se ubica (tampoco los dos centros de mujeres que solo tienen el teléfono reservado, aunque traigan coordenadas). Como casi todos tienen también el municipio reservado, no pueden contarse por celda, municipio ni zona afectada; se dan solo como total en esta memoria. Los demás centros sociales se muestran como cualquier otro, también los 731 de sectores como pisos de refugiados, de personas sin hogar o de familias y centros de atención a la infancia. En los de colectivos protegidos el rótulo se queda en el tipo de centro («Piso tutelado», «Centro de atención»), sin el colectivo, que señalaría la vivienda; los de mayores, discapacidad y enfermedad mental lo llevan («Residencia de mayores», «Centro ocupacional · discapacidad intelectual»).

Salida: `datos/procesados/activos.csv` con identificador (prefijo EDU, SAN o SOC más el código del conjunto de origen), familia, subtipo, vulnerabilidad, marca de sensible, nombre, municipio, plazas, coordenadas UTM y longitud y latitud. No lleva NIF, teléfonos, correos ni webs.

### 5.2 Capas de peligrosidad

Se usan las capas de **peligrosidad** del catálogo, no las de riesgo, porque estas ya incorporan una vulnerabilidad que incluye colegios, residencias y hospitales y producirían doble cómputo.

| Grupo | Capa | Código |
|---|---|---|
| Naturales | Incendios forestales | 3_1 |
| Naturales | Avenidas y crecidas | 2_1 |
| Naturales | Rotura de presas | 2_3 |
| Naturales | Derrumbes y colapso de edificaciones | 6_27 |
| Naturales | Subsidencias | 5_4 |
| Tecnológicos | Nube tóxica | 6_3 |
| Tecnológicos | Sobrepresión por explosión | 6_4 |
| Tecnológicos | Centrales energéticas | 6_11 |
| Tecnológicos | Transporte de energía | 6_12 |
| Tecnológicos | Transporte por carretera | 6_16 |
| Tecnológicos | Transporte por tren | 6_15 |
| Tecnológicos | Transporte por avión | 6_14 |
| Tecnológicos | Actividades extractivas | 6_6 |

Para el efecto cascada se usa además la capa de radiación térmica (6_5).

Codificación: 0 sin peligro, 1 a 5 de muy baja a muy alta, 255 fuera de la Comunidad. Cada GeoTIFF tiene unos 740 millones de píxeles. Cada capa usa un tramo distinto de la escala: nube tóxica, sobrepresión y radiación térmica llegan a 2 (zona de alerta y zona de intervención); rotura de presas a 2 (plana de inundación y primeros 30 minutos); transporte de energía, centrales y actividades extractivas a 3; incendios forestales, avenidas y derrumbes usan la escala completa. El nivel no mide lo mismo en todas las capas: en avenidas es el periodo de retorno, en las industriales la intensidad del daño según la zona de planificación, en derrumbes la frecuencia histórica de intervenciones por municipio o distrito. Incendios forestales y avión asignan nivel 1 a todo el territorio como fondo.

### 5.3 Teselas

Cada capa se convierte en un fichero PMTiles (`datos/visor/capas/peligrosid_<código>.pmtiles`) con teselas PNG de 256 píxeles en Web Mercator, de zoom 7 a 15 (3,6 m por píxel en el 15, la resolución de los 5 m del catálogo). Cada tesela se reproyecta desde la capa de 5 m, y la forma de agregar los píxeles de origen que caen en cada píxel de destino depende del tipo de capa:

- **Capas de superficie** (incendios forestales, subsidencias, avión): el **nivel más frecuente**. Con el máximo, al alejarse casi toda la Comunidad aparecería en el nivel más alto.
- **Resto de capas**: el **máximo**, para que los elementos finos o pequeños (vías, carreteras, conducciones, cauces, instalaciones, y los edificios en derrumbes, cuya peligrosidad va por edificio) no desaparezcan al alejarse.

Las tres capas lineales (tren, carretera, transporte de energía) se engrosan a 3 píxeles en todos los zooms. Las de elementos pequeños (sobrepresión, centrales energéticas, actividades extractivas) se engrosan a 7 píxeles hasta el zoom 9, 5 hasta el 11 y 3 en el 12, para que sigan viéndose a escala de la Comunidad. Para los zooms bajos se usa una pirámide reducida en memoria (máximo por bloque, o nivel más frecuente por etapas de 2 × 2), de modo que GDAL no tenga que leer la capa completa de 5 m para cada tesela. El valor "sin dato" de destino es 255, no 0, porque GDAL convertiría los ceros válidos en 1.

**Capas combinadas por grupo.** Al marcar un grupo entero, el visor no superpone sus capas (con una sola paleta, el color sería el de la capa dibujada encima), sino que muestra una capa combinada con el nivel máximo del grupo en cada píxel, sin el fondo de incendios y avión; una capa suelta y la combinada de su grupo no se ven a la vez. Se teselan como las de superficie (nivel más frecuente al alejarse) y sin borde, porque son muy fragmentadas.

Paleta cálida por nivel absoluto, del amarillo al granate, con los niveles bajos saturados para que las capas que no pasan de nivel 2 o 3 se lean sobre el mapa base. Cada zona lleva un borde del mismo color oscurecido, salvo el fondo, las capas lineales y las muy fragmentadas (incendios y derrumbes), donde el borde se convertiría en un punteado oscuro. El nivel 1 de fondo de incendios y avión se pinta casi transparente. Hasta el zoom 15, los 13 ficheros ocupan unos 110 MB (incendios 46 MB, derrumbes 17, carretera 16, avenidas 9, avión 7; el resto, de 0,2 a 5 MB) y las dos capas combinadas 65 MB.

### 5.4 Rejilla de 1 km y población

Se usa la rejilla europea de 1 km (INSPIRE/Eurostat, EPSG:3035), la misma en que el INE publica el Censo 2021, con el mismo identificador de celda (`CRS3035RES1000mN<norte>E<este>`). Cada píxel de 5 m se asigna a la celda que contiene su centro. Para cada celda y capa se calcula el nivel máximo y el porcentaje de la parte de la celda que está dentro de la Comunidad con peligro (en incendios y avión no cuenta el nivel 1). Se añaden la fracción de celda dentro de la Comunidad, la población (total, menores de 16, mayores de 64; el INE la redondea a múltiplos de 5), y el número de activos, de centros sensibles y de plazas sensibles de la celda.

Resultado: 8.473 celdas con una población total de 6.756.230 habitantes (1.067.280 menores de 16 y 1.212.735 mayores de 64). Salida: `datos/procesados/rejilla_1km.csv`.

## 6. Análisis basal

### 6.1 Riesgo de un activo

Para cada capa, la peligrosidad del píxel de 5 m en el punto del activo se cruza con su vulnerabilidad mediante la matriz del propio catálogo (memoria metodológica, apartado 3, cartografías de riesgo):

| Vulnerabilidad ↓ / Peligrosidad → | Muy baja | Baja | Moderada | Alta | Muy alta |
|---|---|---|---|---|---|
| Muy baja | Muy bajo | Muy bajo | Bajo | Bajo | Moderado |
| Baja | Muy bajo | Bajo | Moderado | Moderado | Moderado |
| Moderada | Bajo | Moderado | Moderado | Alto | Alto |
| Alta | Bajo | Moderado | Alto | Alto | Muy alto |
| Muy alta | Moderado | Alto | Alto | Muy alto | Muy alto |

Consecuencias documentadas: las capas que nunca pasan de peligrosidad baja (nube tóxica, sobrepresión, presas) dan como máximo riesgo alto, incluso en un hospital; una peligrosidad muy baja sobre un centro de vulnerabilidad muy alta da riesgo moderado. **El nivel 1 de fondo de incendios y avión no da riesgo**: cubre todo el territorio y no distingue un centro de otro. Con este criterio, 48 activos cuyo único riesgo sería ese fondo (39 con riesgo bajo y 9 con moderado) quedan sin riesgo.

Para cada activo se guardan el nivel y el riesgo de cada capa, el riesgo máximo, el número de amenazas presentes (sin contar el fondo, que tampoco da riesgo) y su celda. Salida: `datos/procesados/activos_basal.csv` (incluye los sensibles; no se publica) y `datos/visor/activos.geojson` (solo no sensibles, sin datos personales).

Distribución del riesgo máximo entre los 5.632 activos ubicados: muy alto 232, alto 2.181, moderado 2.838, bajo 364, muy bajo 17.

Activos con peligrosidad de nivel 2 o más por capa: subsidencias 4.003; incendios forestales 2.345; derrumbes 1.894; transporte de energía 1.111; avión 1.034; carretera 358; nube tóxica 112; avenidas 33; sobrepresión 29; presas 22; tren 4; actividades extractivas 2; centrales 0. Cuatro capas dominan cualquier recuento por su extensión (subsidencias, incendios, derrumbes y transporte de energía). Derrumbes es una media municipal asignada a cada edificio y subsidencias es un fenómeno lento: las capas que discriminan de verdad entre centros son las de menor extensión.

### 6.2 Consulta de celda

`GET /api/municipios` devuelve, para el buscador, los 179 municipios con su código, su nombre, el recuadro de su término y el punto de su capital en el Nomenclátor del IGN (la que cae dentro del término; si no hay ninguna, un punto interior).

`GET /api/resumen` devuelve el número de celdas de 1 km que cubren la Comunidad y la suma de su población, menores de 16 y mayores de 64 (Censo 2021), para la ventana «Datos del visor» del arranque.

`GET /api/celda?lon=&lat=` devuelve, para la celda de 1 km que contiene el punto: identificador, contorno en lon/lat para dibujarla, fracción dentro de la Comunidad, población, lista de riesgos presentes (código, nombre, grupo, nivel máximo, nombre del nivel y porcentaje; sin el fondo de incendios y avión), lista de activos no sensibles con su riesgo máximo y número de amenazas, y el recuento de centros sensibles y sus plazas. Fuera de la Comunidad responde 404.

### 6.3 Consulta de activo

`GET /api/activo?id=` devuelve la ficha común de un activo no sensible: identificador, familia, subtipo, nombre, municipio, vulnerabilidad, plazas, coordenadas, riesgo máximo, número de amenazas y la lista de riesgos por capa (peligrosidad, riesgo y si es solo fondo, en cuyo caso el riesgo es «sin riesgo»), ordenada por riesgo. La ficha del visor muestra esa fila con la marca «(fondo)». Un activo sensible responde 404, igual que uno inexistente.

### 6.4 Visor en modo basal

- Selector entre el mapa base operativo y la ortofoto del PNOA. Sobre la ortofoto van los mismos rótulos y carreteras del mapa base, no la capa de nombres del IGN para ortofoto, que pinta los embalses a máximo nivel en azul y duplicaría los nombres.
- Pestaña en el borde derecho del mapa para **plegar el panel lateral** y ver el mapa a todo el ancho; el navegador recuerda la elección.
- **Mapa base operativo**, dibujado desde el mapa base vectorial del IGN para localizar a simple vista el escenario de operaciones sin competir con las capas de peligrosidad. No usa tonos cálidos, reservados para los riesgos. Tiene dos niveles:
  - Terreno, por debajo de las capas: relieve sombreado del modelo digital del terreno del IGN, bosque en verde apagado, núcleos urbanos en gris, ríos principales (los menores, desde el zoom 13) y embalses en azul. Los núcleos salen de dos capas de CartoCiudad que trae el IGN: los núcleos urbanos (desde el zoom 10) y las manzanas (desde el 12), porque a la de núcleos le faltan poblaciones enteras o su casco principal (Parla, Robregordo y Valverde de Alcalá no tienen ningún polígono; el centro de Majadahonda, tampoco) que sí tienen manzanas: 160 km² de manzanas quedan fuera de los núcleos. Desde el zoom 12 se pintan las dos capas del IGN; por debajo, un fichero propio que la cadena extrae de las 195 teselas de zoom 12 que tocan la Comunidad, con un lector mínimo del formato de teselas vectoriales escrito para el proyecto: las manzanas se engordan 30 m para cerrar las calles, se unen con los núcleos, se simplifican a 30 m y se descartan las manchas de menos de 0,02 km² (806 manchas, 1.584 km²; los núcleos de zoom 10, por su generalización, suman 1.928 km²).
  - Referencias, por encima de las capas y por debajo de los activos: carreteras por categoría en grises más oscuros y anchos cuanto más importantes, sin borde (autonómicas de segundo y tercer nivel desde los zooms 10 y 11); ferrocarril troncal en negro con discontinuo blanco, sin playas de vías; nombres de capitales, municipios, núcleos, embalses y números de carretera, con halo blanco.
- Sección desplegable **Elementos del mapa** arriba del panel derecho, en los tres modos, con tres casillas: **Nombres**, **Trenes** y **Tráfico** (apartado 6.5). La de nombres muestra u oculta de golpe todos los rótulos del mapa, también sobre la ortofoto. Las secciones **Capas de peligrosidad** y **Activos** también son comunes a los tres modos: las capas y el filtro de activos siguen aplicándose en la prealerta y en la crisis. **Al arrancar, todo desmarcado**: sin nombres, trenes, tráfico, capas de peligrosidad ni activos; el usuario enciende lo que quiere. Así tampoco pasan a la gestión de crisis capas que taparían el incendio.
- **Ficha en una ventana sobre el mapa**: la ficha de la celda de 1 km y la de un activo salen arriba a la izquierda del mapa, con su botón Cerrar (que quita también la celda marcada); el panel derecho queda solo con los selectores. El texto de ayuda («Haz clic en el mapa…») está en la ventana «Datos del visor».
- **Buscador de municipios**: caja arriba en el centro del mapa, en los tres modos. Busca sin tildes ni mayúsculas, primero los nombres que empiezan por lo escrito, y se maneja con el teclado. Al elegir un municipio, el mapa encuadra su término; en el análisis basal se abre además la celda de 1 km de su capital. En la crisis y la prealerta solo encuadra.
- **Ventana «Datos del visor» al arrancar**: centrada sobre el mapa, con los activos por familia y subtipo, las capas de peligrosidad (13: 5 naturales y 8 tecnológicas), la población de las celdas de 1 km que cubren la Comunidad (Censo 2021; la da `/api/resumen`) y los trenes, el tráfico y las incidencias de la DGT en tiempo real, con su fuente, su hora y la leyenda de sus símbolos; se piden al arrancar aunque sus casillas estén desmarcadas (en la copia sin conexión, un aviso de que no hay tiempo real). Se cierra con su botón y no vuelve a abrirse.
- Casilla general **Todos** dentro de la sección de activos: marcada si están todos los subtipos, a medias si hay algunos; al pulsarla los enciende o apaga todos.
- Panel de capas de peligrosidad con casillas por grupo (naturales, tecnológicos) y por capa. La casilla del grupo muestra la capa combinada con el nivel máximo del grupo (apartado 5.3) y apaga las capas sueltas del grupo; marcar una suelta apaga la combinada. La leyenda de niveles cambia de rótulo con la combinada y avisa cuando hay varias capas sueltas a la vez de que en cada punto se ve la dibujada encima.
- Panel de activos con casillas por familia y subtipo. Color por familia en tonos fríos (azul educativos, verde sanitarios, morado atención social) y forma por subtipo (círculo, cuadrado, triángulo); los colores cálidos se reservan para los riesgos.
- Agrupación de activos cercanos hasta el zoom 12, con el recuento en cada grupo; al pulsar un grupo el mapa se acerca hasta separarlo.
- Clic en el mapa: se dibuja el contorno de la celda y la ficha muestra población, riesgos (con nivel y porcentaje) y activos de la celda, además del recuento de sensibles.
- Clic en un activo: ficha común con sus riesgos por capa.

### 6.5 Trenes y tráfico en tiempo real

Capas opcionales en los tres modos, apagadas al empezar, con las casillas **Trenes** y **Tráfico** de la sección «Elementos del mapa». Mientras están encendidas se refrescan solas. La fuente, el número de elementos, la hora de los datos y la leyenda de símbolos van en la ventana «Datos del visor» del arranque (apartado 6.4). El servidor (`procesamiento/tiempo_real.py`) descarga cada fuente bajo demanda, guarda la última copia en la caché, anota cada descarga en el registro local y mantiene el resultado en memoria (30 s los trenes, 5 min el tráfico). Si una fuente no responde, las demás se muestran igual.

- **Trenes de viajeros** (`GET /api/trenes`): posiciones de Renfe (GTFS-Realtime), filtradas al límite de la Comunidad. Círculo gris oscuro con borde blanco y la línea (C5, C8b…) al acercarse; al pulsarlo, estado (en marcha, parado o llegando a estación), parada y hora de la posición. Sin dirección ni plazas: no se estima cuántas personas llevan. El feed de posiciones de Renfe solo trae, en el entorno de Madrid, trenes de Cercanías.
- **Tráfico de la ciudad** (`GET /api/trafico`): nivel de servicio de unos 3.200 puntos de medida válidos del Ayuntamiento de Madrid (se descartan los marcados con error o sin nivel), con el semáforo clásico: verde fluido, amarillo lento, rojo retenciones y granate congestión. Lo fluido solo aparece a partir del zoom 11. Al pulsar un punto: descripción, nivel, intensidad, ocupación y velocidad si la hay. Solo cubre el municipio de Madrid.
- **Incidencias de la DGT** (`GET /api/trafico`): registros DATEX II dentro de la Comunidad, con su tipo en español (obras, vehículo detenido, accidente, tráfico lento, carril o calzada cortados…), carretera, punto kilométrico, sentido, municipio y hora de inicio. Los cortes de carretera o de calzada completa llevan la señal de prohibido; el resto, la de peligro. Cuando el registro es un tramo, la señal se sitúa en su inicio.

## 7. Gestión de crisis por incendio forestal

### 7.1 Alerta

La crisis empieza siempre con una alerta en un punto, que se codifica con tipo, ubicación y hora:

- **Manual:** clic en el mapa en modo crisis. El panel muestra el punto, un campo de hora de ignición (por defecto, la actual) y la elección del viento.
- **Automática:** botón de focos de satélite. `GET /api/focos` descarga los CSV casi en tiempo real de Europa de NASA FIRMS para los tres satélites VIIRS, filtra las detecciones de las últimas 24 horas dentro del límite de la Comunidad y devuelve, para cada foco, posición, hora, satélite, confianza, potencia radiativa, día o noche, y si es una posible **fuente fija**: un foco con detecciones a menos de 500 m en 3 o más días de la última semana (industria, vertedero). Los focos se pintan en el mapa y se listan en el panel; al elegir uno, se convierte en la alerta.

### 7.2 Entradas del modelo

- **Ventana de cálculo:** rejilla de 50 m en EPSG:25830, de 1.000 × 1.000 celdas (50 × 50 km), centrada en la ignición y alineada a múltiplos de 50 m. La respuesta da el minuto en que el fuego toca su borde (`borde_min`) y el visor lo avisa.
- **Combustible:** dentro de la Comunidad, su mapa de modelos de combustibles, rasterizado a 25 m por la cadena (`procesamiento/incendio/combustible_cm.py`: 87 páginas de 5.000 polígonos del servicio WFS del IDEM, comprimidas y registradas) y llevado a la ventana por el modelo más frecuente; fuera, el mapa de EFFIS (250 m, EPSG:3035) por vecino más próximo. Modelos NFFL 1 a 13; 0 significa sin combustible. La respuesta indica de qué mapa sale el combustible de la ignición. Si la ignición cae en una celda sin combustible, la simulación se rechaza con un mensaje claro.
- **Relieve:** el MDT de 25 m del IGN se pide por WCS para la ventana con un margen, se guarda en la caché con su registro y se promedia a la rejilla de 50 m. De él salen la pendiente (tangente) y la dirección de máxima subida por celda, y la altitud de la ignición.
- **Viento:** un valor por hora durante 25 horas.
  - **AEMET:** la primera hora usa la última observación de la estación convencional más cercana a la ignición con dato de viento; las siguientes, la predicción horaria del municipio de la ignición (8 rumbos y velocidad). Si falta alguna hora se mantiene la anterior. La respuesta indica estación, distancia, hora de la observación y cuántas horas son previstas o repetidas. La clave se lee de un fichero `.env` local. Las respuestas se guardan en la caché con su registro. Si AEMET no responde en dos intentos de 20 segundos, el error indica que se introduzca el viento a mano.
  - **Manual:** velocidad (0 a 150 km/h) y rumbo de procedencia, constantes durante las 24 horas.
- **Humedad del combustible:** valor fijo de verano seco: 6, 7 y 8 % en los combustibles muertos de 1, 10 y 100 horas, y 90 % en los vivos.
- **Municipios:** el shapefile de 2020 da el municipio de la ignición (código INE de 5 cifras) y se rasteriza en la ventana para los municipios alcanzados.

### 7.3 Modelo de propagación

**Velocidad.** Modelo de Rothermel (1972) con las correcciones de Albini (1976), en implementación propia a partir de las publicaciones, con los 13 modelos de combustible NFFL de Anderson (1982). Del viento a 10 m de AEMET se pasa al viento a 6,1 m de Rothermel (factor 1/1,15) y de ahí al viento a media llama con un factor por modelo (Albini y Baughman, 1979). Viento y pendiente se suman como vectores. El frente es una elipse con la ignición en el foco y relación longitud/anchura de Anderson (1983), limitada a 8. De cada celda salen la velocidad máxima (m/min), su dirección y la excentricidad, y de ellas la velocidad en cualquier dirección.

**Validación:** con humedad del 8 % en muertos, 100 % en vivos, viento a media llama de 5 millas por hora y terreno llano, 11 de los 13 modelos quedan a menos del 10 % de las velocidades nominales de la tabla de Anderson (1982). El modelo 5 se desvía un −20 % y el 7 un +30 %; ambos tienen combustible vivo y ocupan el 2,2 % y el 0,3 % de la Comunidad. Los dominantes (2, 4 y 10) quedan por debajo del 7 %. Estas comprobaciones forman parte de las pruebas automáticas.

**Ruta.** Tiempo mínimo de recorrido (Finney, 2002): el tiempo de llegada a cada celda es el del camino más rápido desde la ignición sobre un grafo dirigido de 32 vecinos (desplazamientos de hasta tres celdas), con el peso de cada arista igual a la distancia por la media de las lentitudes (inversa de la velocidad en esa dirección) de las dos celdas. Las celdas sin combustible no tienen aristas, y una arista que cruza alguna no existe: actúan como barrera.

**Viento por horas.** El cálculo se hace por tramos de condiciones constantes (un solo tramo con viento a mano): para cada tramo se construye el grafo con su viento y su humedad, solo en el recuadro que el fuego puede alcanzar en él, y se resuelve el camino mínimo con `scipy.sparse.csgraph.dijkstra` desde un nodo virtual unido a cada celda ya quemada con el peso del comienzo del tramo, limitado a su final. Cada arista que el fuego ha empezado a recorrer conserva la fracción recorrida, así que las condiciones nuevas solo actúan hacia delante. Horizonte de 24 horas. Unos 3 segundos con viento constante y unos 10 con viento horario.

**Salida del motor:** el mapa completo de tiempos de llegada, en minutos desde la ignición, guardado como GeoTIFF de 32 bits (`datos/procesados/crisis/<id>/llegada.tif`) junto con la respuesta completa en JSON. El identificador de la simulación combina hora de ignición, coordenadas y, si es manual, el viento.

### 7.4 Consecuencias

- **Activos alcanzados.** Un activo se considera alcanzado cuando el fuego llega a menos de 250 m de su ubicación (filtro de mínimo sobre el mapa de llegada en un radio de 250 m, leído en el píxel del activo). Se devuelve la lista con el minuto de llegada, separando los no sensibles (con identificador, nombre, familia, subtipo, municipio) del recuento de sensibles y sus plazas. Casi todos los centros están en suelo urbano sin combustible: la amenaza les llega desde el borde.
- **Instalaciones Seveso.** No hay fuente abierta con su posición; se deducen del propio catálogo. Según la memoria, las zonas de las capas 6_3, 6_4 y 6_5 son círculos concéntricos trazados con los radios de intervención (nivel 2) y alerta (nivel 1) alrededor de cada instalación. Se toma como instalación el centro de cada zona de intervención y se fusionan los centros de distintas capas a menos de 300 m: **44 instalaciones** a partir de 88 zonas (21 de nube tóxica, 30 de sobrepresión, 37 de radiación térmica), con sus radios. La lista (`datos/procesados/instalaciones_seveso.csv`) se regenera en local y no se publica. Cuando el fuego llega a menos de 250 m del centro, la instalación se marca con su minuto de activación y sus amenazas, y se activan sus zonas de intervención y alerta como **amenaza derivada**, con los activos que contienen (zona, origen y amenaza). Cada amenaza tiene sus propios radios (`zonas` en la respuesta, de mayor a menor alcance): en SEV-04, por ejemplo, la nube tóxica llega a 4,7 km y la sobrepresión por explosión a 51 m. `radio_intervencion_m` y `radio_alerta_m` son los mayores de la instalación.
- **Conducciones de hidrocarburos.** La capa 6_12 es una franja trazada alrededor de gasoductos y oleoductos. Se toma su núcleo (nivel 3) como trazado. Cuando el fuego entra en él, se activa la franja (nivel 2 o más) en 750 m alrededor del tramo alcanzado (la mayor distancia de efectos de la memoria: incendio de un charco de gasolinas, 738 m), con el primer minuto de llegada, el número de celdas de núcleo alcanzadas, el punto y los activos dentro de la franja activada.
- **Municipios alcanzados.** Para cada municipio de la ventana, el primer minuto en que el fuego entra en él y el punto por el que entra.
- **Carreteras y vías de tren afectadas** (`procesamiento/incendio/vias.py`). La red de la BTA 2017 de la Comunidad se descarga del servicio WFS en páginas de 5.000 tramos (`procesamiento/red_transporte.py`, paso 1 de la cadena) y se corta en trozos de unos 200 m con puntos cada 25 m: 199.877 trozos, de ellos los de 101.646 tramos de carretera, 20.021 de pista y 7.507 de ferrocarril, metro y tranvía. Para cada trozo de la ventana, el minuto en que el fuego llega a menos de 250 m de alguno de sus puntos y el primer minuto en que alguno queda bajo el humo (en pasos de 5 minutos, apartado 7.5). La respuesta lleva los trozos afectados con su geometría simplificada a 5 m (`vias.tramos`) y un resumen por carretera, o por tipo para las vías de tren (`vias.resumen`), con las horas y los kilómetros alcanzados por el fuego. Las pistas forestales se descargan con la red pero no se cruzan con el incendio: en el mapa despistan más que ayudan.
- **Trenes de Cercanías programados**. El horario de Renfe (`procesamiento/cercanias.py`, paso 1 de la cadena; se renueva si la copia tiene más de 7 días) da 95 estaciones del núcleo de Madrid y unos 550.000 pasos de tren en 30 días. Para cada estación afectada, los trenes que pasan por ella cuando ya lo está, agrupados por línea y estación (`trenes_programados`): primero, destino, número de trenes y cuántos con el fuego a menos de 250 m. Si la fecha simulada queda fuera del horario, se usan los trenes del mismo día de la semana dentro de él (`dia_equivalente`) y el visor lo dice.
- **Superficie quemada** a 1, 3, 6, 12 y 24 horas, en km².

### 7.5 Humo

Modelo geométrico, no de dispersión (`procesamiento/incendio/humo.py`). Cada 5 minutos el humo sale del área quemada hasta ese momento y se desplaza viento abajo con el viento de esa hora, abriéndose en un cono de semiángulo 20°. El alcance es la velocidad del viento por el tiempo transcurrido, hasta 2 horas de permanencia y con un máximo de 25 km; sin viento, un radio de 500 m. La zona es la envolvente convexa del área quemada y de esa misma área desplazada y ensanchada. Es una sola geometría: la calcula el servidor (`humo.zonas`, con su minuto), el visor dibuja en cada minuto la del último paso, y cada centro, carretera, vía o estación queda bajo el humo desde el primer paso en que su punto cae dentro. Los parámetros son provisionales.

### 7.6 Comunicaciones ficticias

Para el instante mostrado, el visor genera:

- **Mensaje para redes sociales:** texto con el municipio y la hora de la ignición, la situación estimada a la hora mostrada (superficie afectada y municipios en los que ha entrado el fuego), la dirección del humo, el número de centros con población vulnerable alcanzados y los nombres de los tres primeros, una recomendación de evitar la zona y las coordenadas de la ignición.
- **Falso ES-Alert:** el aviso a los móviles por celda que solo puede emitir la autoridad. Indica los municipios que pueden verse afectados en la próxima hora, instrucciones de autoprotección (alejarse del fuego por las vías indicadas; con humo, cerrar puertas y ventanas y permanecer dentro; no acercarse; teléfono 112), el área del aviso (los municipios en los que el fuego ha entrado o entra en la hora siguiente) y la hora de emisión. **Se ve sobre el mapa**, en la esquina superior izquierda, con aspecto de aviso en un móvil: se emite al declarar la alerta y cada vez que crece el área (un municipio entra en la hora siguiente del fuego), y cada emisión se resalta en rojo durante 20 minutos simulados. El panel conserva el texto completo.

Se muestran en pantalla tal como saldrían. No se publica nada en ninguna red ni se envía ningún aviso.

### 7.7 API de crisis

| Ruta | Función |
|---|---|
| `POST /api/incendio` | Cuerpo JSON con `lon`, `lat`, `hora` (opcional, ISO local; por defecto la actual) y `viento` (opcional: `velocidad_kmh`, `desde`; sin él se usa AEMET). Devuelve la respuesta completa de la simulación: identificador, ignición (coordenadas, hora, municipio, código INE, modelo de combustible y nombre, altitud), ventana (esquinas en lon/lat, filas, columnas, tamaño de celda), horizonte, cortes, origen del viento y vientos por hora, humedades, distancia de alcanzado, superficies, municipios, activos y sensibles alcanzados, cascada (instalaciones, conducción, activos, sensibles), humo (activos, sensibles, parámetros) y la URL del mapa de llegada. Los activos alcanzados de vulnerabilidad alta y muy alta llevan además la ruta del fuego hasta ellos (`ruta`), y cada municipio el punto por el que entra el fuego (`lon`, `lat`) |
| `GET /api/incendio/llegada?id=` | Mapa de llegada de la simulación como enteros de 16 bits sin signo, uno por celda y por filas, con los minutos redondeados hacia arriba y 65535 para "no llega". El identificador se valida contra un patrón antes de tocar el disco |
| `GET /api/focos` | Focos de calor de las últimas 24 horas (apartado 7.1) |
| `GET /api/incendio/movilidad?id=` | Trenes, incidencias de la DGT y puntos de tráfico de la ciudad actuales que el fuego o el humo de la simulación alcanzarían (apartado 7.8), con el total consultado de cada fuente y, si una no responde, su error |

Errores: 400 si la alerta es incorrecta o la ignición no tiene combustible o está fuera de la Comunidad; 503 si AEMET, el IGN o FIRMS no responden, con un mensaje que indica el respaldo.

La simulación también se lanza desde la línea de comandos:

```
python -m procesamiento.incendio.simulacion --lon -4.02 --lat 40.71 [--hora 2026-07-15T15:00] [--viento 20,270]
```

### 7.8 Visor en modo crisis

- Al cambiar de modo se borra la celda del modo basal y se muestran solo las capas del modo elegido; al salir de la crisis se detiene la reproducción, y al volver se recupera la última simulación.
- Panel de alerta: ayuda, botón de focos de satélite con lista, y al situar la alerta: punto, hora de ignición, elección de viento (AEMET o a mano con velocidad y rumbo) y botón de simular. Mientras calcula, el estado lo indica; los errores de la API se muestran en el panel.
- Al recibir la simulación, el visor descarga el mapa de llegada y lo guarda en memoria; encuadra la ventana de cálculo.
- **Reproductor** sobre el mapa: volver al inicio, reproducir y pausar, velocidad de 1, 5, 15 o 60 minutos simulados por segundo, reloj con la hora simulada, botones de salto a 1, 3, 6, 12 y 24 h, y barra de tiempo arrastrable de 0 a 1.440 minutos con marcas en los cortes.
- En cada minuto se pintan sobre un lienzo: el área quemada (llegada ≤ t) en granate y el frente activo (quemado en los últimos 20 minutos) en naranja. El lienzo se sitúa con las esquinas de la ventana y cada celda se pinta en su posición sin recalcular nada en el servidor. El mapa interpola el lienzo al ampliarlo (remuestreo lineal): el cálculo es en celdas de 50 m, pero los bordes no se ven como cuadrados.
- Humo: la zona que calcula el servidor para el último paso de 5 minutos anterior al minuto mostrado (apartado 7.5).
- **Avisos en globo para todo lo que alcanzará el fuego**: el globo de los centros (nombre, símbolo y «Llega en 1 h 19 min · hacia las 00:57», rojo al llegar y apagado a los 30 minutos) se usa también para las carreteras y vías de tren (en el punto por el que llega el fuego), los núcleos de población, las instalaciones Seveso y la conducción, desde 3 horas antes; se ven a la vez los cinco más próximos de cualquier tipo. Las instalaciones Seveso y la conducción tienen siempre su globo, fuera de ese cupo: en zonas densas, lo más próximo lo llenaría y se quedarían sin aviso hasta que el fuego las alcanzara. Los destinos de la cascada llevan, además del globo, un círculo. Los núcleos de población salen del Nomenclátor Geográfico Básico del IGN (`procesamiento/poblaciones.py`, paso 5 de la cadena: 610 núcleos, descargados por recuadros) y su casco, de las manchas urbanas del mapa base; la simulación devuelve `poblaciones` con el minuto y el punto de llegada, y `vias.resumen` añade el punto por el que llega el fuego a cada carretera (`lon_llamas`, `lat_llamas`). Las poblaciones entran también en la cronología, en el tipo «Municipios y poblaciones».
- **Cada cosa afectada aparece en la animación**, en el minuto en que le llega el fuego, la zona Seveso o de la conducción, o el humo: los centros, con su propio símbolo (forma y color de su familia), sin anillo; las estaciones de Cercanías, los trenes, las incidencias de la DGT y los puntos de tráfico, con un punto del color del efecto; las carreteras bajo el humo, con su código (las que alcanza el fuego van en el anuncio); y la entrada del fuego en cada municipio, con el texto «El fuego entra en…». El nombre se queda hasta el final de la simulación, en rojo (fuego), marrón (zona Seveso o de la conducción) o gris (humo); el símbolo también se queda. Si dos nombres se pisan, se oculta el de menor prioridad: poblaciones, instalaciones Seveso y conducción primero; después, fuego antes que zona y humo, y a igualdad, mayor vulnerabilidad. Al acercarse, los ocultos reaparecen. Así la animación se entiende sin mirar la cronología. Al pulsar un centro, el mapa se acerca. Instalaciones Seveso: etiqueta con su identificador y zonas de intervención (naranja) y alerta (amarillo) con borde discontinuo, visibles desde el minuto de activación. El mapa dibuja las zonas de la amenaza de mayor alcance; la cartela, la cronología, el esquema de la cadena y el panel dan el radio de cada amenaza («SEV-04 · nube tóxica 4,7 km, radiación 112 m, explosión 51 m»), y cada centro de las zonas dice por qué amenaza está en ellas («zona de alerta por nube tóxica»). Focos de satélite en rojo, o en gris si son posible fuente fija.
- Panel de resultado: hora y municipio de la ignición, combustible, altitud, origen del viento (estación y distancia, municipio de la predicción, horas sin predicción) o viento manual, leyenda; superficie quemada por corte; municipios en los que entra el fuego; activos alcanzados por las llamas; efecto cascada (instalaciones Seveso con hora, amenazas y radios; conducción con hora de llegada; activos bajo amenaza derivada con origen y zona); activos bajo el humo. Cada elemento lleva su hora y el tiempo desde la ignición, y cada activo su símbolo, municipio y vulnerabilidad; al pulsarlo, el mapa vuela hasta él. Los centros sensibles de cada lista aparecen como una frase con el recuento de centros y plazas.
- Comunicaciones ficticias regeneradas para el instante mostrado (apartado 7.6).
- **Avisos anticipados**: para los centros de vulnerabilidad alta y muy alta alcanzados por las llamas, la respuesta incluye la ruta del fuego hasta cada uno (`ruta`: puntos con longitud, latitud y minuto de llegada, de la ignición al centro; `consecuencias.ruta_del_fuego`). Desde 3 horas antes de la llegada, el visor muestra sobre el centro un globo con su nombre y la cuenta atrás, y una flecha discontinua roja con el tramo de la ruta que queda entre el frente y el punto en que el fuego queda a menos de 250 m, y de ahí al propio centro. Al llegar, el globo se pone rojo con la hora y se apaga 30 minutos simulados después. Como mucho hay tres globos a la vez, los de llegada más próxima. Pulsar un globo acerca el mapa al centro. Método en el apartado 3.5 de la metodología.
- **Cartelas de aviso**: el globo de aviso se convierte en una cartela apartada de su objetivo y unida a él por un conector. Va siempre a los espacios vacíos del mapa: nunca sobre el fuego (lo quemado, el frente y lo que arderá en la media hora siguiente), el humo que se ve, las zonas Seveso activadas, la franja de la conducción ni los símbolos de lo alcanzado; tampoco sobre otras cartelas, los objetivos, los conectores, el buscador ni los paneles del mapa, y su conector no cruza otro. Busca por toda la pantalla el hueco vacío más cercano a su objetivo, preferiblemente en la dirección que va del centro del fuego al objetivo, para que los conectores salgan hacia fuera y no se crucen. La pantalla se divide en celdas de 9 px marcadas como llenas o vacías; las cartelas se colocan de una en una, en varios órdenes (primero las que menos huecos tienen), se queda la mejor colocación y se repasa cada cartela con las demás ya puestas. Una cartela se mantiene donde está mientras siga en vacío y no esté a más de 150 px de su hueco vacío más cercano, y se recoloca al mover el mapa. Cuando el incendio ocupa casi toda la pantalla, las cartelas quedan en los bordes con conectores largos. La franja superior lleva el color del tipo (azul educativos, verde sanitarios, morado sociales, gris poblaciones, negro carreteras y vías, naranja Seveso y conducción) con el tipo escrito; el cuerpo, la urgencia: blanco con borde gris azulado a más de 1 h, naranja a menos de 1 h y rojo al ser alcanzado.
- **Literales «tipo · nombre»**: en cartelas, nombres del mapa, cronología, listas y fichas, el tipo corto va delante del nombre («Colegio de primaria · …», «Residencia de mayores · …», «Carretera · A-6», «Núcleo (IGN) · Majadahonda» (no «Población»: el Nomenclátor del IGN llama núcleo de población también a polígonos, bases, campings o instalaciones como «Iberdrola»), «Instalación Seveso · …», «Estación de Cercanías · …», «Tren de Cercanías · C7»). Los tipos educativos salen del código de tipo de centro; los sociales, del subtipo y el colectivo del registro; los hospitales llevan su tipo oficial. La casilla «Nombres» apaga todos los nombres del mapa, también los de lo afectado en la crisis, la conducción y las líneas de los trenes.
- **La animación arranca solo con la ignición**: en las 3 primeras horas, cartelas, isocronas, flecha de aproximación de la cascada y sus destinos miran tan lejos como tiempo lleva el incendio (en el minuto 10, lo que llega antes del minuto 20); a partir de la tercera hora, la antelación normal de 3 horas. Así la animación empieza con la ignición sola y los avisos aparecen uno a uno. Con viento, en el minuto 0 no se dibuja humo.
- **Personas**: la respuesta incluye `poblacion_celdas`, la población del Censo 2021 (con menores de 16 y mayores de 64) de cada celda de 1 km a la que llega el fuego, con el primer minuto de llegada (`consecuencias.poblacion_por_celda`), y los activos llevan sus plazas. El reloj de la animación suma los habitantes de las celdas que ha tocado el fuego hasta ese minuto y las plazas de los centros sociales alcanzados; el panel da las mismas cifras en los cortes de 1, 3, 6, 12 y 24 h. Es una cota alta: cuenta la celda entera aunque arda solo una parte (apartado 3.8 de la metodología).
- **Isocronas**: por delante del frente, líneas discontinuas con halo blanco que marcan hasta dónde habrá llegado el fuego a cada hora en punto de las 3 siguientes, con la hora del reloj; la próxima, más marcada, y las siguientes, más tenues. Se calculan en el servidor (`consecuencias.isocronas`): para cada hora en punto de las 24 simuladas, el contorno del área con llegada hasta entonces, simplificado a 50 m, sin manchas de menos de 1 ha ni huecos sin quemar de menos de 5 ha (`isocronas` en la respuesta).
- **Cascada animada**: en la hora previa a que el fuego alcance una instalación Seveso o una conducción, una flecha naranja recorre la ruta del fuego desde el frente hasta ella (la respuesta incluye esa ruta, `ruta`, como la de los avisos anticipados). Al alcanzarla, tres anillos de pulso salen de la instalación y sus zonas de intervención y alerta, o la franja de la conducción, crecen desde ella hasta su tamaño en 2 segundos reales, sea cual sea la velocidad de reproducción; si se salta más de hora y media en la barra, aparecen ya completas. Durante 30 minutos simulados, flechas naranjas discontinuas van de la instalación a los centros de vulnerabilidad alta y muy alta que quedan en sus zonas. La franja de la conducción se dibuja en el mapa y crece hora a hora con el tramo alcanzado (`cascada.conduccion.franja`: 750 m alrededor de las celdas del núcleo alcanzadas hasta cada hora). `cascada.conduccion.tramos` trae, además de la primera llegada, cada tramo nuevo que alcanza el fuego (a más de 1,5 km de lo ya alcanzado; `consecuencias.tramos_alcanzados`), con su punto en el eje, su hora y su ruta del fuego; cada uno tiene cartela («otro tramo»), línea en la cronología, pausa en los sucesos clave, flecha de aproximación y pulso. Las flechas a los centros de la franja salen del tramo ya alcanzado más cercano. En el panel, un **esquema de la cadena** por instalación o conducción: fuego con su hora, instalación y amenazas, zonas y centros afectados por vulnerabilidad; cada cadena se ilumina en el minuto en que se activa. **Destinos de la cascada**: cada instalación Seveso y el punto de la conducción que el fuego alcanzará se marcan en el mapa con un círculo naranja y una etiqueta («Conducción de hidrocarburos · fuego hacia las 12:16», que pasa a «alcanzada a las…»). Aparecen con su flecha de aproximación (ver «La animación arranca solo con la ignición»), de modo que la flecha siempre apunta a algo visible.
- **Conducciones de hidrocarburos en el mapa**: se pinta siempre, en los tres modos y en toda la Comunidad, solo la línea de cada conducción, en amarillo y con su nombre desde el zoom 12. Como la Comunidad publica los tramos de la BTA sin geometría, la línea es el eje del núcleo de la capa 6_12 (nivel 3), calculado una vez en la cadena de datos (`procesamiento/conducciones.py`: núcleo a 25 m, adelgazamiento de Zhang y Suen, vectorización, poda de ramitas de menos de 300 m y simplificación a 25 m; unos 1.100 km). El punto en que el fuego alcanza la conducción se coloca sobre esa línea. No se dibuja la banda del catálogo, que llenaría el mapa de franjas superpuestas.
- **Carreteras y vías afectadas**: los trozos de carretera se pintan en gris cuando les llega el humo y en rojo cuando el fuego llega a menos de 250 m, con borde blanco; las vías de tren, con línea discontinua. El panel añade la lista de carreteras y vías afectadas, con la hora de cada efecto y los kilómetros alcanzados por el fuego, y la de trenes de Cercanías programados que pasan por estaciones afectadas. Los dos entran en la cronología como tipo «Carreteras y trenes de Cercanías», marcado por defecto; el humo sobre varias vías a la misma hora va en un solo suceso.
- **Cronología de sucesos**: la simulación se cuenta como una sucesión de hechos con su hora. Son la ignición, la entrada en cada municipio (por el punto en que entra el fuego), los centros alcanzados (uno a uno los de vulnerabilidad alta y muy alta, los demás agrupados por hora), las instalaciones Seveso y conducciones alcanzadas con los centros que quedan en sus zonas y, opcionalmente, los trenes, el tráfico y los centros bajo el humo. Los últimos cinco sucesos se ven en un recuadro sobre el mapa titulado «Últimos sucesos», en orden de arriba abajo, con el más reciente al final y resaltado al aparecer; la lista completa, en el panel de resultado, con casillas para elegir qué tipos se muestran (por defecto municipios, centros, y Seveso y conducciones). Cada suceso tiene una marca en la barra de tiempo, y pulsar la marca o el suceso lleva a ese minuto y a su lugar. La reproducción **se detiene sola en los sucesos clave**: instalaciones Seveso y conducciones alcanzadas y centros de vulnerabilidad muy alta. Un selector del reproductor elige la cámara: fija (por defecto) o que sigue los sucesos clave.
- **Trenes y tráfico ahora en la zona afectada:** al cargar una simulación, el visor pide el cruce de la situación actual con la evolución simulada (`procesamiento/incendio/movilidad.py`). Para cada tren, incidencia de la DGT y punto de tráfico de la ciudad calcula el minuto en que el fuego llega a menos de 250 m (la misma distancia que para los activos) y el primer minuto en que queda bajo el humo (en pasos de 5 minutos); en las incidencias que ocupan un tramo cuenta el primero de sus dos extremos. Los alcanzados se listan con su hora y efecto, siguen al reproductor como el resto de listas y se marcan en el mapa con el mismo anillo que los activos (rojo llamas, gris humo). Es una foto del momento de la consulta, no una proyección del recorrido de los trenes.

### 7.9 Ejecuciones de referencia

Tres simulaciones guardadas en el demostrador, calculadas con el mapa de combustibles de la Comunidad, sin el límite de viento de Rothermel y con el combustible vivo al 60 % de julio a septiembre (que solo afecta a la de Collado Mediano, de julio). Cada una tiene su hora y su viento (la de Manzanares el Real, el que dio AEMET para esa ignición, hora a hora). En Collado Mediano y en Manzanares el Real el mapa de la Comunidad no da combustible en el punto elegido, y la ignición se sitúa en la celda con combustible más cercana, a 62 y 75 m.

| Ignición | Viento | Superficie a 24 h | Activos alcanzados | Municipios | Seveso activadas |
|---|---|---|---|---|---|
| Collado Mediano, 15-07-2026 15:00 | Manual, 20 km/h del O | 43,2 km² (20,6 con EFFIS) | 17 (8) | 6 (6) | 1, a las 5 h 2 min (a las 2 h 28 min) |
| Cercedilla, 19:10 | Manual, 20 km/h del O | 30,5 km² (36,5 con EFFIS) | 12 (8) | 8 (7) | 1, a las 6 h 54 min |
| Manzanares el Real, 23:21 | AEMET: observación de Navacerrada Puerto (10,1 km) y 24 horas de predicción del municipio | 8,1 km² (12,7 con EFFIS) | 0 (0) | 2 (2) | 0 (0) |

Entre paréntesis, los valores con el mapa europeo de EFFIS.

La tercera verifica el camino completo de AEMET (observación más predicción horaria).

### 7.10 Validación con un caso real

El incendio de Tres Cantos del 11 de agosto de 2025 se simula con el viento medio horario medido en la estación de Colmenar Viejo de la Red de Calidad del Aire y se compara con su perímetro final de Copernicus EFFIS (2.037 ha), con los focos de satélite de NASA FIRMS y con lo publicado por el Ayuntamiento de Colmenar Viejo: superficie, coincidencia espacial (índice de Sørensen), dirección del avance, avance en los primeros 40 minutos y focos dentro del área simulada. Lo calcula `procesamiento/incendio/validacion.py` (también el paso 8 de la cadena) y lo devuelve la API local (`/api/validacion`). La simulación se guarda como caso (`caso_tres_cantos_2025`), que la poda de simulaciones antiguas no borra. Para ello, el motor admite un viento manual distinto en cada hora, también desde la API (`vientos`). Método, métricas y lectura de los resultados, en el apartado 3.11 de la metodología. El punto de ignición no se ha publicado oficialmente: se usa uno estimado por el proyecto en los pastos del noreste de Nuevo Tres Cantos, junto a la Gran Vía. Con este caso se ajustaron los parámetros del modelo. Con el mapa de combustibles de la Comunidad y el viento medio, la mejor coincidencia con el perímetro es un índice de Sørensen de 0,65, a las 21 horas, con el 80 % del área quemada real (0,46 y 41 % con EFFIS); la carrera inicial empujada por la tormenta seca no se reproduce (0,2 km en 40 minutos frente a más de 6 km), porque el viento medio no recoge las rachas y el modelo no salta la franja sin combustible de la Gran Vía. Por eso el modelo usa además la racha en las horas de tormenta, la humedad del combustible de cada hora y el salto de franjas sin combustible de hasta 300 m con viento fuerte; y la validación pone la racha de AEMET con la dirección medida junto al incendio. Con todo ello y, además, sin el límite de viento de Rothermel y con el combustible vivo al 60 % en verano: 302 ha en la primera hora, 4,5 km en 40 minutos (6 km a los 76 minutos, frente a unos 40 en el incendio real) y, cortado a las 8 horas, cuando el real ya estaba perimetrado, 1.653 ha con avance hacia los 98°, frente a los 107° reales. La mejor coincidencia global es 0,62, porque sin extinción el fuego simulado desborda después de la noche. Detalle por pasos en el apartado 3.11 de la metodología.

Además, el modelo se comparó con siete incendios de la Comunidad entre 2022 y 2025 (`procesamiento/incendio/casos.py`), con hasta 15 simulaciones por caso que mueven la ignición 200 m y giran el viento 15°. La comparación se hace a una hora fijada de antemano (la de contención o, si no se conoce, 8 horas) y frente a un modelo nulo: un círculo de la misma superficie centrado en la ignición. En los seis casos de evaluación (Tres Cantos, con el que se ajustaron los parámetros, va aparte), la coincidencia mediana es 0,37 frente a 0,22 del círculo; el modelo supera al círculo en cuatro de los seis y sobrestima la superficie (mediana de 1,4 veces la real), porque no tiene extinción. Detalle en el apartado 3.12 de la metodología.

## 8. Prealerta a 7 días

Método, umbrales y limitaciones en `docs/metodologia.md`, apartado 4.

### 8.1 Territorio

La cadena de datos construye `datos/visor/municipios.geojson` (los 179 municipios, con los 21 distritos de la capital unidos, simplificados a 30 m), `datos/visor/zonas_aviso.geojson` (las tres zonas de aviso de AEMET y un punto en la parte mayor de cada una para el rótulo), `datos/procesados/municipios.csv` (código INE, nombre, zona de aviso de mayor solape, centroide y superficie: 75 municipios en la Sierra de Madrid, 44 en Metropolitana y Henares y 60 en Sur, Vegas y Oeste) y `datos/procesados/activos_municipio.csv` (municipio de cada activo por cruce espacial; los 5.632 activos ubicados caen dentro de algún municipio). Las 13 capas meteorológicas del catálogo y la de torrencialidad en cauces se muestrean en el punto de cada activo (`meteo_activos.csv`), leyendo cada bloque del GeoTIFF una sola vez, y las 13 meteorológicas se teselan hasta el zoom 11 con el nivel más frecuente.

### 8.2 Previsión y avisos

`procesamiento/prealerta/aemet.py` pide la previsión diaria de cada municipio, y la horaria cuando la diaria anuncia precipitación, tormenta o nieve, con la clave de `.env`; guarda cada respuesta en `datos/cache/prealerta/` con el día de referencia en el nombre (repetir el mismo día no vuelve a llamar a AEMET) y anota las descargas en el registro local. El resultado de una actualización queda en `prevision_<fecha>.json`; el servidor sirve la última disponible aunque sea de otro día, con su fecha de elaboración. Cada petición tiene dos intentos de 15 segundos; tres municipios seguidos sin respuesta interrumpen la actualización, que se reintenta más tarde.

`avisos.py` lee el RSS público de avisos de AEMET, descarga el paquete de ficheros CAP vigentes, conserva los avisos de nivel amarillo o superior de las tres zonas de Madrid (zona, fenómeno, nivel, umbral, probabilidad, vigencia y polígonos) y cae al canal de Meteoalarm si AEMET no responde; caché de media hora. En la comprobación con los avisos reales, el paquete traía 350 ficheros CAP de toda España y, para Madrid, dos avisos amarillos de lluvia para el día siguiente en la Sierra y en el Sur.

### 8.3 Cálculo

`calculo.py` traduce la previsión de cada municipio y día a niveles con los umbrales de su zona (`umbrales.py`), aplica los avisos oficiales de la zona y el día (mandan sobre el cálculo y se etiquetan como tales), calcula el índice de Fosberg, deduce los peligros basales activados y resume la Comunidad por día. Los activos afectados se calculan por día: efecto directo según el subtipo y activación cuando su peligrosidad en la capa activada es moderada o superior, con el riesgo basal de esa capa; los centros sensibles solo se cuentan. El cálculo completo tarda unas centésimas de segundo; la lista de activos de un día, medio segundo.

### 8.4 API y servicio

`servicio.py` mantiene la previsión en memoria (releída solo si cambia el fichero), lanza la actualización en segundo plano cuando la previsión guardada no es de hoy o le faltan municipios (como mucho una vez cada 15 minutos) y recalcula el resultado solo cuando cambian la previsión o los avisos. Rutas: `GET /api/prealerta` (resumen de los siete días y niveles de todos los municipios, unos 45 KB), `GET /api/prealerta/municipio?codigo=&dia=` (los siete días del municipio y sus activos del día), `GET /api/prealerta/activos?dia=` (índice 0 a 6 o fecha) y `POST /api/prealerta/actualizar`.

### 8.5 Visor en modo prealerta

Tercer modo del visor (`visor/prealerta.js`): estado de la previsión y de los avisos (fecha de elaboración, progreso de la actualización y botón para repetirla), selector de siete días con el nivel máximo de cada uno y el número de municipios en amarillo o más, municipios coloreados por su nivel (los de verde, sin color), zonas de aviso en trazo discontinuo con su rótulo y los activos con riesgo focal marcados con un anillo del color del nivel, más pequeño de lejos. El panel muestra el resumen del día (fenómenos con su origen, avisos oficiales y peligros activados), los activos agrupados por fenómeno y por peligro activado (con desglose por subtipo y lista limitada a 40 por grupo; todos quedan en el mapa) y, al pulsar un municipio, su detalle: sus siete días, la previsión del día, la tabla de fenómenos con nivel, dato y origen, y sus activos. Las 13 capas meteorológicas del catálogo se añaden al mapa la primera vez que se marcan.

### 8.6 Estado de la comprobación

La primera previsión real, el muestreo de las capas meteorológicas en los activos y sus teselas están pendientes de ejecutar la cadena y el servidor con AEMET OpenData y el geoportal IDEM disponibles. Lo que va por el canal público de AEMET está comprobado: las zonas de aviso están descargadas y registradas, y los avisos CAP reales se leyeron correctamente. El visor se comprobó con una previsión de muestra de Madrid repetida en los 179 municipios con variaciones (calor, viento y frío ficticios), que no se conserva.

## 9. Privacidad y seguridad

- No hay usuarios ni se recogen datos personales.
- Los datos personales de los conjuntos de centros (NIF de titulares, teléfonos, correos, webs) no se cargan en ninguna salida.
- Los 177 centros con algún dato reservado por la Comunidad (los únicos sensibles) no se ubican ni se geocodifican: no aparecen en el mapa ni en ninguna consulta, y solo se dan como total en esta memoria. El mecanismo de recuento sin puntos (consulta de celda, prealerta y crisis) se conserva en el código.
- Los ficheros con centros sensibles (`activos.csv`, `activos_basal.csv`), la lista de instalaciones Seveso deducida y las simulaciones no se suben al repositorio; se regeneran en local.
- La clave de AEMET está en un fichero `.env` excluido del repositorio; se publica una plantilla.
- El servidor escucha solo en la propia máquina, rechaza rutas que salgan de las carpetas servidas y valida el identificador de simulación antes de leer del disco.

## 10. Pruebas

151 pruebas con pytest, que se ejecutan sin red y en unos 10 segundos:

| Fichero | Qué comprueba |
|---|---|
| `test_cadena.py` | La matriz de riesgo (valores y monotonía); que las 13 capas tienen los códigos acordados; el identificador de celda como el INE y la celda de un punto de Madrid; el acumulador por celda y nivel; el coloreado de teselas (fondo y engrosado de lineales); el factor de reducción por zoom y las teselas que cubren Madrid |
| `test_servidor.py` | Servicio del visor y de ficheros con rangos (206, 416); que ninguna ruta sale de las carpetas; la API de celda (resultado, fuera de la Comunidad, parámetros) y de activo, sobre datos ficticios |
| `test_incendio.py` | Velocidad nominal de los 13 modelos frente a Anderson (1982); que el viento alarga y orienta la elipse; que la pendiente acelera cuesta arriba; que la humedad de extinción apaga; que sin viento el fuego es casi circular y con viento del oeste va al este; que las celdas sin combustible son barrera; que una ignición sin combustible avisa; el cambio de viento por hora; que el humo va viento abajo, que su alcance crece y tiene tope, y los activos bajo humo |
| `test_crisis_api.py` | El mapa de llegada en 16 bits (redondeo, "nunca", identificador inválido); la validación de la alerta y la conversión de hora y viento; la traducción de errores del motor a 400 y 503; el cruce de movilidad con identificadores inexistentes o inválidos |
| `test_nucleos.py` | El lector mínimo de teselas vectoriales (capa pedida, huecos con su exterior) y la conversión entre teselas y coordenadas |
| `test_tiempo_real.py` | La lectura de las posiciones de Renfe, de los puntos de medida de la ciudad (coma decimal, descarte de errores) y de las incidencias DATEX II de la DGT (corte frente a causa, tramos, registros sin coordenadas); el filtro por la Comunidad; que una fuente caída no tumba la otra; el cálculo de llamas y humo sobre una ventana ficticia y el cruce con una simulación guardada |
| `test_prealerta.py` | Los umbrales de Meteoalerta por zona y el índice de Fosberg; la lectura de la previsión diaria y horaria de AEMET sobre muestras locales de Madrid y el acumulado deslizante de 12 h; la lectura de un fichero CAP (solo el bloque en castellano, nivel, umbral, polígonos con exclave) y el filtro de avisos por día en hora local; el lector de Meteoalarm y la caída de AEMET a Meteoalarm con caché; los niveles por municipio y día (el aviso oficial manda solo en su zona; calor, viento y activaciones); los activos con efecto directo y activados y el recuento de sensibles; la API de prealerta sobre datos ficticios (resumen, municipio, activos, 404 y 400, actualización) |

Además, cada bloque se ha comprobado a mano en el navegador integrado: capas, activos, fichas, modo crisis con las tres simulaciones del apartado 7.9, reproductor y comunicaciones, y el modo prealerta con la previsión de muestra (apartado 8.6), sin errores de JavaScript.

## 11. Reproducibilidad e instalación

1. Python 3.12 o superior; crear un entorno virtual e instalar `requirements.txt` (versiones fijadas).
2. Opcional: copiar `.env.ejemplo` como `.env` con la clave de AEMET OpenData. Sin ella, el visor ofrece el viento a mano y la prealerta solo muestra los avisos oficiales, que van por el canal público.
3. `python -m procesamiento.cadena`: descarga las fuentes que falten, extrae los GeoTIFF a la caché y genera activos, rejilla, teselas, núcleos urbanos y la base de la prealerta (municipios, zonas de aviso, capas meteorológicas de cada activo y sus teselas).
4. `python -m procesamiento.servidor` y abrir `http://localhost:8765`. La primera vez que se entra en el modo prealerta, el servidor pide la previsión de los 179 municipios a AEMET en segundo plano (unos minutos) y la guarda para el resto del día.
5. `python -m pytest` para las pruebas.

Conexión necesaria: para descargar las fuentes la primera vez; en el visor, para el fondo del IGN y las librerías; en la prealerta, para la previsión diaria (una vez al día) y los avisos de AEMET; en la crisis, para el relieve de cada ventana nueva (se guarda en caché), el viento de AEMET y los focos de FIRMS; con las capas encendidas, para los trenes y el tráfico en tiempo real.

**Demo en línea:** no hay; el demostrador se usa en local.

## 12. Repositorio

Git, destinado a publicarse en GitHub como repositorio público (el formulario oficial de presentación cita GitHub y GitLab como ejemplos de repositorio). Licencia del código EUPL 1.2 (fichero `LICENSE`). Los datos conservan la licencia de su fuente. Finales de línea LF en todo el repositorio. Mensajes de commit en español.

```
cascada/
├── README.md              descripción, instalación, reproducción, fuentes y licencias
├── LICENSE                EUPL 1.2
├── requirements.txt
├── pytest.ini
├── .env.ejemplo           plantilla de claves (el .env real no se publica)
├── docs/                  memoria del demostrador y metodología
├── datos/
│   ├── registro.csv       URL, fecha y huella de cada descarga de la cadena
│   ├── brutos/            descargas (no se suben)
│   ├── cache/             descargas de uso y extracciones (no se suben)
│   ├── procesados/        resultados intermedios y simulaciones (no se suben)
│   └── visor/             ficheros que sirve el servidor (PMTiles, GeoJSON)
├── procesamiento/         cadena de datos, análisis basal, servidor y API
│   ├── incendio/          combustibles, Rothermel, propagación, entradas,
│   │                      consecuencias, humo, focos y simulación
│   ├── prealerta/         territorio, capas meteorológicas de los activos, previsión y
│   │                      avisos de AEMET, umbrales, cálculo y servicio
│   └── pruebas/           pruebas con pytest y muestras de AEMET (datos/)
└── visor/                 index.html, estilos.css, mapabase.js, app.js (basal),
                           prealerta.js, crisis.js, movilidad.js (trenes y tráfico)
```

Historial: un commit por bloque de trabajo.

## 13. Limitaciones conocidas

**Datos**

- Las coordenadas de los centros apuntan al interior de la parcela: en centros grandes (hospitales, campus) pueden estar a más de 200 m del portal, y con píxeles de 5 m el riesgo "en el punto" puede no recoger peligros del borde.
- El conjunto de centros sanitarios no publica el nombre del centro.
- Dentro de la Comunidad, lo que el mapa propio da como sin combustible (suelo urbano, agua, viales) actúa como barrera: el modelo no salta carreteras ni cortafuegos. Fuera de la Comunidad, el mapa de EFFIS, de 250 m y con la vegetación de hacia el año 2000, trata los cultivos como barrera.
- La población del INE está redondeada a múltiplos de 5.

**Modelo de incendio**

- No incluye fuego de copas, pavesas (focos secundarios), extinción ni cortafuegos.
- Humedad fija: no depende de la meteorología real del día.
- Viento homogéneo en toda la ventana, sin ajuste al relieve; cambia solo cada hora.
- El fuego no puede salir de la ventana de 50 km; si llega al borde, el visor lo avisa.
- La resolución efectiva de los resultados es la del combustible (250 m), aunque el cálculo sea a 50 m.
- El factor de viento a media llama está pendiente de verificar contra la publicación original.

**Efecto cascada**

- En el sur de la Comunidad varias zonas de alerta se solapan en una sola mancha de unos 12 km de radio: para esas instalaciones el radio de alerta se estima con la diferencia típica entre alerta e intervención de las aisladas (metodología, apartado 3.6).
- El centro de la zona aproxima la instalación, que ocupa una parcela.
- Los gasoductos van enterrados; el riesgo real está en las instalaciones de superficie, que el catálogo incluye en la franja pero no distingue.
- No se incluyen las vías de mercancías peligrosas ni las centrales eléctricas.

**Humo**

- Construcción geométrica: no tiene en cuenta la altura de la columna, la estabilidad atmosférica, el relieve ni las concentraciones. Señala qué activos pueden quedar a sotavento.

**Focos de satélite**

- Cada detección es un píxel de 375 m: indica fuego en el píxel, no su perímetro. Unas 6 pasadas al día; el humo denso y las nubes impiden la detección; los datos llegan unas horas después de la pasada.

**Trenes y tráfico en tiempo real**

- El cruce con la crisis es una foto: no proyecta el recorrido de los trenes ni la evolución del tráfico, y usa la situación actual aunque la simulación sea de otra fecha.
- El tráfico con nivel de servicio solo existe en el municipio de Madrid, lejos de casi todos los incendios; en el resto de la Comunidad solo hay incidencias de la DGT, no la congestión.
- Las incidencias de un tramo se representan por su inicio y se cruzan por sus dos extremos, no por su trazado.

**Prealerta**

- La previsión municipal de AEMET es un valor por municipio y día; las cantidades de lluvia y nieve solo existen en la horaria, que llega a tres días.
- El índice de Fosberg se calcula con valores diarios (máxima, humedad mínima, viento máximo) que no coinciden necesariamente en la misma hora, y no incluye la sequedad acumulada del combustible; sus clases y los umbrales de tormenta son criterios propios de Cascada.
- La activación de peligros basales es un cruce cualitativo (fenómeno en el municipio × peligrosidad en el punto), sin modelo físico de cada peligro.
- Los avisos oficiales solo llegan hasta pasado mañana; de ahí en adelante toda la prealerta es cálculo propio sobre la previsión.

**Visor**

- **Modo sin conexión:** con red, el visor pide el mapa directamente al IGN; para la defensa sin red, `procesamiento/sin_conexion.py` descarga de antemano las teselas del IGN de toda la Comunidad hasta el zoom 13 (y de una zona con más zoom), las tipografías y el MDT de 25 m de toda la Comunidad con el margen de una ventana (`datos/cache/mdt25_comunidad.tif`, del mismo WCS; el modelo lo usa en lugar de pedir el relieve de cada ventana cuando la cubre), y puede dejar calculada una simulación con viento a mano. Con `--sin-conexion`, el visor pide el mapa a esa copia (el servidor no descarga nada: solo sirve lo guardado), cualquier petición a internet falla en el acto, y el visor, que lo sabe por `/externo/configuracion.js`, limita el zoom de las fuentes del IGN al de las teselas guardadas, de modo que MapLibre las amplía al acercarse. Comprobado con el navegador sin acceso a nada fuera del equipo: mapa a los zooms 13 y 15 lejos de la zona preparada y simulaciones nuevas en El Escorial, Valdemaqueda y Galapagar, sin ninguna petición externa ni error. Sin red no hay viento de AEMET, focos de FIRMS, trenes ni tráfico.
- El criterio de 250 m es una distancia geométrica única para todos los activos y amenazas.

## 14. Parámetros del demostrador

| Parámetro | Valor |
|---|---|
| Celda del análisis basal | 1 km (rejilla europea) |
| Píxel de las capas | 5 m |
| Teselas | PNG 256 px, zoom 7 a 15 (las meteorológicas, 7 a 11) |
| Capas combinadas por grupo | nivel máximo del grupo por píxel, sin el fondo de incendios y avión; nivel más frecuente al alejarse |
| Agrupación de activos en el visor | hasta zoom 12, radio 42 px |
| Celda de la simulación | 50 m |
| Ventana | 50 × 50 km (1.000 × 1.000 celdas) |
| Horizonte | 24 h, cortes a 1, 3, 6, 12 y 24 h |
| Vecinos del grafo | 32 |
| Viento 10 m a 6,1 m | factor 1/1,15 |
| Relación longitud/anchura máxima de la elipse | 8 |
| Humedades (1 h, 10 h, 100 h, vivos) | 6, 7, 8 y 90 % |
| Distancia de alcanzado | 250 m |
| Fusión de centros Seveso entre capas | 300 m |
| Franja de conducción activada | 750 m |
| Humo: semiángulo, permanencia, alcance máximo, radio en calma | 20°, 2 h, 25 km, 500 m |
| Frente activo en el visor | últimos 20 min |
| Fuente fija (FIRMS) | 3 o más días con detecciones a menos de 500 m en 7 días |
| Intentos y espera con AEMET (viento) | 2 intentos de 20 s |
| Viento manual admitido | 0 a 150 km/h |
| Prealerta: horizonte | 7 días con la previsión diaria; 3 con la horaria |
| Prealerta: la horaria se pide si | probabilidad de precipitación ≥ 30 %, tormenta o nieve en los tres primeros días |
| Prealerta: umbrales | Plan Meteoalerta, anexo 1 (2022), por zona de aviso |
| Prealerta: tormenta | probabilidad ≥ 40 % amarillo, ≥ 70 % naranja |
| Prealerta: clases de Fosberg | < 15 bajo, < 30 moderado, < 50 alto, < 70 muy alto, resto extremo |
| Prealerta: activación de un peligro basal | fenómeno en amarillo o más y peligrosidad moderada (3) o superior |
| Prealerta: AEMET OpenData | 2 intentos de 15 s por petición; 3 municipios seguidos sin respuesta interrumpen; reintento cada 15 min |
| Prealerta: avisos | caché de 30 min; Meteoalarm de respaldo |
| Teselas meteorológicas | zoom 7 a 11, nivel más frecuente |

## 15. Pendiente

**Diseño por definir:**

- Mecanismo de la ficha restringida y contenido de la ficha común.
- Activos cercanos: detalle de los deslizadores de distancia y nivel de riesgo.
- Subtipos y filtrado de activos: acogida, colegios extranjeros, cuatro centros educativos dudosos, zonas de casas de niños, hogares y clubes.
- Parámetros del humo.
- Informes del diseño funcional.
- Segunda amenaza de crisis (nube tóxica o rotura de presa).
- Proyección del recorrido de los trenes que entran en la zona afectada.

**Previsto y no construido todavía:** marca de plan de autoprotección (RDPA) que sube un grado la vulnerabilidad; estaciones del CRTM con los viajeros por franja de Renfe; alerta automática por incidencias de la DGT de incendio o humo; núcleos oficiales de la Comunidad en lugar de los extraídos de las teselas.

**Verificaciones pendientes:**

- La prealerta con la previsión real de AEMET OpenData, y el muestreo y las teselas de las capas meteorológicas del catálogo (apartado 8.6).
- El botón de focos de FIRMS desde el visor (la API responde; no se ha ejercitado en el navegador).
- El factor de viento a media llama frente a Albini y Baughman (1979).
- La versión de la licencia Creative Commons Reconocimiento de las incidencias de la DGT: la ficha del punto de acceso nacional no la indica y el aviso legal general de la DGT no habla de reutilización (contacto del conjunto: el buzón del punto de acceso nacional). El tráfico del Ayuntamiento de Madrid es CC BY 4.0.

## 16. Referencias

- AEMET (2022). *Plan Meteoalerta. Anexo 1: umbrales*. Versión de 31 de mayo de 2022.
- Albini, F. A. (1976). *Estimating wildfire behavior and effects*. USDA Forest Service, INT-GTR-30.
- Albini, F. A. y Baughman, R. G. (1979). *Estimating windspeeds for predicting wildland fire behavior*. USDA Forest Service, INT-RP-221.
- Anderson, H. E. (1982). *Aids to determining fuel models for estimating fire behavior*. USDA Forest Service, INT-GTR-122.
- Anderson, H. E. (1983). *Predicting wind-driven wild land fire size and shape*. USDA Forest Service, INT-RP-305.
- Comunidad de Madrid (2025). *Catálogo de Riesgos Potenciales de la Comunidad de Madrid. Memoria metodológica*. Noviembre de 2025.
- European Forest Fire Information System (2017). *European Fuel Map*. Copernicus Emergency Management Service.
- Finney, M. A. (2002). Fire growth using minimum travel time methods. *Canadian Journal of Forest Research*, 32(8), 1420–1424.
- Fosberg, M. A. (1978). Weather in wildland fire management: the fire weather index. *Proceedings of the Conference on Sierra Nevada Meteorology*, American Meteorological Society, 1–4.
- Rothermel, R. C. (1972). *A mathematical model for predicting fire spread in wildland fuels*. USDA Forest Service, INT-RP-115.
