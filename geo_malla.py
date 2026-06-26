"""
Geometría de la malla de cómputo SWAN.

Convierte una definición en lat/lon (centro + tamaño + resolución) en los campos
UTM que usa el formulario "Armar y correr" (xpc/ypc/xlenc/ylenc/mxc/myc) y deriva
la zona UTM sola, para no tener que saber el origen UTM a mano.
"""

from pyproj import Transformer

from io_batimetria import epsg_utm


def _zona_utm(lat, lon):
    """Zona UTM ('19S', '18S', '19N', ...) del punto."""
    zona = int((lon + 180) // 6) + 1
    return f"{zona}{'S' if lat < 0 else 'N'}"


def malla_desde_latlon(lat_centro, lon_centro, ancho_km, alto_km, celda_m):
    """
    Campos de malla UTM para un dominio centrado en (lat, lon).

    ancho_km/alto_km: extensión; celda_m: tamaño de celda. La zona UTM se deriva
    del centro. Devuelve {xpc, ypc, xlenc, ylenc, mxc, myc, zona_utm}. Lanza
    ValueError si los datos no son físicos.
    """
    if not -90.0 <= lat_centro <= 90.0:
        raise ValueError(f"Latitud fuera de rango: {lat_centro}")
    if not -180.0 <= lon_centro <= 180.0:
        raise ValueError(f"Longitud fuera de rango: {lon_centro}")
    if ancho_km <= 0 or alto_km <= 0:
        raise ValueError("El ancho y el alto deben ser positivos.")
    if celda_m <= 0:
        raise ValueError("El tamaño de celda debe ser positivo.")

    xlenc = float(ancho_km) * 1000.0
    ylenc = float(alto_km) * 1000.0
    mxc = int(round(xlenc / celda_m))
    myc = int(round(ylenc / celda_m))
    if mxc < 2 or myc < 2:
        raise ValueError("La celda es demasiado grande: se necesitan al menos "
                         "2 celdas por lado.")

    zona = _zona_utm(lat_centro, lon_centro)
    a_utm = Transformer.from_crs(4326, epsg_utm(zona), always_xy=True)
    x_c, y_c = a_utm.transform(lon_centro, lat_centro)

    return {"xpc": x_c - xlenc / 2.0, "ypc": y_c - ylenc / 2.0,
            "xlenc": xlenc, "ylenc": ylenc, "mxc": mxc, "myc": myc,
            "zona_utm": zona}
