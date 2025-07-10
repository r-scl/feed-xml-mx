# Feed XML Processor - Accu-Chek México

Procesador automatizado de feeds XML para Google Merchant Center y Facebook Catalog.

## Características

- 🔄 Genera feeds separados optimizados para cada plataforma
- 🧹 Limpia URLs de productos (elimina títulos redundantes)
- 💰 Formatea precios correctamente
- 📝 Genera descripciones apropiadas para cada plataforma
- 🤖 Automatización con GitHub Actions

## Diferencias entre feeds

### Google Merchant Center (`feed_google.xml`)
- Mantiene namespace `g:`
- Descripciones simples (título + punto)
- Todos los campos requeridos por Google

### Facebook Catalog (`feed_facebook.xml`)
- Sin namespace (campos planos)
- Descripciones detalladas según tipo de producto
- Optimizado para Facebook Commerce

## Uso local

```bash
# Instalar dependencias
pip install -r requirements.txt

# Ejecutar procesador
python feed_processor.py
```

Los feeds se generan en el directorio `output/`:
- `output/feed_google.xml` - Para Google Merchant Center
- `output/feed_facebook.xml` - Para Facebook Catalog
- `output/metadata.json` - Información de la última actualización

## Automatización con GitHub Actions

El workflow se ejecuta:
- Diariamente a las 2 AM (hora de México)
- En cada push a la rama `main`
- Manualmente desde la pestaña Actions

### Configuración de GitHub Pages

1. Ve a Settings > Pages en tu repositorio
2. En "Source", selecciona "Deploy from a branch"
3. Selecciona la rama `gh-pages` y carpeta `/ (root)`
4. Guarda los cambios

### URLs de los feeds (después de configurar GitHub Pages)

- Google: `https://[tu-usuario].github.io/[repo]/feed_google.xml`
- Facebook: `https://[tu-usuario].github.io/[repo]/feed_facebook.xml`

**Nota**: La primera vez puede tomar unos minutos en estar disponible.

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

## Estructura del proyecto

```
FeedXML-MX/
├── feed_processor.py      # Script principal
├── requirements.txt       # Dependencias
├── .github/
│   └── workflows/
│       └── generate-feeds.yml  # GitHub Actions
└── output/               # Feeds generados (ignorado en git)
    ├── feed_google.xml
    ├── feed_facebook.xml
    └── metadata.json
```