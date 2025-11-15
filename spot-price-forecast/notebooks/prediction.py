import os
import pandas as pd
import numpy as np
from forecaster.models import models
from forecaster.models.evaluate import calculate_metrics

# -------------------------------
# File paths
# -------------------------------
file_path = '../data/165.csv'

# -------------------------------
# Load CSV and parse dates
# -------------------------------
df = pd.read_csv(file_path)

# Convert startTime to datetime with UTC (handles mixed timezones)
df['startTime'] = pd.to_datetime(df['startTime'], utc=True)
# Remove timezone info to work with datetime64[ns]
df['startTime'] = df['startTime'].dt.tz_localize(None)

df.set_index('startTime', inplace=True)

# Rename column to 'y' for compatibility with the model
df.rename(
    columns={'Electricity consumption forecast - updated once a day': 'y'},
    inplace=True
)

print("="*60)
print("DATA LOADED")
print("="*60)
print(f"Date range: {df.index.min()} to {df.index.max()}")
print(f"Total records: {len(df)}")
print(f"Years in data: {sorted(df.index.year.unique())}")
print("\nFirst few rows:")
print(df.head())

# -------------------------------
# Initialize the model
# -------------------------------
external_features = {}  # Empty dict to disable external features

model = models.LinearModel(
    daily_price_lags=[1, 2, 3, 7],
    time_features=True,
    external_features=external_features,
    daily_external_lags=[]
)

print(f"\n{'='*60}")
print(f"MODEL CONFIGURATION")
print(f"{'='*60}")
print(f"Daily price lags: {model.daily_price_lags}")
print(f"Time features: {model.time_features}")
print(f"Total features: {model.nFeatures}")

# -------------------------------
# Preprocess data (create features)
# -------------------------------
print(f"\n{'='*60}")
print("PREPROCESSING DATA")
print(f"{'='*60}")
data_with_features = model.preprocess_data(df)
print(f"Shape after preprocessing: {data_with_features.shape}")
print(f"Date range after preprocessing: {data_with_features.index.min()} to {data_with_features.index.max()}")

# -------------------------------
# Train-test split (use 80-20 split instead of year-on-year)
# -------------------------------
print(f"\n{'='*60}")
print("TRAIN-TEST SPLIT")
print(f"{'='*60}")

# Use first 80% for training, last 20% for testing
split_idx = int(len(data_with_features) * 0.8)
train_data = data_with_features.iloc[:split_idx]
test_data = data_with_features.iloc[split_idx:]

print(f"Training set: {len(train_data)} samples ({train_data.index.min()} to {train_data.index.max()})")
print(f"Test set: {len(test_data)} samples ({test_data.index.min()} to {test_data.index.max()})")

# -------------------------------
# Train the model
# -------------------------------
print(f"\n{'='*60}")
print("TRAINING MODEL")
print(f"{'='*60}")

X_train = train_data.drop(columns='y')
y_train = train_data['y']

model.fit(X_train, y_train)
print("Model training complete!")

# -------------------------------
# Make predictions
# -------------------------------
print(f"\n{'='*60}")
print("MAKING PREDICTIONS")
print(f"{'='*60}")

# Predictions on training set
y_pred_train = model.predict(X_train)

# Predictions on test set
X_test = test_data.drop(columns='y')
y_test = test_data['y']
y_pred_test = model.predict(X_test)

# -------------------------------
# Evaluate model
# -------------------------------
print(f"\n{'='*60}")
print("MODEL PERFORMANCE")
print(f"{'='*60}")

train_metrics = calculate_metrics(y_train, y_pred_train)
test_metrics = calculate_metrics(y_test, y_pred_test)

print("\nTraining Set:")
print(f"  MAE:  {train_metrics['mean_absolute_error']:.2f}")
print(f"  RMSE: {train_metrics['root_mean_squared_error']:.2f}")

print("\nTest Set:")
print(f"  MAE:  {test_metrics['mean_absolute_error']:.2f}")
print(f"  RMSE: {test_metrics['root_mean_squared_error']:.2f}")

# Calculate additional statistics
print(f"\nActual values (test set):")
print(f"  Mean: {y_test.mean():.2f}")
print(f"  Std:  {y_test.std():.2f}")
print(f"  Min:  {y_test.min():.2f}")
print(f"  Max:  {y_test.max():.2f}")

print(f"\nPredicted values (test set):")
print(f"  Mean: {y_pred_test.mean():.2f}")
print(f"  Std:  {y_pred_test.std():.2f}")
print(f"  Min:  {y_pred_test.min():.2f}")
print(f"  Max:  {y_pred_test.max():.2f}")

# -------------------------------
# Merge predictions with original data
# -------------------------------
print(f"\n{'='*60}")
print("SAVING RESULTS")
print(f"{'='*60}")

# Create a dataframe with all predictions
all_predictions = pd.concat([y_pred_train, y_pred_test])
all_predictions.name = 'predicted_price'

# Merge with original data
result_df = df.copy()
result_df = result_df.merge(
    all_predictions,
    left_index=True,
    right_index=True,
    how='left'
)

# Reset index for CSV output
result_df.reset_index(inplace=True)

# -------------------------------
# Save to new CSV
# -------------------------------
directory, full_file_name = os.path.split(file_path)
file_name, file_extension = os.path.splitext(full_file_name)
new_full_file_name = f"{file_name}_with_predictions{file_extension}"
new_file_path = os.path.join(directory, new_full_file_name)

result_df.to_csv(new_file_path, index=False)
print(f"\nPredictions saved to: {new_file_path}")

print(f"\nSummary:")
print(f"  Total rows: {len(result_df)}")
print(f"  Rows with predictions: {result_df['predicted_price'].notna().sum()}")
print(f"  Rows without predictions: {result_df['predicted_price'].isna().sum()}")

print(f"\n{'='*60}")
print("SAMPLE OUTPUT")
print(f"{'='*60}")
print("\nFirst 5 rows with predictions:")
print(result_df[result_df['predicted_price'].notna()].head())
print("\nLast 5 rows with predictions:")
print(result_df[result_df['predicted_price'].notna()].tail())

# -------------------------------
# Optional: Create simple visualization
# -------------------------------
print(f"\n{'='*60}")
print("PREDICTION QUALITY CHECK")
print(f"{'='*60}")

# Show some sample comparisons
comparison = pd.DataFrame({
    'actual': y_test.values[:10],
    'predicted': y_pred_test.values[:10],
    'error': (y_test.values[:10] - y_pred_test.values[:10]),
    'error_pct': ((y_test.values[:10] - y_pred_test.values[:10]) / y_test.values[:10] * 100)
})
comparison.index = y_test.index[:10]
print("\nFirst 10 test predictions:")
print(comparison.round(2))

print(f"\n{'='*60}")
print("COMPLETE!")
print(f"{'='*60}")