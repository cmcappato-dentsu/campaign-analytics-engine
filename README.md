# Campaign Analytics Engine

Motor interno para el procesamiento automatizado, normalización y análisis de performance de campañas de publicidad digital.

El proyecto está inicialmente orientado al procesamiento de reportes exportados desde Google Ads y diseñado para evolucionar hacia una solución extensible de análisis de Paid Media.

---

## Índice

- [Descripción](#descripción)
- [Requisitos](#requisitos)
- [Instalación](#instalación)
  - [Ubicarse en la carpeta del proyecto](#ubicarse-en-la-carpeta-del-proyecto)
  - [Crear el entorno virtual](#crear-el-entorno-virtual)
  - [Activar el entorno virtual](#activar-el-entorno-virtual)
  - [Solución de problemas en PowerShell](#solución-de-problemas-en-powershell)
  - [Instalar dependencias](#instalar-dependencias)
- [Estructura del proyecto](#estructura-del-proyecto)
- [Ejecución](#ejecución)
- [Tests](#tests)
- [Desactivar el entorno virtual](#desactivar-el-entorno-virtual)
- [Documentación interna](#documentación-interna)

---

## Descripción

Campaign Analytics Engine es una herramienta interna orientada a automatizar el procesamiento inicial de reportes de campañas de publicidad digital.

El proyecto contempla:

- Lectura de archivos CSV y Excel.
- Soporte para reportes en español e inglés.
- Normalización de nombres de columnas.
- Limpieza y tipado de datos.
- Eliminación de filas de resumen o totales.
- Validación de la estructura de los reportes.
- Cálculo de métricas de performance.
- Generación de datasets diarios.
- Agregación de información por campaña.
- Preparación de datos para análisis automatizado.

El proyecto está inicialmente enfocado en reportes exportados desde Google Ads.

---

## Requisitos

Antes de comenzar, se requiere tener instalado:

- Python 3.13
- pip
- Git, opcionalmente, para control de versiones

Para verificar las versiones de Python instaladas en Windows:

```powershell
py --list
```

La versión recomendada para este proyecto es Python 3.13.

Para consultar la versión activa:

```powershell
python --version
```

---

## Instalación

### Ubicarse en la carpeta del proyecto

Abrir PowerShell y navegar hasta la raíz del proyecto:

```powershell
cd "ruta\del\proyecto"
```

Ejemplo:

```powershell
cd "C:\Users\usuario\Documentos\campaign-analytics-engine"
```

---

### Crear el entorno virtual

Desde la raíz del proyecto, ejecutar:

```powershell
py -3.13 -m venv .venv
```

Esto creará un entorno virtual local utilizando Python 3.13.

La carpeta `.venv` contiene las dependencias aisladas del proyecto y no debe subirse al repositorio.

---

### Activar el entorno virtual

En Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

Si la activación fue correcta, el nombre del entorno aparecerá al inicio de la terminal:

```text
(.venv) PS C:\ruta\del\proyecto>
```

Para verificar que se está utilizando la versión correcta de Python:

```powershell
python --version
```

Resultado esperado:

```text
Python 3.13.x
```

---

### Solución de problemas en PowerShell

Si al ejecutar:

```powershell
.\.venv\Scripts\Activate.ps1
```

aparece un error similar a:

```text
La ejecución de scripts está deshabilitada en este sistema
```

PowerShell está bloqueando la ejecución del script de activación.

Para habilitar la ejecución de scripts para el usuario actual, ejecutar:

```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

Confirmar con `Y` si se solicita autorización.

Luego volver a ejecutar:

```powershell
.\.venv\Scripts\Activate.ps1
```

#### Alternativa sin modificar la política de PowerShell

También puede utilizarse el activador de CMD:

```powershell
.\.venv\Scripts\activate.bat
```

---

### Instalar dependencias

Con el entorno virtual activado, actualizar `pip`:

```powershell
python -m pip install --upgrade pip
```

Instalar las dependencias del proyecto:

```powershell
pip install -r requirements.txt
```

---

## Estructura del proyecto

```text
campaign-analytics-engine/
│
├── .venv/                         # Entorno virtual local
│
├── config/                        # Configuraciones del proyecto
│   ├── __init__.py
│   ├── column_mapping.py          # Aliases y nombres canónicos
│   ├── constants.py               # Constantes generales
│   ├── thresholds.py              # Umbrales de análisis
│   └── settings.py                # Rutas y configuración
│
├── data/
│   ├── input/                     # Archivos originales de entrada
│   ├── processed/                 # Datos procesados
│   └── output/                    # Resultados generados
│
├── notebooks/                     # Notebooks de exploración
│   └── exploration.ipynb
│
├── src/                           # Código fuente principal
│   ├── __init__.py
│   ├── loader.py                  # Carga de archivos
│   ├── cleaner.py                 # Limpieza y normalización
│   ├── metrics.py                 # Cálculo de métricas
│   ├── eligibility.py             # Criterios de elegibilidad
│   ├── diagnostics.py             # Diagnósticos
│   ├── pareto.py                  # Análisis de Pareto
│   ├── outliers.py                # Detección de outliers
│   ├── scoring.py                 # Scoring de campañas
│   ├── reporting.py               # Generación de reportes
│   └── pipeline.py                # Orquestación del flujo
│
├── tests/                         # Pruebas automatizadas
│   ├── __init__.py
│   ├── test_loader.py
│   ├── test_cleaner.py
│   └── test_metrics.py
│
├── docs/                          # Documentación interna
│
├── app.py                         # Aplicación Streamlit
├── requirements.txt               # Dependencias del proyecto
├── README.md                      # Documentación principal
└── .gitignore                     # Archivos excluidos de Git
```

---

## Ejecución

Para ejecutar la aplicación Streamlit:

```powershell
streamlit run app.py
```

La aplicación se abrirá en el navegador predeterminado.

---

## Tests

Para ejecutar las pruebas automatizadas:

```powershell
pytest
```

Para obtener información detallada de cada prueba:

```powershell
pytest -v
```

---

## Desactivar el entorno virtual

Cuando se termine de trabajar en el proyecto:

```powershell
deactivate
```

Para volver a activarlo en una próxima sesión:

```powershell
.\.venv\Scripts\Activate.ps1
```

---

## Documentación interna

La documentación funcional, metodológica y de diseño del proyecto se encuentra en la carpeta `docs/`.

Esta documentación incluye:

- Contexto del negocio.
- Roadmap.
- Decisiones de arquitectura.
- Análisis de los reportes de Google Ads.
- Diccionario de datos.
- Definición de métricas.
- Criterios de elegibilidad.
- Lógica de análisis.
- Diagnósticos.
- Scoring.
- Registro de decisiones técnicas.
- Evolución y pendientes del proyecto.
