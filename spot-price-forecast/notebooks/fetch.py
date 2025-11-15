from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import pandas as pd
from forecaster.data import fingrid

dataset_id = '242'  # Changed from '246' to '242' for electricity production prediction
timezone = ZoneInfo('Europe/Helsinki')

# Fetch just 30 hours of data to avoid 429
dt_start = datetime(2024, 1, 1, 0, 0, tzinfo=timezone)
dt_end = dt_start + timedelta(hours=30)

start_time_utc_3339 = dt_start.astimezone(ZoneInfo('UTC')).isoformat().replace("+00:00", "Z")
end_time_utc_3339 = dt_end.astimezone(ZoneInfo('UTC')).isoformat().replace("+00:00", "Z")

print("Fetching data from:", start_time_utc_3339, "to", end_time_utc_3339)

# Get short descriptions of all datasets
dataset_shorts = fingrid.fetch_dataset_shorts()
fingrid.print_dataset_shorts(dataset_shorts)

# Fetch data (no pageSize)
data = fingrid.fetch_dataset_data(dataset_id, start_time_utc_3339, end_time_utc_3339)

# Convert to DataFrame
data = pd.DataFrame(data)
if 'endTime' in data.columns:
    data.drop(columns='endTime', inplace=True)
data['startTime'] = pd.to_datetime(data['startTime']).dt.tz_convert(timezone)
data.set_index('startTime', inplace=True)
data.sort_index(inplace=True)

# Save small sample to CSV
data.to_csv(f'../data/{dataset_id}_sample.csv')
print(f"Saved small dataset to ../data/{dataset_id}_sample.csv")