#!/usr/bin/env python3
"""
Feed XML Processor for Accu-Chek Mexico
Procesa y genera feeds XML separados para Google Merchant y Facebook Catalog
"""

import xml.etree.ElementTree as ET
import requests
from urllib.parse import urlparse, urlunparse
import re
from datetime import datetime
import json
import os


class FeedProcessor:
    def __init__(self, feed_url):
        self.feed_url = feed_url
        self.namespaces = {
            'g': 'http://base.google.com/ns/1.0'
        }
    
    def fetch_feed(self):
        """Descarga el feed XML original"""
        response = requests.get(self.feed_url)
        response.raise_for_status()
        return response.text
    
    def clean_url(self, url):
        """
        Limpia las URLs eliminando el título del producto
        Ejemplo: https://tienda.accu-chek.com.mx/Main/Producto/1916/50-Tiras-Reactivas-Accu-Chek®-Instant
        Se convierte en: https://tienda.accu-chek.com.mx/Main/Producto/1916/
        """
        # Usar regex para extraer solo la parte base de la URL con el ID
        match = re.match(r'(https://tienda\.accu-chek\.com\.mx/Main/Producto/\d+/).*', url)
        if match:
            return match.group(1)
        return url
    
    def format_price(self, price, platform='both'):
        """
        Formatea el precio según la plataforma
        """
        # Extraer solo el número del precio
        price_match = re.match(r'(\d+\.?\d*)\s*MXN', price)
        if price_match:
            price_value = float(price_match.group(1))
            if platform == 'facebook':
                # Facebook: formato $380,50
                return f"${price_value:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
            else:
                # Google: mantener formato con MXN
                return f"{price_value:.2f} MXN"
        return price
    
    def generate_description(self, title, platform='both'):
        """
        Genera descripciones apropiadas para cada plataforma
        """
        base_desc = title.strip()
        
        # Solo agregar punto final si no lo tiene
        if not base_desc.endswith('.'):
            base_desc += '.'
        
        return base_desc
    
    def process_feed_google(self, root):
        """Procesa el feed para Google Merchant Center"""
        # Crear copia profunda del XML
        google_root = ET.fromstring(ET.tostring(root))
        channel = google_root.find('channel')
        items = channel.findall('item')
        
        for item in items:
            # URL limpia (Google acepta ambas, pero mejor limpia)
            link_elem = item.find('.//g:link', self.namespaces)
            if link_elem is not None and link_elem.text:
                link_elem.text = self.clean_url(link_elem.text)
            
            # Precio formateado
            price_elem = item.find('.//g:price', self.namespaces)
            if price_elem is not None and price_elem.text:
                price_elem.text = self.format_price(price_elem.text, 'google')
            
            # GTIN - Enviar siempre vacío
            gtin_elem = item.find('.//g:gtin', self.namespaces)
            if gtin_elem is not None:
                gtin_elem.text = ""
            
            # Descripción simple con punto
            desc_elem = item.find('.//g:description', self.namespaces)
            title_elem = item.find('.//g:title', self.namespaces)
            if desc_elem is not None and title_elem is not None:
                desc_elem.text = self.generate_description(title_elem.text, 'google')
        
        return google_root
    
    def process_feed_facebook(self, root):
        """Procesa el feed para Facebook Catalog"""
        # Crear nuevo root sin namespace
        fb_root = ET.Element('rss', version='2.0')
        fb_channel = ET.SubElement(fb_root, 'channel')
        
        # Información del canal
        channel = root.find('channel')
        ET.SubElement(fb_channel, 'title').text = 'Tienda Accuchek Mexico'
        ET.SubElement(fb_channel, 'link').text = 'https://tienda.accu-chek.com.mx'
        ET.SubElement(fb_channel, 'description').text = 'Productos Accu-Chek para el cuidado de la diabetes'
        
        # Procesar items
        items = channel.findall('item')
        for item in items:
            fb_item = ET.SubElement(fb_channel, 'item')
            
            # ID del producto
            id_elem = item.find('.//g:id', self.namespaces)
            if id_elem is not None:
                ET.SubElement(fb_item, 'id').text = id_elem.text
            
            # Título
            title_elem = item.find('.//g:title', self.namespaces)
            if title_elem is not None:
                ET.SubElement(fb_item, 'title').text = title_elem.text
            
            # Descripción detallada para Facebook
            if title_elem is not None:
                ET.SubElement(fb_item, 'description').text = self.generate_description(title_elem.text, 'facebook')
            
            # URL limpia
            link_elem = item.find('.//g:link', self.namespaces)
            if link_elem is not None:
                ET.SubElement(fb_item, 'link').text = self.clean_url(link_elem.text)
            
            # Imagen
            image_elem = item.find('.//g:image_link', self.namespaces)
            if image_elem is not None:
                ET.SubElement(fb_item, 'image_link').text = image_elem.text
            
            # Disponibilidad
            avail_elem = item.find('.//g:availability', self.namespaces)
            if avail_elem is not None:
                ET.SubElement(fb_item, 'availability').text = avail_elem.text
            
            # Condición
            cond_elem = item.find('.//g:condition', self.namespaces)
            if cond_elem is not None:
                ET.SubElement(fb_item, 'condition').text = cond_elem.text
            
            # Precio
            price_elem = item.find('.//g:price', self.namespaces)
            if price_elem is not None:
                ET.SubElement(fb_item, 'price').text = self.format_price(price_elem.text, 'facebook')
            
            # Marca
            brand_elem = item.find('.//g:brand', self.namespaces)
            if brand_elem is not None and brand_elem.text:
                ET.SubElement(fb_item, 'brand').text = brand_elem.text
            
            # GTIN
            gtin_elem = item.find('.//g:gtin', self.namespaces)
            if gtin_elem is not None:
                ET.SubElement(fb_item, 'gtin').text = gtin_elem.text
        
        return fb_root
    
    def process_feeds(self):
        """Procesa y genera ambos feeds"""
        # Obtener el XML original
        xml_content = self.fetch_feed()
        root = ET.fromstring(xml_content)
        
        # Procesar para cada plataforma
        google_root = self.process_feed_google(root)
        facebook_root = self.process_feed_facebook(root)
        
        return google_root, facebook_root
    
    def save_feed(self, root, output_file, platform='google'):
        """Guarda el feed procesado"""
        if platform == 'google':
            # Registrar el namespace para mantener el prefijo 'g:'
            ET.register_namespace('g', 'http://base.google.com/ns/1.0')
        
        # Crear el árbol y guardarlo
        tree = ET.ElementTree(root)
        tree.write(output_file, encoding='utf-8', xml_declaration=True)
        
        # Leer el archivo y formatearlo mejor
        with open(output_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Agregar la declaración XML correcta y formatear
        if '<?xml' not in content:
            formatted_content = '<?xml version="1.0" encoding="UTF-8"?>\n' + content
        else:
            formatted_content = content
        
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(formatted_content)
        
        return output_file


def main():
    # URL del feed original
    feed_url = 'https://tienda.accu-chek.com.mx/Main/FeedXML'
    
    print("Procesando feed XML de Accu-Chek México...")
    print(f"Obteniendo feed desde: {feed_url}")
    
    processor = FeedProcessor(feed_url)
    
    try:
        # Procesar ambos feeds
        google_root, facebook_root = processor.process_feeds()
        
        # Crear directorio de salida si no existe
        os.makedirs('output', exist_ok=True)
        
        # Guardar feed de Google
        google_file = processor.save_feed(google_root, 'output/feed_google.xml', 'google')
        print(f"\n✅ Feed de Google Merchant procesado!")
        print(f"📄 Archivo: {google_file}")
        
        # Guardar feed de Facebook
        facebook_file = processor.save_feed(facebook_root, 'output/feed_facebook.xml', 'facebook')
        print(f"\n✅ Feed de Facebook Catalog procesado!")
        print(f"📄 Archivo: {facebook_file}")
        
        print("\n📊 Diferencias entre feeds:")
        print("- Google: Mantiene namespace g:, descripciones simples")
        print("- Facebook: Sin namespace, descripciones detalladas")
        print("- Ambos: URLs limpias, precios formateados")
        
        # Guardar metadata
        metadata = {
            'last_update': datetime.now().isoformat(),
            'source_url': feed_url,
            'google_feed': google_file,
            'facebook_feed': facebook_file
        }
        
        with open('output/metadata.json', 'w') as f:
            json.dump(metadata, f, indent=2)
        
    except Exception as e:
        print(f"\n❌ Error procesando los feeds: {e}")
        raise


if __name__ == "__main__":
    main()