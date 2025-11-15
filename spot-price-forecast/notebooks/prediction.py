import os
import pandas as pd
import numpy as np
import pickle
from datetime import datetime
from forecaster.models import models
from forecaster.models.evaluate import calculate_metrics


file_path = '../data/165.csv'
model_save_path = '../models/consumption_forecast_model.pkl'


df = pd.read_csv(file_path)

df['startTime'] = pd.to_datetime(df['startTime'], utc=True)
df['startTime'] = df['startTime'].dt.tz_localize(None)
df.set_index('startTime', inplace=True)


external_features = {} 

model = models.LinearModel(
    daily_price_lags=[1, 2, 3, 7],
    time_features=True,
    external_features=external_features,
    daily_external_lags=[]
)

data_with_features = model.preprocess_data(df)

# Use first 80% for training, last 20% for testing
split_idx = int(len(data_with_features) * 0.8)
train_data = data_with_features.iloc[:split_idx]
test_data = data_with_features.iloc[split_idx:]


X_train = train_data.drop(columns='y')
y_train = train_data['y']

model.fit(X_train, y_train)

# Predictions on training set
y_pred_train = model.predict(X_train)

# Predictions on test set
X_test = test_data.drop(columns='y')
y_test = test_data['y']
y_pred_test = model.predict(X_test)



directory, full_file_name = os.path.split(file_path)
file_name, file_extension = os.path.splitext(full_file_name)
new_full_file_name = f"{file_name}_with_predictions{file_extension}"
new_file_path = os.path.join(directory, new_full_file_name)



model_data = {
    'coeffs': model.coeffs,
    'daily_price_lags': model.daily_price_lags,
    'time_features': model.time_features,
    'external_features': model.external_features,
    'daily_external_lags': model.daily_external_lags,
    'nFeatures': model.nFeatures,
    'fit_coeffs': model.fit_coeffs,
    'saved_at': datetime.now().isoformat(),
}

with open(model_save_path, 'wb') as f:
    pickle.dump(model_data, f)

print(f"✓ Model saved to: {model_save_path}")

# Also save model info as JSON for easy inspection
json_path = model_save_path.replace('.pkl', '_info.json')
import json
info_data = {k: v for k, v in model_data.items() if k != 'coeffs'}
info_data['num_coefficients'] = len(model.coeffs)
with open(json_path, 'w') as f:
    json.dump(info_data, f, indent=2, default=str)
print(f"✓ Model info saved to: {json_path}")
print(f"\nModel is ready for forecasting!")