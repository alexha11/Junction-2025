import pickle
import pandas as pd
from datetime import datetime, timedelta
from forecaster.models import models

# Load model
with open("../models/consumption_forecast_model.pkl", "rb") as f:
    md = pickle.load(f)

model = models.LinearModel(
    daily_price_lags=md["daily_price_lags"],
    time_features=md["time_features"],
)
model.coeffs = md["coeffs"]

# Load historical data
df = pd.read_csv("../data/165.csv")
df["startTime"] = pd.to_datetime(df["startTime"], utc=True).dt.tz_localize(None)
df.set_index("startTime", inplace=True)
hist = model.preprocess_data(df)

feature_cols = hist.drop(columns="y").columns.tolist()
last_row = hist.iloc[-1]
max_lag = max(model.daily_price_lags)
recent_values = hist['y'].iloc[-max_lag:].tolist()

# Forecast starting from now
now = datetime.now()
forecast_hours = pd.date_range(start=now, periods=24, freq="h")
predictions = []

for ts in forecast_hours:
    features = {}
    for lag in model.daily_price_lags:
        features[f'y_lag_avg_{lag}'] = recent_values[-lag] if len(recent_values) >= lag else recent_values[-1]
    
    hour = ts.hour
    is_weekend = ts.weekday() >= 5
    for col in feature_cols:
        if col.startswith("weekday_hour_") or col.startswith("weekend_hour_"):
            features[col] = 0.0
    current = f"weekend_hour_{hour}" if is_weekend else f"weekday_hour_{hour}"
    if current in feature_cols:
        features[current] = 1.0
    
    X = pd.DataFrame([[features.get(col, last_row[col] if col in last_row.index and col != 'y' else 0.0)
                       for col in feature_cols]], columns=feature_cols)

    y_hat = abs(model.predict(X).values[0])  # Use absolute value
    predictions.append((ts, y_hat))
    recent_values.append(y_hat)
    recent_values = recent_values[-max_lag:]

pred_df = pd.DataFrame(predictions, columns=["timestamp", "prediction"])
pred_df["hour"] = pred_df["timestamp"].dt.hour

print("\n" + "="*60)
print(f"GENERATING PRICE FORECAST FOR NEXT 24 HOURS STARTING {now.strftime('%A, %B %d, %Y %H:%M')}")
print("="*60 + "\n")
print("="*60)
print("24-HOUR PRICE FORECAST")
print("="*60)
print(pred_df[["hour", "prediction"]].round(2).to_string(index=False))
