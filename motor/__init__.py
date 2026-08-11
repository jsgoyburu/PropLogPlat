# motor/__init__.py
# Re-exporta la interfaz pública para que los consumidores hagan:
#   from motor import verificar, generar_tabla, parsear, verificar_argumento

from .verificador import verificar, generar_tabla, parsear, verificar_argumento, verificar_determinacion
from .parser import normalizar_simbolos

__all__ = ["verificar", "generar_tabla", "parsear", "normalizar_simbolos", "verificar_argumento", "verificar_determinacion"]
