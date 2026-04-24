class AppError(Exception):
    """Base de errores de la aplicación."""


class ValidationError(AppError):
    """Errores de validación de input o formato."""


class ProcessingError(AppError):
    """Errores durante el procesamiento del archivo."""


class StorageError(AppError):
    """Errores de persistencia o lectura/escritura."""


class ExportError(AppError):
    """Errores al generar CSV/XLSX u otros artefactos."""