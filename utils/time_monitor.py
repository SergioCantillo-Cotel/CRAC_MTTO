import pandas as pd

def round_down_10_minutes():
    now = pd.Timestamp.now(tz='UTC-05:00')
    # Redondear hacia abajo a los 10 minutos
    rounded_minute = (now.minute // 10) * 10
    rounded_time = now.replace(minute=rounded_minute, second=0, microsecond=0)
    return rounded_time.strftime("%Y-%m-%d %H:%M")