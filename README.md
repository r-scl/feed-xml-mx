# FeedXML-MX

Procesador de feeds XML para Accu-Chek México que genera feeds optimizados para Google Merchant Center y Facebook Catalog.

## Descripción

Este proyecto automatiza la transformación del feed de productos de Accu-Chek México (`https://tienda.accu-chek.com.mx/Main/FeedXML`) en dos formatos optimizados:

- **Google Merchant Center**: Feed XML con namespace `g:` y formato de precios estándar
- **Facebook Catalog**: Feed XML sin namespaces, precios en formato europeo y descripciones mejoradas

## Características

### Versión Básica (`feed_processor.py`)
- ✅ Transformación de XML con limpieza de URLs
- 💰 Formateo de precios específico por plataforma
- 📝 Generación de descripciones apropiadas
- 🔧 Preservación de todos los campos requeridos

### Versión Mejorada (`feed_processor_v2.py`)
- 🌐 Web scraping con Playwright para detalles adicionales
- 📊 Extracción de datos estructurados (`dataProd`) de las páginas
- 🚫 Detección y exclusión de páginas de error (404)
- 🖼️ Captura de imágenes adicionales (hasta 5 por producto)
- 📋 Logging detallado del proceso

## Diferencias entre Feeds

### Google Merchant Center (`feed_google.xml`)
- Mantiene namespace XML (`g:`)
- Formato de precio: `380.50 MXN`
- Descripciones simples con punto final
- URLs limpias sin título de producto

### Facebook Catalog (`feed_facebook.xml`)
- Sin namespaces XML
- Formato de precio: `$380,50` (estilo europeo)
- Descripciones idénticas a las de Google
- Estructura plana de campos

## Instalación

### Requisitos
- Python 3.10+
- pip

### Pasos

1. Clonar el repositorio:
```bash
git clone https://github.com/tu-usuario/FeedXML-MX.git
cd FeedXML-MX
```

2. Instalar dependencias:
```bash
pip install -r requirements.txt
```

3. Para la versión v2 (con web scraping):
```bash
playwright install chromium
```

## Uso

### Ejecutar versión básica:
```bash
python feed_processor.py
```

### Ejecutar versión mejorada:
```bash
python feed_processor_v2.py
```

### Archivos de salida:
Los feeds generados se guardan en el directorio `output/`:
- `feed_google.xml` - Feed para Google Merchant Center
- `feed_facebook.xml` - Feed para Facebook Catalog
- `metadata.json` - Metadatos de la última ejecución
- `product_details.json` - Detalles adicionales de productos (solo v2)

## Automatización con GitHub Actions

El proyecto incluye un workflow de GitHub Actions que:
- Se ejecuta diariamente a las 2 AM (hora de México)
- Se activa en cada push a la rama `main`
- Permite ejecución manual con opción de habilitar/deshabilitar scraping
- Publica los feeds en GitHub Pages (opcional)

### Configurar GitHub Pages:
1. Ir a Settings > Pages en el repositorio
2. Seleccionar "Deploy from a branch"
3. Elegir la rama `gh-pages`
4. El workflow creará esta rama automáticamente

### URLs de los feeds (después de configurar GitHub Pages):
- Google: `https://[tu-usuario].github.io/[repo]/feed_google.xml`
- Facebook: `https://[tu-usuario].github.io/[repo]/feed_facebook.xml`

## Configuración en las plataformas

### Google Merchant Center
1. Ve a Feeds > + Nuevo feed
2. Selecciona "Scheduled fetch"
3. Ingresa la URL del feed de Google
4. Configura la frecuencia de actualización

### Facebook Commerce Manager
1. Ve a Catálogo > Orígenes de datos
2. Agregar productos > Feed de datos
3. Ingresa la URL del feed de Facebook
4. Configura actualización automática

## Estructura del Proyecto

```
FeedXML-MX/
├── feed_processor.py       # Procesador básico
├── feed_processor_v2.py    # Procesador con web scraping
├── requirements.txt        # Dependencias de Python
├── .github/
│   └── workflows/
│       └── generate-feeds.yml  # Workflow de GitHub Actions
├── output/                 # Directorio de salida (gitignored)
│   ├── feed_google.xml
│   ├── feed_facebook.xml
│   ├── metadata.json
│   └── product_details.json
├── CLAUDE.md              # Guía para Claude Code
└── README.md              # Este archivo
```

## Desarrollo

### Agregar nuevas transformaciones:
1. Modificar el método correspondiente en `FeedProcessor`
2. Para Google: `process_feed_google()`
3. Para Facebook: `process_feed_facebook()`

### Depuración:
- Los logs detallados se muestran en consola durante la ejecución
- La versión v2 incluye timestamps y estadísticas de procesamiento
- Revisar `output/metadata.json` para información de la última ejecución

## Dependencias

- `requests`: HTTP requests para obtener el feed XML
- `playwright`: Web scraping para detalles adicionales (v2)
- `beautifulsoup4`: Parsing de HTML para contenido scrapeado
- `lxml`: Parsing de XML con soporte de namespaces
- `pydantic`: Validación de datos estructurados

## Contribuir

1. Fork el proyecto
2. Crear una rama para tu feature (`git checkout -b feature/AmazingFeature`)
3. Commit tus cambios (`git commit -m 'Add some AmazingFeature'`)
4. Push a la rama (`git push origin feature/AmazingFeature`)
5. Abrir un Pull Request

## Licencia

Este proyecto es privado y propiedad de Accu-Chek México.

## Contacto

Para preguntas o soporte, contactar al equipo de desarrollo de Accu-Chek México.