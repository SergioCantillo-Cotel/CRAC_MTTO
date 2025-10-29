import pandas as pd

# Si el archivo está guardado como CSV
df = pd.read_csv(
    'reporte_mttos.csv',
    quotechar='"',
    doublequote=True,
    escapechar='\\',
    na_filter=False,
    keep_default_na=False
)
print(df[['serial','hora_salida']])
