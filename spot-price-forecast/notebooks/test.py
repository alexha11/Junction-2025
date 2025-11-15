import pickle
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from forecaster.models import models

model_path = "../models/consumption_forecast_model.pkl"

with open(model_path, "rb") as f:
    md = pickle.load(f)

model = models.LinearModel(
    daily_price_lags=md["daily_price_lags"],
    time_features=md["time_features"],
    external_features=md["external_features"],
    daily_external_lags=md["daily_external_lags"],
    fit_coeffs=md["fit_coeffs"]
)
model.coeffs = md["coeffs"]

print("✓ Model loaded")

data_path = "../data/165.csv"
df = pd.read_csv(data_path)
df["startTime"] = pd.to_datetime(df["startTime"], utc=True).dt.tz_localize(None)
df.set_index("startTime", inplace=True)


print("✓ Data loaded")

# Historical feature generation
hist = model.preprocess_data(df)
print("✓ Historical features prepared")

feature_cols = hist.drop(columns="y").columns.tolist()
last_row = hist.iloc[-1].copy()
last_actual = last_row['y']

print(f"\n✓ Last known value: {last_actual:.2f}")
print(f"  Last timestamp: {hist.index[-1]} ({hist.index[-1].strftime('%A')})")

# Store recent actual values
max_lag = max(model.daily_price_lags)
recent_values = hist['y'].iloc[-max_lag:].values.tolist()

print(f"\n✓ Historical context (last 7 days at same hour as last observation):")
last_hour = hist.index[-1].hour
for lag in [1, 2, 3, 7]:
    idx = -24 * lag
    if abs(idx) <= len(hist):
        val = hist['y'].iloc[idx]
        ts = hist.index[idx]
        print(f"  {lag} day(s) ago ({ts.strftime('%A %H:%M')}): {val:.2f}")


def build_feature_vector(ts, recent_values, last_row, feature_cols):
    """Build complete feature vector for a given timestamp."""
    features = {}
    
    # Update lag features
    for lag in model.daily_price_lags:
        lag_col = f'y_lag_avg_{lag}'
        if len(recent_values) >= lag:
            features[lag_col] = recent_values[-lag]
        else:
            features[lag_col] = recent_values[-1]
    
    # Time features
    hour = ts.hour
    is_weekend = 1 if ts.weekday() >= 5 else 0
    
    # Set all time features to 0
    for col in feature_cols:
        if col.startswith('weekday_hour_') or col.startswith('weekend_hour_'):
            features[col] = 0.0
    
    # Set the current hour feature
    if is_weekend:
        current_feature = f'weekend_hour_{hour}'
    else:
        current_feature = f'weekday_hour_{hour}'
    
    if current_feature in feature_cols:
        features[current_feature] = 1.0
    
    # Build final vector
    feature_vector = {}
    for col in feature_cols:
        if col in features:
            feature_vector[col] = features[col]
        else:
            if col in last_row.index and col != 'y':
                feature_vector[col] = last_row[col]
            else:
                feature_vector[col] = 0.0
    
    return pd.DataFrame([feature_vector], columns=feature_cols)


tomorrow = (datetime.now() + timedelta(days=10)).date()
forecast_hours = pd.date_range(
    start=datetime.combine(tomorrow, datetime.min.time()),
    periods=24,
    freq="h"
)

predictions = []
print(f"\n{'='*60}")
print(f"GENERATING PRICE FORECAST FOR {tomorrow.strftime('%A, %B %d, %Y')}")
print(f"{'='*60}\n")

for i, ts in enumerate(forecast_hours):
    X = build_feature_vector(ts, recent_values, last_row, feature_cols)
    y_hat = model.predict(X).values[0]
    predictions.append((ts, y_hat))
    
    # Update recent_values
    recent_values.append(y_hat)
    recent_values = recent_values[-max_lag:]

pred_df = pd.DataFrame(predictions, columns=["timestamp", "prediction"])
pred_df["hour"] = pred_df["timestamp"].dt.hour
pred_df["weekday"] = pred_df["timestamp"].dt.day_name()

print(f"{'='*60}")
print("24-HOUR PRICE FORECAST")
print(f"{'='*60}")
print(pred_df[["hour", "prediction"]].round(2).to_string(index=False))
